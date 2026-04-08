"""
db.py — database access helpers for the orpham synteny report.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_phage_id(phage_id: str) -> str:
    """Lowercase the phage_id for comparison."""
    return phage_id.strip().lower()


def sql_norm_phage(col: str = "phage_id") -> str:
    """SQL expression that normalises a phage_id for same-phage comparison."""
    return f"lower({col})"


def resolve_phage_id(
    conn: sqlite3.Connection, phage_name: str, dataset: str
) -> str | None:
    """Return the canonical phage_id for *phage_name* in *dataset*, or None."""
    name = normalize_phage_id(phage_name)
    row = conn.execute(
        "SELECT phage_id FROM phages WHERE lower(phage_id) = ? AND dataset = ?",
        (name, dataset),
    ).fetchone()
    return row["phage_id"] if row else None


def resolve_cluster_phages(
    conn: sqlite3.Connection,
    patterns: list[str],
    dataset: str,
) -> list[tuple[str, str, str]]:
    """Return (phage_id, cluster, cluster_subcluster) rows matching *patterns*.

    Pattern rules:
      - "all"  → every phage in the dataset
      - "F"    → phages whose *cluster* column is exactly "F" (all subclusters)
      - "F1"   → phages whose *cluster_subcluster* is exactly "F1"

    Matching is case-insensitive. Multiple patterns are OR'd together.
    """
    all_rows = conn.execute(
        """
        SELECT phage_id, cluster, cluster_subcluster
        FROM phages WHERE dataset = ?
        ORDER BY cluster, cluster_subcluster, phage_id
        """,
        (dataset,),
    ).fetchall()

    if any(p.lower() == "all" for p in patterns):
        return [(r["phage_id"], r["cluster"], r["cluster_subcluster"]) for r in all_rows]

    matched: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    pat_lower = [p.lower() for p in patterns]

    for row in all_rows:
        phage_id = row["phage_id"]
        if phage_id in seen:
            continue
        cluster = row["cluster"] or ""
        cs = row["cluster_subcluster"] or ""

        for pat in pat_lower:
            if pat == cluster.lower() or pat == cs.lower():
                matched.append((phage_id, cluster, cs))
                seen.add(phage_id)
                break

    return matched
