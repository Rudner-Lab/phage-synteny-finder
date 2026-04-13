#!/usr/bin/env python3
"""
generate_cluster_reports.py
---------------------------
Generates one HTML orpham-synteny report per cluster in the dataset, saving
each to the output directory.  It also always writes a combined CSV of every
passing orpham across all clusters (``all_orpham_report.csv``).

For each cluster, the pattern ``<cluster>*`` is used so that all phages
in the cluster — across every subcluster and unsubclustered — are included
in a single report.

Usage
-----
    .venv/bin/python scripts/generate_cluster_reports.py
    .venv/bin/python scripts/generate_cluster_reports.py --dataset Actino_Draft
    .venv/bin/python scripts/generate_cluster_reports.py --db phamerator.sqlite --out-dir output
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing the package as an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orpham_report.db import open_db
from orpham_report.cli import main as report_main


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one HTML orpham synteny report per cluster, plus a combined CSV.",
    )
    parser.add_argument("--dataset", default="Actino_Draft", help="Dataset name in the database")
    parser.add_argument("--db",      default="phamerator.sqlite", help="Path to the SQLite database")
    parser.add_argument("--out-dir", default="output", help="Directory for output files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        sys.exit(f"ERROR: Database not found: {db_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = open_db(db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT cluster FROM phages
            WHERE dataset = ? AND cluster IS NOT NULL AND cluster != ''
            ORDER BY cluster
            """,
            (args.dataset,),
        ).fetchall()
    finally:
        conn.close()

    clusters = [r["cluster"] for r in rows]
    if not clusters:
        sys.exit(f"ERROR: No clusters found in dataset '{args.dataset}'.")

    print(f"Dataset : {args.dataset}")
    print(f"Clusters: {len(clusters)}")
    print(f"Out dir : {out_dir}")
    print()

    failed: list[str] = []
    for i, cluster in enumerate(clusters, 1):
        out_file = out_dir / f"{cluster}_orpham_report.html"
        print(f"[{i}/{len(clusters)}] Cluster {cluster} → {out_file.name}")
        try:
            report_main([
                "--cluster", f"{cluster}*",
                "--dataset", args.dataset,
                "--db",      str(db_path),
                "--out",     str(out_file),
            ])
        except SystemExit as e:
            print(f"  WARNING: cluster {cluster} failed — {e}")
            failed.append(cluster)
        print()

    # Always produce a combined CSV of every passing orpham across all clusters.
    all_csv = out_dir / "all_orpham_report.csv"
    print(f"Combined CSV → {all_csv.name}")
    try:
        report_main([
            "--cluster", "all",
            "--dataset", args.dataset,
            "--db",      str(db_path),
            "--format",  "csv",
            "--out",     str(all_csv),
        ])
    except SystemExit as e:
        print(f"  WARNING: combined CSV failed — {e}")
        failed.append("all (CSV)")
    print()

    if failed:
        print(f"Finished with {len(failed)} failure(s): {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"All {len(clusters)} cluster reports + combined CSV written to {out_dir}/")


if __name__ == "__main__":
    main()
