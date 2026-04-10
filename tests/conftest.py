"""
conftest.py — shared pytest fixtures.

The ``db`` fixture builds a minimal in-memory SQLite database that exercises
the report's full pipeline:

Phages (dataset "Test"):
  Alpha   cluster A  subcluster A1  → 5 genes, 1 orpham (gene 3)
  Beta    cluster A  subcluster A1  → 5 genes, shares phams with Alpha
  Zeta    cluster A  no subcluster  → 0 genes (tests unsubclustered "A" pattern)
  Gamma   cluster B  subcluster B   → 4 genes, 1 orpham (gene 2) with informative function
  Delta   cluster B  subcluster B   → 4 genes (pham neighbours of Gamma's orpham)
  Epsilon cluster C  no subcluster  → 0 genes, is_draft=1

Pham membership summary:
  pham_shared_up   – in Alpha genes[1], Beta genes[1]         (non-orpham)
  pham_shared_dn   – in Alpha genes[3], Beta genes[3]         (non-orpham)
  pham_orpham_A    – only in Alpha genes[2]                   (orpham)
  pham_b_up        – in Gamma genes[1], Delta genes[1]        (non-orpham)
  pham_b_dn        – in Gamma genes[3], Delta genes[3]        (non-orpham)
  pham_orpham_B    – only in Gamma genes[2]                   (orpham)
  pham_b_candidate – in Delta genes[2]; function = "lysin A"  (informative hit)
  pham_solo        – only in Gamma genes[0]; no neighbors → no hits

Alpha gene 3 (pham_orpham_A): flanked by pham_shared_up / pham_shared_dn.
  Beta has the same flanking context around gene 3, but its gene 2 is pham_b_candidate
  (function "NKF") → Alpha's orpham will NOT pass the filter.

Gamma gene 3 (pham_orpham_B): flanked by pham_b_up / pham_b_dn.
  Delta carries both flanking phams; its central gene has pham_b_candidate / function "lysin A"
  → Gamma's orpham WILL pass the filter (two-sided hit with informative function).
"""
import sqlite3

import pytest


SCHEMA = """
CREATE TABLE phages (
    phage_id TEXT NOT NULL, dataset TEXT NOT NULL,
    phagename TEXT, cluster TEXT, subcluster TEXT, cluster_subcluster TEXT,
    genome_length INTEGER, is_draft INTEGER NOT NULL DEFAULT 0, scraped_at TEXT,
    PRIMARY KEY (phage_id, dataset)
);
CREATE TABLE genes (
    gene_id TEXT NOT NULL, phage_id TEXT NOT NULL, dataset TEXT NOT NULL,
    name TEXT, accession TEXT, start INTEGER, stop INTEGER,
    midpoint REAL, gap INTEGER, direction TEXT, pham_color TEXT,
    pham_name TEXT, translation TEXT, gene_function TEXT, locus_tag TEXT,
    domain_count INTEGER, tm_domain_count INTEGER,
    is_draft INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (gene_id, dataset)
);
CREATE INDEX idx_genes_phage ON genes (phage_id, dataset);
CREATE INDEX idx_genes_pham  ON genes (pham_name);
"""

DATASET = "Test"


def _gene(gene_id, phage_id, name, start, stop, pham, gene_function="", direction="forward"):
    return (
        gene_id, phage_id, DATASET, str(name), "", start, stop,
        (start + stop) / 2, 0, direction, "#000000", pham,
        "M", gene_function, f"{phage_id}_{name}", 0, 0, 0,
    )


def _phage(phage_id, cluster, subcluster, cs, is_draft=0):
    return (phage_id, DATASET, phage_id, cluster, subcluster, cs, 10000, is_draft, None)


PHAGES = [
    _phage("Alpha",   "A", "1", "A1"),
    _phage("Beta",    "A", "1", "A1"),
    _phage("Zeta",    "A", "",  ""),   # unsubclustered in cluster A → tests bare "A" pattern
    _phage("Gamma",   "B", "",  "B"),
    _phage("Delta",   "B", "",  "B"),
    _phage("Epsilon", "C", "",  "C", is_draft=1),  # draft phage, no genes → empty result
]

# Alpha: genes 1-5, gene 3 is orpham flanked by shared_up (gene 2) and shared_dn (gene 4)
ALPHA_GENES = [
    _gene("A_1", "Alpha", 1,  100,  500, "pham_edge"),
    _gene("A_2", "Alpha", 2,  600, 1000, "pham_shared_up"),
    _gene("A_3", "Alpha", 3, 1100, 1500, "pham_orpham_A"),       # orpham
    _gene("A_4", "Alpha", 4, 1600, 2000, "pham_shared_dn"),
    _gene("A_5", "Alpha", 5, 2100, 2500, "pham_edge"),
]

# Beta: same pham structure as Alpha; central gene (3) has pham_b_candidate but fn="" (NKF)
BETA_GENES = [
    _gene("B_1", "Beta", 1,  100,  500, "pham_edge"),
    _gene("B_2", "Beta", 2,  600, 1000, "pham_shared_up"),
    _gene("B_3", "Beta", 3, 1100, 1500, "pham_b_candidate", ""),  # NKF → won't pass filter
    _gene("B_4", "Beta", 4, 1600, 2000, "pham_shared_dn"),
    _gene("B_5", "Beta", 5, 2100, 2500, "pham_edge"),
]

# Gamma: gene 1 is a solo orpham (no neighbors in DB), gene 2 is orpham with informative hit
GAMMA_GENES = [
    _gene("G_1", "Gamma", 1,  100,  500, "pham_solo"),            # orpham, no useful context
    _gene("G_2", "Gamma", 2,  600, 1000, "pham_b_up"),
    _gene("G_3", "Gamma", 3, 1100, 1500, "pham_orpham_B"),        # orpham with informative hit
    _gene("G_4", "Gamma", 4, 1600, 2000, "pham_b_dn"),
]

# Delta: carries both pham_b_up and pham_b_dn flanking pham_orpham_B context
# Central gene 2 has function "lysin A" → informative two-flank hit
DELTA_GENES = [
    _gene("D_1", "Delta", 1,  100,  500, "pham_b_up"),
    _gene("D_2", "Delta", 2,  600, 1000, "pham_b_candidate", "lysin A"),  # informative
    _gene("D_3", "Delta", 3, 1100, 1500, "pham_b_dn"),
    _gene("D_4", "Delta", 4, 1600, 2000, "pham_edge"),
]

ALL_GENES = ALPHA_GENES + BETA_GENES + GAMMA_GENES + DELTA_GENES


@pytest.fixture
def db():
    """In-memory SQLite connection pre-populated with test data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    conn.executemany(
        "INSERT INTO phages VALUES (?,?,?,?,?,?,?,?,?)", PHAGES
    )
    conn.executemany(
        "INSERT INTO genes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ALL_GENES
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def real_db():
    """Connection to the actual phamerator.sqlite (skipped if file absent)."""
    import os
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "phamerator.sqlite"
    if not db_path.exists():
        pytest.skip("phamerator.sqlite not present")
    from orpham_report.db import open_db
    conn = open_db(db_path)
    yield conn
    conn.close()
