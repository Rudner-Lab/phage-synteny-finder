#!/usr/bin/env python3
"""
scrape_phamerator.py
--------------------
Scrapes all phage genomes (and their genes) from the Phamerator API for a
given dataset and stores them in a local SQLite database.

Phamily membership is *not* stored as a separate table — it is fully
reconstructable from the genes table:
    SELECT * FROM genes WHERE pham_name = '12345'

Usage
-----
    .venv/bin/python scripts/scrape_phamerator.py
    .venv/bin/python scripts/scrape_phamerator.py --dataset Actino_Draft --output phamerator.sqlite

Credentials
-----------
An API key is required. Resolution order:
  1. --api-key flag
  2. PHAMERATOR_API_KEY environment variable (or .env file)
  3. macOS Keychain (service "phamerator_api_key", account "phamerator")

Store the key in Keychain once with:

    security add-generic-password -a "phamerator" -s "phamerator_api_key" -w

Then no flags are needed at all.

Rate-limiting behaviour (all configurable via CLI flags)
---------------------------------------------------------
  --delay       Seconds to sleep between successful requests  (default: 2.0)
  --retry-wait  Base wait in seconds before retrying a failed request (default: 5.0)
  --max-retries Maximum number of retry attempts per phage    (default: 3)

The script is fully resumable: re-running it will skip any phage already
marked 'success' in the scrape_log table.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit(
        "ERROR: 'requests' is not installed.\n"
        "Run in this project venv:  .venv/bin/python -m pip install requests\n"
        "Or:   .venv/bin/python -m pip install requests python-dotenv"
    )

# Optional: load a .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://phamerator.org/api"


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS phages (
    phage_id            TEXT NOT NULL,
    dataset             TEXT NOT NULL,
    phagename           TEXT,
    cluster             TEXT,
    subcluster          TEXT,
    cluster_subcluster  TEXT,
    genome_length       INTEGER,
    is_draft            INTEGER NOT NULL DEFAULT 0,
    scraped_at          TEXT,
    PRIMARY KEY (phage_id, dataset)
);

CREATE TABLE IF NOT EXISTS genes (
    gene_id         TEXT NOT NULL,
    phage_id        TEXT NOT NULL,
    dataset         TEXT NOT NULL,
    name            TEXT,
    accession       TEXT,
    start           INTEGER,
    stop            INTEGER,
    midpoint        REAL,
    gap             INTEGER,
    direction       TEXT,
    pham_color      TEXT,
    pham_name       TEXT,
    translation     TEXT,
    gene_function   TEXT,
    locus_tag       TEXT,
    domain_count    INTEGER,
    tm_domain_count INTEGER,
    is_draft        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (gene_id, dataset)
);

CREATE INDEX IF NOT EXISTS idx_genes_phage    ON genes (phage_id, dataset);
CREATE INDEX IF NOT EXISTS idx_genes_pham     ON genes (pham_name);

CREATE TABLE IF NOT EXISTS scrape_log (
    phage_id     TEXT NOT NULL,
    dataset      TEXT NOT NULL,
    is_draft     INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT,
    error_msg    TEXT,
    PRIMARY KEY (phage_id, dataset)
);
"""


def strip_draft(name: str) -> tuple[str, int]:
    """Return (clean_name, is_draft) stripping a trailing '_Draft' suffix."""
    if name.lower().endswith("_draft"):
        return name[: -len("_draft")], 1
    return name, 0


