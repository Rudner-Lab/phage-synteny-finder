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
    .venv/bin/python scrape_phamerator.py --dataset Actino_Draft --output phamerator.sqlite

Credentials are read from environment variables (or a .env file if
python-dotenv is installed). For better security on macOS, store the password
in Keychain and pass it to --password at runtime:

    security add-generic-password -a "you@example.com" -s "phamerator_password" -w
    .venv/bin/python scrape_phamerator.py \
      --email "you@example.com" \
      --password "$(security find-generic-password -a "you@example.com" -s "phamerator_password" -w)"

If you prefer .env, keep only non-sensitive values there:

    PHAMERATOR_EMAIL=you@example.com
    PHAMERATOR_PASSWORD=yourpassword

Rate-limiting behaviour (all configurable via CLI flags)
---------------------------------------------------------
  --delay       Seconds to sleep between successful requests  (default: 2.0)
  --retry-wait  Base wait in seconds before retrying a failed request (default: 5.0)
  --max-retries Maximum number of retry attempts per phage    (default: 3)

The script is fully resumable: re-running it will skip any phage already
marked 'success' in the scrape_log table.
"""

import argparse
import base64
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
    PRIMARY KEY (gene_id, dataset)
);

CREATE INDEX IF NOT EXISTS idx_genes_phage    ON genes (phage_id, dataset);
CREATE INDEX IF NOT EXISTS idx_genes_pham     ON genes (pham_name);

CREATE TABLE IF NOT EXISTS scrape_log (
    phage_id     TEXT NOT NULL,
    dataset      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT,
    error_msg    TEXT,
    PRIMARY KEY (phage_id, dataset)
);
"""


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

def _auth_header(email: str, password: str) -> dict:
    token = base64.b64encode(f"{email}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


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
    conn.execute(
        """
        INSERT INTO phages
            (phage_id, dataset, phagename, cluster, subcluster,
             cluster_subcluster, genome_length, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (phage_id, dataset) DO UPDATE SET
            phagename          = excluded.phagename,
            cluster            = excluded.cluster,
            subcluster         = excluded.subcluster,
            cluster_subcluster = excluded.cluster_subcluster,
            genome_length      = excluded.genome_length,
            scraped_at         = excluded.scraped_at
        """,
        (
            genome.get("phagename", ""),
            dataset,
            genome.get("phagename", ""),
            genome.get("cluster", ""),
            genome.get("subcluster", ""),
            genome.get("clusterSubcluster", ""),
            genome.get("genomelength"),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def upsert_genes(conn: sqlite3.Connection, dataset: str, genes: list) -> int:
    rows = []
    for g in genes:
        rows.append((
            g.get("geneID", ""),
            g.get("phageID", ""),
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
        ))

    conn.executemany(
        """
        INSERT INTO genes
            (gene_id, phage_id, dataset, name, accession, start, stop,
             midpoint, gap, direction, pham_color, pham_name, translation,
             gene_function, locus_tag, domain_count, tm_domain_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            tm_domain_count = excluded.tm_domain_count
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
) -> list[str]:
    """Fetch the lightweight /genomes list and return all phage names."""
    url = f"{BASE_URL}/{dataset}/genomes"
    print(f"Fetching genome list from {url} ...")
    data = fetch_with_retry(url, headers, max_retries, retry_wait, label="genomes")
    if data is None:
        sys.exit("ERROR: Could not fetch genome list. Check credentials and dataset name.")
    if not isinstance(data, list):
        sys.exit(f"ERROR: Expected a list from /genomes, got: {type(data)}")

    names = [g["phagename"] for g in data if g.get("phagename")]
    print(f"Found {len(names)} phages in dataset '{dataset}'.")
    return names


def seed_scrape_log(
    conn: sqlite3.Connection, dataset: str, phage_names: list[str]
) -> None:
    """
    Insert 'pending' rows for any phage not yet in scrape_log.
    Already-present rows (any status) are left untouched.
    """
    conn.executemany(
        """
        INSERT OR IGNORE INTO scrape_log (phage_id, dataset, status, attempts)
        VALUES (?, ?, 'pending', 0)
        """,
        [(name, dataset) for name in phage_names],
    )
    conn.commit()


def pending_phages(conn: sqlite3.Connection, dataset: str) -> list[str]:
    rows = conn.execute(
        "SELECT phage_id FROM scrape_log WHERE dataset = ? AND status != 'success' "
        "ORDER BY phage_id",
        (dataset,),
    ).fetchall()
    return [r["phage_id"] for r in rows]


def scrape_dataset(
    conn: sqlite3.Connection,
    dataset: str,
    headers: dict,
    delay: float,
    retry_wait: float,
    max_retries: int,
) -> None:
    # --- Step 1: get phage list and seed the log ---
    phage_names = get_all_phage_names(dataset, headers, max_retries, retry_wait)
    seed_scrape_log(conn, dataset, phage_names)

    todo = pending_phages(conn, dataset)
    total = len(phage_names)
    already_done = total - len(todo)

    if already_done:
        print(f"Resuming: {already_done} already scraped, {len(todo)} remaining.")
    if not todo:
        print("Nothing to do — all phages already scraped successfully.")
        return

    # --- Step 2: fetch each genome ---
    succeeded = 0
    failed = 0

    for i, phage_id in enumerate(todo, start=1):
        pct = (already_done + i) / total * 100
        print(f"[{already_done + i}/{total}  {pct:.1f}%]  {phage_id}")

        # Look up current attempt count
        row = conn.execute(
            "SELECT attempts FROM scrape_log WHERE phage_id = ? AND dataset = ?",
            (phage_id, dataset),
        ).fetchone()
        attempts_so_far = row["attempts"] if row else 0

        url = f"{BASE_URL}/{dataset}/genome/{phage_id}"
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
            n_genes = upsert_genes(conn, dataset, genes)
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
        "--email",
        help="Phamerator login email (overrides PHAMERATOR_EMAIL env var)",
    )
    parser.add_argument(
        "--password",
        help="Phamerator login password (overrides PHAMERATOR_PASSWORD env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Credentials: CLI flag > env var
    email = args.email or os.environ.get("PHAMERATOR_EMAIL", "")
    password = args.password or os.environ.get("PHAMERATOR_PASSWORD", "")

    if not email or not password:
        sys.exit(
            "ERROR: Phamerator credentials not found.\n"
            "Set PHAMERATOR_EMAIL and PHAMERATOR_PASSWORD environment variables,\n"
            "create a .env file with those keys, or pass --email / --password.\n"
            "On macOS, prefer storing PHAMERATOR_PASSWORD in Keychain and\n"
            "passing it to --password at runtime instead of storing plaintext secrets."
        )

    print(f"Dataset : {args.dataset}")
    print(f"Output  : {args.output}")
    print(f"Delay   : {args.delay}s between requests")
    print(f"Retries : up to {args.max_retries} (base wait {args.retry_wait}s, doubling)")
    print()

    headers = _auth_header(email, password)
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
