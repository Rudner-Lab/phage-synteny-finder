#!/usr/bin/env python3
"""
migrate_phage_ids.py
--------------------
One-time migration: strip the '_Draft' suffix from phage_id / phagename in
the database and store draft status in a proper boolean (INTEGER 0/1) column
instead.

What this changes
-----------------
phages     Add is_draft column; normalize phage_id and phagename.
genes      Add is_draft column; populate from the phages table (genes.phage_id
           was already stored without '_Draft' by the scraper, so no ID change).
scrape_log Add is_draft column; normalize phage_id.

The migration is idempotent: running it on an already-migrated database is
safe (the ALTER TABLE will fail gracefully if the column already exists, and
the UPDATE will touch 0 rows because no phage_id ends in '_draft' any more).

Usage
-----
  .venv/bin/python migrate_phage_ids.py --db phamerator.sqlite
"""

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Migrate phage_id/phagename to strip _Draft and add is_draft column.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--db", default="phamerator.sqlite", help="SQLite database path")
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip making a .bak copy of the database before migrating",
    )
    return p.parse_args()


def add_column_if_missing(conn: sqlite3.Connection, table: str, col_def: str) -> bool:
    """ALTER TABLE … ADD COLUMN if the column doesn't exist yet. Returns True if added."""
    col_name = col_def.split()[0]
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if col_name in existing:
        print(f"  {table}.{col_name} already exists — skipping ALTER TABLE.")
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    print(f"  Added {table}.{col_name}.")
    return True


def run_migration(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")  # we're restructuring, no FK cascades needed

    with conn:  # single transaction for atomicity
        # ── phages ────────────────────────────────────────────────────────────
        print("phages:")
        add_column_if_missing(conn, "phages", "is_draft INTEGER NOT NULL DEFAULT 0")

        n = conn.execute(
            "UPDATE phages"
            " SET is_draft = CASE WHEN lower(phage_id) LIKE '%_draft' THEN 1 ELSE 0 END"
            " WHERE is_draft != (CASE WHEN lower(phage_id) LIKE '%_draft' THEN 1 ELSE 0 END)"
        ).rowcount
        print(f"  is_draft populated ({n} rows updated).")

        n = conn.execute(
            """
            UPDATE phages
            SET phage_id  = substr(phage_id,  1, length(phage_id)  - 6),
                phagename = CASE WHEN lower(phagename) LIKE '%_draft'
                                 THEN substr(phagename, 1, length(phagename) - 6)
                                 ELSE phagename END
            WHERE is_draft = 1
              AND lower(phage_id) LIKE '%_draft'
            """
        ).rowcount
        print(f"  Stripped '_Draft' from {n} phage_id / phagename values.")

        # ── genes ─────────────────────────────────────────────────────────────
        print("genes:")
        added = add_column_if_missing(conn, "genes", "is_draft INTEGER NOT NULL DEFAULT 0")
        if added:
            # genes.phage_id was already stored without '_Draft' by the scraper,
            # so join directly to the (now-normalised) phages table.
            n = conn.execute(
                """
                UPDATE genes
                SET is_draft = (
                    SELECT p.is_draft FROM phages p
                    WHERE p.phage_id = genes.phage_id AND p.dataset = genes.dataset
                )
                """
            ).rowcount
            print(f"  is_draft populated ({n} gene rows updated).")
        else:
            print("  Skipping is_draft population (column already existed).")

        # ── scrape_log ────────────────────────────────────────────────────────
        print("scrape_log:")
        add_column_if_missing(conn, "scrape_log", "is_draft INTEGER NOT NULL DEFAULT 0")

        n = conn.execute(
            "UPDATE scrape_log"
            " SET is_draft = CASE WHEN lower(phage_id) LIKE '%_draft' THEN 1 ELSE 0 END"
            " WHERE is_draft != (CASE WHEN lower(phage_id) LIKE '%_draft' THEN 1 ELSE 0 END)"
        ).rowcount
        print(f"  is_draft populated ({n} rows updated).")

        n = conn.execute(
            """
            UPDATE scrape_log
            SET phage_id = substr(phage_id, 1, length(phage_id) - 6)
            WHERE is_draft = 1
              AND lower(phage_id) LIKE '%_draft'
            """
        ).rowcount
        print(f"  Stripped '_Draft' from {n} scrape_log phage_id values.")


def verify(conn: sqlite3.Connection) -> None:
    print("\nVerification:")
    for table in ("phages", "genes", "scrape_log"):
        remaining = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE lower(phage_id) LIKE '%_draft'"
        ).fetchone()[0]
        drafts = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE is_draft = 1"
        ).fetchone()[0]
        status = "OK" if remaining == 0 else f"WARN: {remaining} rows still have _Draft suffix"
        print(f"  {table}: {drafts} is_draft=1 rows | {status}")

    # Spot-check: genes and phages should join cleanly now
    mismatched = conn.execute(
        """
        SELECT COUNT(*) FROM genes g
        WHERE NOT EXISTS (
            SELECT 1 FROM phages p
            WHERE p.phage_id = g.phage_id AND p.dataset = g.dataset
        )
        """
    ).fetchone()[0]
    if mismatched == 0:
        print("  genes ↔ phages join: all genes have a matching phage row. OK")
    else:
        print(f"  WARN: {mismatched} gene rows have no matching phage row after migration.")


def main() -> None:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()

    if not db_path.exists():
        raise SystemExit(f"ERROR: Database not found: {db_path}")

    if not args.no_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = db_path.with_suffix(f".{ts}.bak")
        shutil.copy2(db_path, backup)
        print(f"Backup created: {backup}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        run_migration(conn)
        verify(conn)
    finally:
        conn.close()

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
