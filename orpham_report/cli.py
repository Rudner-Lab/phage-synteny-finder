"""
cli.py — command-line interface for the orpham synteny report.

Usage examples
--------------
  # Single subcluster
  .venv/bin/python report_orpham_synteny.py --cluster F1

  # Unsubclustered phages in cluster F only
  .venv/bin/python report_orpham_synteny.py --cluster F

  # All phages in cluster F (any subcluster or none)
  .venv/bin/python report_orpham_synteny.py --cluster "F*"

  # Multiple explicit patterns
  .venv/bin/python report_orpham_synteny.py --cluster F1 F2 K1

  # Entire dataset
  .venv/bin/python report_orpham_synteny.py --cluster all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import compute_cluster_results
from .db import open_db, resolve_cluster_phages
from .render import render_html


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an HTML orpham synteny report for one or more phage clusters.\n\n"
            "Cluster patterns:\n"
            "  F*      → all phages in cluster F (any subcluster or none)\n"
            "  F       → phages in cluster F with no subcluster assigned\n"
            "  F1      → phages in subcluster F1 only\n"
            "  all     → every phage in the dataset"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cluster",
        nargs="+",
        required=True,
        metavar="PATTERN",
        help='Cluster/subcluster pattern(s). Use "all" for the entire dataset.',
    )
    parser.add_argument("--dataset", default="Actino_Draft", help="Dataset name")
    parser.add_argument("--db",      default="phamerator.sqlite", help="SQLite database path")
    parser.add_argument(
        "--out", default=None,
        help="Output HTML file (default: <pattern>_orpham_report.html)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        sys.exit(f"ERROR: Database not found: {db_path}")

    patterns = args.cluster
    out_stem = "_".join(patterns).replace("*", "x").replace(" ", "_")
    out_path = Path(
        args.out or f"{out_stem}_orpham_report.html"
    ).expanduser().resolve()

    conn = open_db(db_path)
    try:
        phage_rows = resolve_cluster_phages(conn, patterns, args.dataset)
        if not phage_rows:
            sys.exit(
                f"ERROR: No phages found for pattern(s) {patterns!r} "
                f"in dataset '{args.dataset}'.\n"
                "Use --cluster all to report on every phage."
            )

        print(f"Dataset  : {args.dataset}")
        print(f"Patterns : {', '.join(patterns)}")
        print(f"Phages   : {len(phage_rows)}")
        print(f"Output   : {out_path}")
        print()

        phage_meta = {pid: (cl, cs) for pid, cl, cs in phage_rows}
        phage_results: list[tuple[str, str, str, list, dict]] = []
        total = len(phage_rows)
        done  = [0]

        def _on_done(phage_id: str, orpham_results: list, summary: dict) -> None:
            done[0] += 1
            cl, cs = phage_meta[phage_id]
            n = summary["with_informative"]
            print(
                f"  [{done[0]}/{total}] {phage_id} ({cs or cl})"
                f"  → {n} result{'s' if n != 1 else ''}"
            )
            phage_results.append((phage_id, cl, cs, orpham_results, summary))

        compute_cluster_results(
            conn,
            [pid for pid, _, _ in phage_rows],
            args.dataset,
            on_phage_done=_on_done,
        )

        print()
        html = render_html(phage_results, args.dataset, patterns)
        out_path.write_text(html, encoding="utf-8")
        print(f"Report written to: {out_path}")

    finally:
        conn.close()
