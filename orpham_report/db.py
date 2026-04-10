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
) -> list[tuple[str, str, str, bool]]:
    """Return (phage_id, cluster, cluster_subcluster, is_draft) rows matching *patterns*.

    Pattern rules:
      - "all"  → every phage in the dataset
      - "F*"   → all phages whose cluster is F (any subcluster or none)
      - "F"    → phages in cluster F with no subcluster assigned
      - "F1"   → phages in subcluster F1 only

    Matching is case-insensitive. Multiple patterns are OR'd together.
    """
    if any(p.lower() == "all" for p in patterns):
        rows = conn.execute(
            """
            SELECT phage_id, cluster, cluster_subcluster, is_draft
            FROM phages WHERE dataset = ?
            ORDER BY cluster, cluster_subcluster, phage_id
            """,
            (dataset,),
        ).fetchall()
        return [(r["phage_id"], r["cluster"], r["cluster_subcluster"], bool(r["is_draft"])) for r in rows]

    # Split patterns into wildcards ("F*") and exact matches ("F" or "F1")
    wildcard_clusters = [p[:-1].lower() for p in patterns if p.endswith("*")]
    exact_patterns    = [p.lower()      for p in patterns if not p.endswith("*")]

    clauses: list[str] = []
    params: list[str]  = [dataset]

    if wildcard_clusters:
        placeholders = ", ".join("?" * len(wildcard_clusters))
        clauses.append(f"lower(cluster) IN ({placeholders})")
        params.extend(wildcard_clusters)

    if exact_patterns:
        placeholders = ", ".join("?" * len(exact_patterns))
        clauses.append(
            f"(lower(cluster_subcluster) IN ({placeholders})"
            f" OR (lower(cluster) IN ({placeholders})"
            f"     AND (cluster_subcluster IS NULL OR cluster_subcluster = '')))"
        )
        params.extend(exact_patterns)
        params.extend(exact_patterns)

    rows = conn.execute(
        f"""
        SELECT phage_id, cluster, cluster_subcluster, is_draft
        FROM phages WHERE dataset = ?
        AND ({" OR ".join(clauses)})
        ORDER BY cluster, cluster_subcluster, phage_id
        """,
        params,
    ).fetchall()

    return [(r["phage_id"], r["cluster"], r["cluster_subcluster"], bool(r["is_draft"])) for r in rows]
