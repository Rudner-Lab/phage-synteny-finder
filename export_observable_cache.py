#!/usr/bin/env python3
"""
export_observable_cache.py
--------------------------
Export scraped Phamerator SQLite data into Observable-friendly JSON shards.

This produces a self-contained cache directory that can be uploaded as
Observable File Attachments. Data is split into small shard files so notebooks
can lazy-load only what they need.

Output layout
-------------
<out_dir>/
  meta.json
  genomes/
    genomes_a.json
    genomes_b.json
    ...
  phams/
    phams_0.json
    phams_1.json
    ...

Bucket rule
-----------
Both genome and pham shards are bucketed by first character:
  - a-z and 0-9 keep their own bucket
  - everything else goes to "other"

Usage
-----
  .venv/bin/python export_observable_cache.py \
    --db phamerator.sqlite \
    --dataset Actino_Draft \
    --out-dir observable_cache
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export scraped Phamerator SQLite data to sharded JSON for Observable.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", default="phamerator.sqlite", help="Path to SQLite database")
    parser.add_argument("--dataset", default="Actino_Draft", help="Dataset to export")
    parser.add_argument(
        "--out-dir",
        default="observable_cache",
        help="Output directory for cache JSON files",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write pretty-printed JSON (larger files, easier to inspect)",
    )
    return parser.parse_args()


def normalize_phage_name(name: str | None) -> str:
    if not name:
        return ""
    return re.sub(r"_draft$", "", name.strip(), flags=re.IGNORECASE).lower()


def bucket_for(value: str | None) -> str:
    if not value:
        return "other"
    c = value.strip().lower()[:1]
    if c and c.isalnum():
        return c
    return "other"


def json_dump(path: Path, payload: object, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        if pretty:
            json.dump(payload, f, indent=2, sort_keys=True)
        else:
            json.dump(payload, f, separators=(",", ":"), sort_keys=True)


def to_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_gene_obj(row: sqlite3.Row) -> dict:
    return {
        "geneID": row["gene_id"],
        "phageID": row["phage_id"],
        "name": row["name"],
        "accession": row["accession"],
        "start": to_int(row["start"]),
        "stop": to_int(row["stop"]),
        "midpoint": row["midpoint"],
        "gap": to_int(row["gap"]),
        "direction": row["direction"],
        "phamColor": row["pham_color"],
        "phamName": row["pham_name"],
        "translation": row["translation"],
        "genefunction": row["gene_function"],
        "LocusTag": row["locus_tag"],
        "domainCount": to_int(row["domain_count"]),
        "tmDomainCount": to_int(row["tm_domain_count"]),
    }


def main() -> None:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not db_path.exists():
        raise SystemExit(f"ERROR: SQLite file not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Validate dataset exists.
        datasets = {
            r["dataset"]
            for r in conn.execute("SELECT DISTINCT dataset FROM phages").fetchall()
            if r["dataset"]
        }
        if args.dataset not in datasets:
            options = ", ".join(sorted(datasets)) if datasets else "(none)"
            raise SystemExit(
                f"ERROR: Dataset '{args.dataset}' not found in DB. Available: {options}"
            )

        phage_rows = conn.execute(
            """
            SELECT phage_id, phagename, cluster, subcluster, cluster_subcluster, genome_length
            FROM phages
            WHERE dataset = ?
            ORDER BY phage_id
            """,
            (args.dataset,),
        ).fetchall()

        gene_rows = conn.execute(
            """
            SELECT gene_id, phage_id, name, accession, start, stop, midpoint, gap,
                   direction, pham_color, pham_name, translation, gene_function,
                   locus_tag, domain_count, tm_domain_count
            FROM genes
            WHERE dataset = ?
            ORDER BY phage_id, stop, start, name
            """,
            (args.dataset,),
        ).fetchall()

        genes_by_phage: dict[str, list[dict]] = defaultdict(list)
        genes_by_pham: dict[str, list[dict]] = defaultdict(list)

        for row in gene_rows:
            gene_obj = build_gene_obj(row)
            genes_by_phage[row["phage_id"]].append(gene_obj)
            pham_name = row["pham_name"]
            if pham_name:
                genes_by_pham[str(pham_name)].append(gene_obj)

        genome_shards: dict[str, dict] = defaultdict(dict)
        for row in phage_rows:
            phage_id = row["phage_id"]
            key = normalize_phage_name(phage_id or row["phagename"])
            if not key:
                continue
            genome_obj = {
                "phageID": phage_id,
                "phagename": row["phagename"] or phage_id,
                "cluster": row["cluster"],
                "subcluster": row["subcluster"],
                "clusterSubcluster": row["cluster_subcluster"],
                "genomelength": to_int(row["genome_length"]),
                "genes": genes_by_phage.get(phage_id, []),
            }
            bucket = bucket_for(key)
            genome_shards[bucket][key] = genome_obj

        pham_shards: dict[str, dict] = defaultdict(dict)
        for pham_name, members in genes_by_pham.items():
            bucket = bucket_for(pham_name)
            members_sorted = sorted(
                members,
                key=lambda g: (
                    (g.get("phageID") or "").lower(),
                    to_int(g.get("name")) if str(g.get("name", "")).isdigit() else 10**12,
                    str(g.get("name") or ""),
                ),
            )
            pham_shards[bucket][pham_name] = members_sorted

        genomes_dir = out_dir / "genomes"
        phams_dir = out_dir / "phams"

        genome_files = []
        for bucket in sorted(genome_shards.keys()):
            payload = genome_shards[bucket]
            if not payload:
                continue
            rel = Path("genomes") / f"genomes_{bucket}.json"
            json_dump(out_dir / rel, payload, args.pretty)
            genome_files.append(str(rel))

        pham_files = []
        for bucket in sorted(pham_shards.keys()):
            payload = pham_shards[bucket]
            if not payload:
                continue
            rel = Path("phams") / f"phams_{bucket}.json"
            json_dump(out_dir / rel, payload, args.pretty)
            pham_files.append(str(rel))

        meta = {
            "schemaVersion": 1,
            "dataset": args.dataset,
            "exportedAt": datetime.now(timezone.utc).isoformat(),
            "sourceDb": str(db_path),
            "counts": {
                "phages": len(phage_rows),
                "genes": len(gene_rows),
                "phams": len(genes_by_pham),
                "genomeShards": len(genome_files),
                "phamShards": len(pham_files),
            },
            "lookup": {
                "normalizePhageName": "lowercase and trim trailing _Draft",
                "bucketRule": "first character a-z/0-9 else 'other'",
            },
            "files": {
                "genomeShards": genome_files,
                "phamShards": pham_files,
            },
        }

        json_dump(out_dir / "meta.json", meta, args.pretty)

        print(f"Export complete: {out_dir}")
        print(f"  Dataset: {args.dataset}")
        print(f"  Phages:  {len(phage_rows)}")
        print(f"  Genes:   {len(gene_rows)}")
        print(f"  Phams:   {len(genes_by_pham)}")
        print(f"  Genome shard files: {len(genome_files)}")
        print(f"  Pham shard files:   {len(pham_files)}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
