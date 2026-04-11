"""
conftest.py — shared pytest fixtures.

The ``db`` fixture builds a minimal in-memory SQLite database that exercises
the report's full pipeline:

Phages (dataset "Test"):
  Alpha   cluster A  subcluster A1              → 5 genes, 1 orpham (gene 3)
  Beta    cluster A  subcluster A1              → 5 genes, shares phams with Alpha
  Zeta    cluster A  no subcluster              → 0 genes (tests bare "A" pattern)
  Gamma   cluster B  subcluster B               → 4 genes, 1 orpham (gene 3) with informative hit
  Delta   cluster B  subcluster B               → 4 genes (two-sided candidate for Gamma)
  Epsilon cluster C  no subcluster  is_draft=1  → 0 genes, empty result
  Iota    cluster D  subcluster D1              → 3 genes, 1 orpham (gene 2) — chimeric evidence
  Eta     cluster D  subcluster D1              → 3 genes (up-only candidate for Iota)
  Theta   cluster D  subcluster D1              → 3 genes (dn-only candidate for Iota)
  Kappa   cluster E  subcluster E1  is_draft=1  → 3 genes, 1 orpham (gene 2, reverse strand)
  Lambda  cluster E  subcluster E1              → 3 genes (two-sided candidate for Kappa)
  Mu      cluster F  subcluster F1              → 3 genes, 1 orpham at terminal position (gene 1)
  Nu      cluster F  subcluster F1              → 3 genes (dn-only candidate for Mu, won't pass)

Pham membership summary:
  pham_shared_up   – Alpha[1], Beta[1]              (non-orpham)
  pham_shared_dn   – Alpha[3], Beta[3]              (non-orpham)
  pham_orpham_A    – only Alpha[2]                  (orpham)
  pham_b_up        – Gamma[1], Delta[1]             (non-orpham)
  pham_b_dn        – Gamma[3], Delta[3]             (non-orpham)
  pham_orpham_B    – only Gamma[2]                  (orpham)
  pham_b_candidate – Delta[2]; function="lysin A"   (informative two-sided hit for Gamma)
  pham_solo        – only Gamma[0]; no neighbors     (orpham, no hits → filtered)
  pham_conv_up     – Iota[0], Eta[0]                (non-orpham)
  pham_conv_dn     – Iota[2], Theta[2]              (non-orpham)
  pham_orpham_C    – only Iota[1]                   (orpham)
  pham_eta_mid     – only Eta[1]; fn="lysin B"      (up-only hit for Iota)
  pham_theta_mid   – only Theta[1]; fn="lysin B"    (dn-only hit for Iota)
  pham_kappa_up_r  – Kappa[0], Lambda[2]            (non-orpham)
  pham_kappa_dn_r  – Kappa[2], Lambda[0]            (non-orpham)
  pham_orpham_rev  – only Kappa[1], reverse strand  (orpham)
  pham_lambda_mid  – only Lambda[1]; fn="terminase & lysin" (two-sided hit for Kappa)
  pham_mu_dn       – Mu[1], Nu[2]                   (non-orpham)
  pham_orpham_term – only Mu[0]; terminal gene       (orpham, no upstream pham → fails filter)

Case notes:
  Alpha gene 3 (pham_orpham_A): flanked by pham_shared_up / pham_shared_dn.
    Beta has the same flanking context but central gene is NKF → does NOT pass.

  Gamma gene 3 (pham_orpham_B): flanked by pham_b_up / pham_b_dn.
    Delta carries both flanks; central gene = "lysin A" → PASSES (two-sided hit).

  Iota gene 2 (pham_orpham_C): flanked by pham_conv_up / pham_conv_dn.
    Eta has pham_conv_up → up-only hit "lysin B".
    Theta has pham_conv_dn → dn-only hit "lysin B".
    No phage has both flanks → zero two-sided hits, but "lysin B" is in both_fns
    (convergent / chimeric evidence) → PASSES.

  Kappa gene 2 (pham_orpham_rev): reverse-strand orpham.
    For reverse strand at index 1: up_idx=2 (pham_kappa_dn_r), dn_idx=0 (pham_kappa_up_r).
    Lambda[0]=pham_kappa_dn_r, Lambda[2]=pham_kappa_up_r → two-sided hit "terminase & lysin".
    Also exercises HTML escaping of '&' in gene functions. → PASSES.

  Mu gene 1 (pham_orpham_term): first gene in genome, no upstream neighbour.
    ref_up_pham=None → up_fns always empty → both_fns always empty → does NOT pass.
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
    _phage("Epsilon", "C", "",  "C", is_draft=1),  # draft, no genes → empty result
    _phage("Iota",    "D", "1", "D1"),  # orpham with chimeric evidence only
    _phage("Eta",     "D", "1", "D1"),  # up-only candidate for Iota's orpham
    _phage("Theta",   "D", "1", "D1"),  # dn-only candidate for Iota's orpham
    _phage("Kappa",   "E", "1", "E1", is_draft=1),  # draft; reverse-strand orpham
    _phage("Lambda",  "E", "1", "E1"),  # two-sided candidate for Kappa (hit fn contains '&')
    _phage("Mu",      "F", "1", "F1"),  # terminal orpham (no upstream pham) → fails filter
    _phage("Nu",      "F", "1", "F1"),  # dn-only candidate for Mu's orpham
]

# Alpha: gene 3 is orpham flanked by shared_up (gene 2) and shared_dn (gene 4)
ALPHA_GENES = [
    _gene("A_1", "Alpha", 1,  100,  500, "pham_edge"),
    _gene("A_2", "Alpha", 2,  600, 1000, "pham_shared_up"),
    _gene("A_3", "Alpha", 3, 1100, 1500, "pham_orpham_A"),       # orpham
    _gene("A_4", "Alpha", 4, 1600, 2000, "pham_shared_dn"),
    _gene("A_5", "Alpha", 5, 2100, 2500, "pham_edge"),
]

# Beta: same pham structure as Alpha; central gene is NKF → won't pass filter
BETA_GENES = [
    _gene("B_1", "Beta", 1,  100,  500, "pham_edge"),
    _gene("B_2", "Beta", 2,  600, 1000, "pham_shared_up"),
    _gene("B_3", "Beta", 3, 1100, 1500, "pham_b_candidate", ""),  # NKF
    _gene("B_4", "Beta", 4, 1600, 2000, "pham_shared_dn"),
    _gene("B_5", "Beta", 5, 2100, 2500, "pham_edge"),
]

# Gamma: gene 1 is a solo orpham (no neighbors in DB), gene 3 is orpham with informative hit
GAMMA_GENES = [
    _gene("G_1", "Gamma", 1,  100,  500, "pham_solo"),            # orpham, no useful context
    _gene("G_2", "Gamma", 2,  600, 1000, "pham_b_up"),
    _gene("G_3", "Gamma", 3, 1100, 1500, "pham_orpham_B"),        # orpham with informative hit
    _gene("G_4", "Gamma", 4, 1600, 2000, "pham_b_dn"),
]

# Delta: two-sided candidate for Gamma's orpham; central gene = "lysin A"
DELTA_GENES = [
    _gene("D_1", "Delta", 1,  100,  500, "pham_b_up"),
    _gene("D_2", "Delta", 2,  600, 1000, "pham_b_candidate", "lysin A"),  # informative
    _gene("D_3", "Delta", 3, 1100, 1500, "pham_b_dn"),
    _gene("D_4", "Delta", 4, 1600, 2000, "pham_edge"),
]

# Iota: orpham flanked by pham_conv_up / pham_conv_dn — chimeric evidence case
IOTA_GENES = [
    _gene("I_1", "Iota", 1,  100,  500, "pham_conv_up"),
    _gene("I_2", "Iota", 2,  600, 1000, "pham_orpham_C"),        # orpham
    _gene("I_3", "Iota", 3, 1100, 1500, "pham_conv_dn"),
]

# Eta: has pham_conv_up → up-only hit for Iota's orpham (function "lysin B")
ETA_GENES = [
    _gene("E_1", "Eta", 1,  100,  500, "pham_conv_up"),
    _gene("E_2", "Eta", 2,  600, 1000, "pham_eta_mid", "lysin B"),
    _gene("E_3", "Eta", 3, 1100, 1500, "pham_eta_other"),
]

# Theta: has pham_conv_dn → dn-only hit for Iota's orpham (function "lysin B")
THETA_GENES = [
    _gene("T_1", "Theta", 1,  100,  500, "pham_theta_other"),
    _gene("T_2", "Theta", 2,  600, 1000, "pham_theta_mid", "lysin B"),
    _gene("T_3", "Theta", 3, 1100, 1500, "pham_conv_dn"),
]

# Kappa: reverse-strand orpham at gene 2 (index 1).
# For reverse strand at index 1: up_idx=2 (pham_kappa_dn_r), dn_idx=0 (pham_kappa_up_r).
KAPPA_GENES = [
    _gene("K_1", "Kappa", 1,  100,  500, "pham_kappa_up_r"),
    _gene("K_2", "Kappa", 2,  600, 1000, "pham_orpham_rev", "", "reverse"),  # orpham, rev strand
    _gene("K_3", "Kappa", 3, 1100, 1500, "pham_kappa_dn_r"),
]

# Lambda: two-sided candidate for Kappa's orpham.
# Lambda[0]=pham_kappa_dn_r (=ref_up_pham), Lambda[2]=pham_kappa_up_r (=ref_dn_pham).
# Hit gene function contains '&' to exercise HTML escaping.
LAMBDA_GENES = [
    _gene("L_1", "Lambda", 1,  100,  500, "pham_kappa_dn_r"),
    _gene("L_2", "Lambda", 2,  600, 1000, "pham_lambda_mid", "terminase & lysin"),  # informative
    _gene("L_3", "Lambda", 3, 1100, 1500, "pham_kappa_up_r"),
]

# Mu: orpham at gene 1, the first gene in the genome — no upstream neighbour.
# ref_up_pham=None → up_fns always empty → both_fns always empty → fails filter.
MU_GENES = [
    _gene("M_1", "Mu", 1,  100,  500, "pham_orpham_term"),       # orpham, terminal
    _gene("M_2", "Mu", 2,  600, 1000, "pham_mu_dn"),
    _gene("M_3", "Mu", 3, 1100, 1500, "pham_mu_edge"),
]

# Nu: dn-only candidate for Mu's orpham; won't pass since ref_up_pham is None.
NU_GENES = [
    _gene("N_1", "Nu", 1,  100,  500, "pham_nu_other"),
    _gene("N_2", "Nu", 2,  600, 1000, "pham_nu_mid", "portal protein"),
    _gene("N_3", "Nu", 3, 1100, 1500, "pham_mu_dn"),
]

ALL_GENES = (
    ALPHA_GENES + BETA_GENES + GAMMA_GENES + DELTA_GENES
    + IOTA_GENES + ETA_GENES + THETA_GENES
    + KAPPA_GENES + LAMBDA_GENES + MU_GENES + NU_GENES
)


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


@pytest.fixture(scope="session")
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