def reset_db(path: str) -> None:
    """Delete the database file so open_db recreates it from scratch."""
    p = Path(path)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(p) + suffix) if suffix else p
        if candidate.exists():
            candidate.unlink()
    print(f"Database reset: {path}")


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for long-running writes
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _auth_header(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _get(url: str, headers: dict, timeout: int = 30) -> dict | list:
    """Perform a GET request and return parsed JSON. Raises on HTTP errors."""
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_with_retry(
    url: str,
    headers: dict,
    max_retries: int,
    retry_wait: float,
    label: str = "",
) -> dict | list | None:
    """
    Fetch a URL with exponential backoff.
    Returns None if all retries are exhausted.
    """
    for attempt in range(max_retries + 1):
        try:
            return _get(url, headers)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if attempt == max_retries:
                print(f"    FAIL [{label}] HTTP {status} after {attempt+1} attempt(s)")
                return None
            wait = retry_wait * (2 ** attempt)
            print(f"    WARN [{label}] HTTP {status} — retrying in {wait:.0f}s "
                  f"(attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
        except requests.exceptions.RequestException as exc:
            if attempt == max_retries:
                print(f"    FAIL [{label}] {exc} after {attempt+1} attempt(s)")
                return None
            wait = retry_wait * (2 ** attempt)
            print(f"    WARN [{label}] {exc} — retrying in {wait:.0f}s "
                  f"(attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
    return None


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_phage(conn: sqlite3.Connection, dataset: str, genome: dict) -> None:
    raw_name = genome.get("phagename", "")
    clean_name, is_draft = strip_draft(raw_name)
    conn.execute(
        """
        INSERT INTO phages
            (phage_id, dataset, phagename, cluster, subcluster,
             cluster_subcluster, genome_length, is_draft, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (phage_id, dataset) DO UPDATE SET
            phagename          = excluded.phagename,
            cluster            = excluded.cluster,
            subcluster         = excluded.subcluster,
            cluster_subcluster = excluded.cluster_subcluster,
            genome_length      = excluded.genome_length,
            is_draft           = excluded.is_draft,
            scraped_at         = excluded.scraped_at
        """,
        (
            clean_name,
            dataset,
            clean_name,
            genome.get("cluster", ""),
            genome.get("subcluster", ""),
            genome.get("clusterSubcluster", ""),
            genome.get("genomelength"),
            is_draft,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def upsert_genes(conn: sqlite3.Connection, dataset: str, genes: list, is_draft: int) -> int:
    rows = []
    for g in genes:
        # The API's phageID field omits '_Draft'; strip_draft is a no-op here
        # but keeps things consistent if the API ever changes.
        phage_id, _ = strip_draft(g.get("phageID", ""))
        rows.append((
            g.get("geneID", ""),
            phage_id,
            dataset,
            g.get("name", ""),
            g.get("accession", ""),
            g.get("start"),
            g.get("stop"),
            g.get("midpoint"),
            g.get("gap"),
            g.get("direction", ""),
            g.get("phamColor", ""),
            g.get("phamName", ""),
            g.get("translation", ""),
            g.get("genefunction", ""),
            g.get("LocusTag", ""),
            g.get("domainCount"),
            g.get("tmDomainCount"),
            is_draft,
        ))

    conn.executemany(
        """
        INSERT INTO genes
            (gene_id, phage_id, dataset, name, accession, start, stop,
             midpoint, gap, direction, pham_color, pham_name, translation,
             gene_function, locus_tag, domain_count, tm_domain_count, is_draft)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (gene_id, dataset) DO UPDATE SET
            name            = excluded.name,
            accession       = excluded.accession,
            start           = excluded.start,
            stop            = excluded.stop,
            midpoint        = excluded.midpoint,
            gap             = excluded.gap,
            direction       = excluded.direction,
            pham_color      = excluded.pham_color,
            pham_name       = excluded.pham_name,
            translation     = excluded.translation,
            gene_function   = excluded.gene_function,
            locus_tag       = excluded.locus_tag,
            domain_count    = excluded.domain_count,
            tm_domain_count = excluded.tm_domain_count,
            is_draft        = excluded.is_draft
        """,
        rows,
    )
    return len(rows)


def set_scrape_status(
    conn: sqlite3.Connection,
    phage_id: str,
    dataset: str,
    status: str,
    attempts: int,
    error_msg: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO scrape_log (phage_id, dataset, status, attempts, last_attempt, error_msg)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (phage_id, dataset) DO UPDATE SET
            status       = excluded.status,
            attempts     = excluded.attempts,
            last_attempt = excluded.last_attempt,
            error_msg    = excluded.error_msg
        """,
        (phage_id, dataset, status, attempts,
         datetime.now(timezone.utc).isoformat(), error_msg),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Core scrape logic
# ---------------------------------------------------------------------------

def get_all_phage_names(
    dataset: str, headers: dict, max_retries: int, retry_wait: float
) -> list[tuple[str, int]]:
    """
    Fetch the lightweight /genomes list.
    Returns a list of (clean_phage_id, is_draft) tuples with '_Draft' stripped.
    """
    url = f"{BASE_URL}/{dataset}/genomes"
    print(f"Fetching genome list from {url} ...")
    data = fetch_with_retry(url, headers, max_retries, retry_wait, label="genomes")
    if data is None:
        sys.exit("ERROR: Could not fetch genome list. Check credentials and dataset name.")
    if not isinstance(data, list):
        sys.exit(f"ERROR: Expected a list from /genomes, got: {type(data)}")

    phages = [
        strip_draft(g["phagename"])
        for g in data
        if g.get("phagename")
    ]
    print(f"Found {len(phages)} phages in dataset '{dataset}'.")
    return phages


def seed_scrape_log(
    conn: sqlite3.Connection, dataset: str, phages: list[tuple[str, int]]
) -> None:
    """
    Insert 'pending' rows for any phage not yet in scrape_log.
    Already-present rows (any status) are left untouched.
    """
    conn.executemany(
        """
        INSERT OR IGNORE INTO scrape_log (phage_id, dataset, is_draft, status, attempts)
        VALUES (?, ?, ?, 'pending', 0)
        """,
        [(name, dataset, is_draft) for name, is_draft in phages],
    )
    conn.commit()


def pending_phages(conn: sqlite3.Connection, dataset: str) -> list[tuple[str, int]]:
    """Return (phage_id, is_draft) for all phages not yet successfully scraped."""
    rows = conn.execute(
        "SELECT phage_id, is_draft FROM scrape_log"
        " WHERE dataset = ? AND status != 'success'"
        " ORDER BY phage_id",
        (dataset,),
    ).fetchall()
    return [(r["phage_id"], r["is_draft"]) for r in rows]


def scrape_dataset(
    conn: sqlite3.Connection,
    dataset: str,
    headers: dict,
    delay: float,
    retry_wait: float,
    max_retries: int,
) -> None:
    # --- Step 1: get phage list and seed the log ---
    phages = get_all_phage_names(dataset, headers, max_retries, retry_wait)
    seed_scrape_log(conn, dataset, phages)

    todo = pending_phages(conn, dataset)
    total = len(phages)
    already_done = total - len(todo)

    if already_done:
        print(f"Resuming: {already_done} already scraped, {len(todo)} remaining.")
    if not todo:
        print("Nothing to do — all phages already scraped successfully.")
        return

    # --- Step 2: fetch each genome ---
    succeeded = 0
    failed = 0

    for i, (phage_id, is_draft) in enumerate(todo, start=1):
        pct = (already_done + i) / total * 100
        print(f"[{already_done + i}/{total}  {pct:.1f}%]  {phage_id}")

        # Reconstruct the API name — the endpoint uses the original name with _Draft.
        api_name = phage_id + "_Draft" if is_draft else phage_id

        # Look up current attempt count
        row = conn.execute(
            "SELECT attempts FROM scrape_log WHERE phage_id = ? AND dataset = ?",
            (phage_id, dataset),
        ).fetchone()
        attempts_so_far = row["attempts"] if row else 0

        url = f"{BASE_URL}/{dataset}/genome/{api_name}"
        genome = fetch_with_retry(
            url, headers, max_retries, retry_wait, label=phage_id
        )

        if genome is None:
            failed += 1
            set_scrape_status(
                conn, phage_id, dataset, "failed",
                attempts_so_far + max_retries + 1,
                error_msg="Exhausted retries",
            )
        else:
            genes = genome.get("genes", [])
            upsert_phage(conn, dataset, genome)
            n_genes = upsert_genes(conn, dataset, genes, is_draft)
            conn.commit()
            succeeded += 1
            set_scrape_status(
                conn, phage_id, dataset, "success",
                attempts_so_far + 1,
            )
            print(f"    OK  {n_genes} genes stored.")

        # Be kind to the API — always sleep, even after failures
        if i < len(todo):
            time.sleep(delay)

    # --- Step 3: summary ---
    print()
    print("=" * 50)
    print(f"Done.  Succeeded: {succeeded}   Failed: {failed}")
    if failed:
        failed_rows = conn.execute(
            "SELECT phage_id, error_msg FROM scrape_log "
            "WHERE dataset = ? AND status = 'failed'",
            (dataset,),
        ).fetchall()
        print("Failed phages (re-run the script to retry):")
        for r in failed_rows:
            print(f"  {r['phage_id']}  — {r['error_msg']}")
    print("=" * 50)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Phamerator genomes + genes into a SQLite database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset", default="Actino_Draft",
        help="Phamerator dataset name (e.g. Actino_Draft)",
    )
    parser.add_argument(
        "--output", default="phamerator.sqlite",
        help="Path to the output SQLite file",
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Seconds to sleep between successful requests",
    )
    parser.add_argument(
        "--retry-wait", type=float, default=5.0,
        help="Base wait in seconds before retrying a failed request (doubles each attempt)",
    )
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="Maximum retry attempts per phage before marking it failed",
    )
    parser.add_argument(
        "--api-key",
        help="Phamerator API key (overrides PHAMERATOR_API_KEY env var)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help=(
            "Drop and recreate the database before scraping. "
            "Use this when Phamerator has pushed a pham renumbering update."
        ),
    )
    return parser.parse_args()


_KEYCHAIN_SERVICE = "phamerator_api_key"
_KEYCHAIN_ACCOUNT = "phamerator"


def _keychain_api_key() -> str:
    """Return the Phamerator API key from macOS Keychain, or '' if unavailable."""
    import subprocess
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-a", _KEYCHAIN_ACCOUNT, "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def main() -> None:
    args = parse_args()

    # API key: CLI flag > env var > macOS Keychain
    api_key = args.api_key or os.environ.get("PHAMERATOR_API_KEY", "")

    if not api_key:
        api_key = _keychain_api_key()
        if api_key:
            print("Credentials: using API key from macOS Keychain.")

    if not api_key:
        sys.exit(
            "ERROR: Phamerator API key not found.\n"
            "Resolution order tried: --api-key flag, PHAMERATOR_API_KEY env var,\n"
            f"macOS Keychain (service '{_KEYCHAIN_SERVICE}', account '{_KEYCHAIN_ACCOUNT}').\n\n"
            "To store your key in Keychain (recommended on macOS):\n"
            f"  security add-generic-password -a \"{_KEYCHAIN_ACCOUNT}\" -s \"{_KEYCHAIN_SERVICE}\" -w\n\n"
            "Or set PHAMERATOR_API_KEY in your .env file."
        )

    if args.force:
        print("--force: dropping existing database for a full re-scrape.")
        print("This is required after a Phamerator pham renumbering update.")
        reset_db(args.output)
        print()

    print(f"Dataset : {args.dataset}")
    print(f"Output  : {args.output}")
    print(f"Delay   : {args.delay}s between requests")
    print(f"Retries : up to {args.max_retries} (base wait {args.retry_wait}s, doubling)")
    print()

    headers = _auth_header(api_key)
    conn = open_db(args.output)

    try:
        scrape_dataset(
            conn,
            dataset=args.dataset,
            headers=headers,
            delay=args.delay,
            retry_wait=args.retry_wait,
            max_retries=args.max_retries,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
