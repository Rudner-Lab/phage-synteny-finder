"""
Smoke tests against the real phamerator.sqlite database.

All tests are skipped if the DB file is not present (handled by the
``real_db`` fixture in conftest.py).

These tests check:
  - the full pipeline produces structurally valid output
  - known-good phages (LordVader, Beanstalk) return expected counts
  - cluster/wildcard resolution returns expected phage counts
  - the CLI can be invoked programmatically without crashing
  - generate_cluster_reports produces valid HTML per cluster
  - reset_db deletes the database file and associated WAL/SHM files
"""
import sys
from pathlib import Path

import pytest

# Allow importing scripts/ as modules (they use sys.path.insert themselves,
# but we need the path set before import at collection time).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REAL_DATASET = "Actino_Draft"


# ---------------------------------------------------------------------------
# DB-level smoke tests
# ---------------------------------------------------------------------------


class TestRealDbAnalysis:
    def test_rrh1_counts(self, real_db):
        # RRH1: small phage (20 genes) with passing orphams — fast smoke check
        from orpham_report.analysis import compute_phage_results
        passing, summary = compute_phage_results(real_db, "RRH1", REAL_DATASET)
        assert summary["total_genes"] == 20
        assert summary["total_orphams"] == 7
        assert summary["with_informative"] == 3

    def test_thatch_no_passing(self, real_db):
        # Thatch: small phage (19 genes) with orphams but none informative
        from orpham_report.analysis import compute_phage_results
        passing, summary = compute_phage_results(real_db, "Thatch", REAL_DATASET)
        assert summary["total_genes"] == 19
        assert summary["total_orphams"] == 2
        assert summary["with_informative"] == 0

    def test_result_fields_present(self, real_db):
        from orpham_report.analysis import compute_phage_results
        passing, _ = compute_phage_results(real_db, "RRH1", REAL_DATASET)
        required = {
            "gene_number", "pham_name", "direction", "gene_function",
            "gene_length", "start", "stop",
            "ref_up_pham", "ref_dn_pham", "ref_up_func", "ref_dn_func",
            "hits", "tally_sorted", "tally_total", "both_fns",
            "one_fns_sorted", "up_only_count", "dn_only_count",
            "passes_filter", "n_two_sided", "n_one_sided",
        }
        for r in passing:
            assert required <= r.keys(), f"Missing keys: {required - r.keys()}"


class TestRealDbClusters:
    def test_cluster_F_wildcard_count(self, real_db):
        from orpham_report.db import resolve_cluster_phages
        # "F*" wildcard: all phages in cluster F regardless of subcluster → 273
        rows = resolve_cluster_phages(real_db, ["F*"], REAL_DATASET)
        assert len(rows) == 273

    def test_cluster_F_unsubclustered(self, real_db):
        from orpham_report.db import resolve_cluster_phages
        # "F" bare: only phages in cluster F with no subcluster assigned
        rows = resolve_cluster_phages(real_db, ["F"], REAL_DATASET)
        assert len(rows) == 4

    def test_subcluster_F1_count(self, real_db):
        from orpham_report.db import resolve_cluster_phages
        rows = resolve_cluster_phages(real_db, ["F1"], REAL_DATASET)
        assert len(rows) == 253

    def test_all_returns_full_dataset(self, real_db):
        from orpham_report.db import resolve_cluster_phages
        rows = resolve_cluster_phages(real_db, ["all"], REAL_DATASET)
        total = real_db.execute(
            "SELECT COUNT(*) FROM phages WHERE dataset = ?", (REAL_DATASET,)
        ).fetchone()[0]
        assert len(rows) == total

    def test_no_duplicates(self, real_db):
        from orpham_report.db import resolve_cluster_phages
        # "F*" includes all of cluster F; "F1" is a subset — no duplicates expected
        rows = resolve_cluster_phages(real_db, ["F*", "F1"], REAL_DATASET)
        ids = [r[0] for r in rows]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_unknown_cluster_exits(self, tmp_path):
        """CLI should exit cleanly (not crash) when no phages match the pattern."""
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "phamerator.sqlite"
        if not db_path.exists():
            pytest.skip("phamerator.sqlite not present")

        from orpham_report.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--cluster", "ZZZNONEXISTENT", "--db", str(db_path)])
        assert exc_info.value.code != 0

    def test_cli_produces_html(self, real_db, tmp_path):
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "phamerator.sqlite"
        if not db_path.exists():
            pytest.skip("phamerator.sqlite not present")

        out = tmp_path / "smoke.html"
        from orpham_report.cli import main
        # Use a tiny subcluster that exists: pick the first phage's subcluster
        from orpham_report.db import resolve_cluster_phages, open_db
        conn = open_db(db_path)
        rows = resolve_cluster_phages(conn, ["F7"], REAL_DATASET)  # F7 has 1 phage
        conn.close()
        if not rows:
            pytest.skip("F7 subcluster not found")

        main(["--cluster", "F7", "--db", str(db_path), "--out", str(out)])
        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "F7" in content


# ---------------------------------------------------------------------------
# generate_cluster_reports smoke test
# ---------------------------------------------------------------------------

import sqlite3 as _sqlite3


def _make_minimal_db(path: Path) -> None:
    """Create a tiny two-phage, one-cluster SQLite DB for script-level tests."""
    conn = _sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE phages (
            phage_id TEXT NOT NULL, dataset TEXT NOT NULL,
            phagename TEXT, cluster TEXT, subcluster TEXT,
            cluster_subcluster TEXT, genome_length INTEGER,
            is_draft INTEGER NOT NULL DEFAULT 0, scraped_at TEXT,
            PRIMARY KEY (phage_id, dataset)
        );
        CREATE TABLE genes (
            gene_id TEXT NOT NULL, phage_id TEXT NOT NULL, dataset TEXT NOT NULL,
            name TEXT, accession TEXT, start INTEGER, stop INTEGER,
            midpoint REAL, gap INTEGER, direction TEXT, pham_color TEXT,
            pham_name TEXT, translation TEXT, gene_function TEXT,
            locus_tag TEXT, domain_count INTEGER, tm_domain_count INTEGER,
            is_draft INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (gene_id, dataset)
        );
        CREATE INDEX IF NOT EXISTS idx_genes_phage ON genes (phage_id, dataset);
        CREATE INDEX IF NOT EXISTS idx_genes_pham  ON genes (pham_name);
        CREATE TABLE scrape_log (
            phage_id TEXT NOT NULL, dataset TEXT NOT NULL,
            is_draft INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, last_attempt TEXT, error_msg TEXT,
            PRIMARY KEY (phage_id, dataset)
        );
        INSERT INTO phages VALUES
            ('P1','Test','P1','A','A1','A1',50000,0,NULL),
            ('P2','Test','P2','A','A1','A1',50000,0,NULL);
        INSERT INTO genes VALUES
            ('P1_1','P1','Test','g1',NULL,1,300,150,0,'forward',NULL,'pham1',NULL,'lysin',NULL,0,0,0),
            ('P1_2','P1','Test','g2',NULL,301,600,450,0,'forward',NULL,'pham_orpham',NULL,'hypothetical protein',NULL,0,0,0),
            ('P1_3','P1','Test','g3',NULL,601,900,750,0,'forward',NULL,'pham3',NULL,'terminase',NULL,0,0,0),
            ('P2_1','P2','Test','g1',NULL,1,300,150,0,'forward',NULL,'pham1',NULL,'lysin',NULL,0,0,0),
            ('P2_2','P2','Test','g2',NULL,301,600,450,0,'forward',NULL,'pham_other',NULL,'integrase',NULL,0,0,0),
            ('P2_3','P2','Test','g3',NULL,601,900,750,0,'forward',NULL,'pham3',NULL,'terminase',NULL,0,0,0);
    """)
    conn.commit()
    conn.close()


class TestGenerateClusterReports:
    def test_main_produces_html_for_cluster(self, tmp_path):
        """main() enumerates clusters, calls report per cluster, writes named HTML."""
        db = tmp_path / "mini.sqlite"
        _make_minimal_db(db)
        out_dir = tmp_path / "out"

        from scripts.generate_cluster_reports import main as gcr_main
        gcr_main(["--db", str(db), "--out-dir", str(out_dir), "--dataset", "Test"])

        html_files = list(out_dir.glob("*_orpham_report.html"))
        assert len(html_files) == 1, f"Expected 1 HTML file, got {html_files}"
        content = html_files[0].read_text()
        assert "<!DOCTYPE html>" in content
        # File should be named after the cluster
        assert html_files[0].name == "A_orpham_report.html"

    def test_main_missing_db_exits(self, tmp_path):
        """main() exits non-zero when the database file is absent."""
        from scripts.generate_cluster_reports import main as gcr_main

        with pytest.raises(SystemExit) as exc_info:
            gcr_main(["--db", str(tmp_path / "nonexistent.sqlite"), "--out-dir", str(tmp_path)])
        assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# reset_db tests — all paths are inside pytest's tmp_path to prevent
# any risk of touching real files outside the test sandbox.
# ---------------------------------------------------------------------------


class TestResetDb:
    @staticmethod
    def _assert_in_tmp(path: Path, tmp_path: Path) -> None:
        """Fail fast if path is not inside the pytest temp directory."""
        assert str(path).startswith(str(tmp_path)), (
            f"Safety check: {path} is not inside tmp_path {tmp_path}"
        )

    def test_deletes_db_and_wal_shm(self, tmp_path):
        """reset_db removes the .sqlite file and any associated -wal/-shm files."""
        from scripts.scrape_phamerator import reset_db

        db  = tmp_path / "test.sqlite"
        wal = tmp_path / "test.sqlite-wal"
        shm = tmp_path / "test.sqlite-shm"
        for f in (db, wal, shm):
            self._assert_in_tmp(f, tmp_path)
            f.write_bytes(b"x")

        reset_db(str(db))

        assert not db.exists(),  "sqlite file was not removed"
        assert not wal.exists(), "-wal file was not removed"
        assert not shm.exists(), "-shm file was not removed"

    def test_no_error_when_wal_shm_absent(self, tmp_path):
        """reset_db succeeds even when -wal/-shm files don't exist."""
        from scripts.scrape_phamerator import reset_db

        db = tmp_path / "test.sqlite"
        self._assert_in_tmp(db, tmp_path)
        db.write_bytes(b"x")

        reset_db(str(db))  # should not raise

        assert not db.exists()

    def test_no_error_when_all_absent(self, tmp_path):
        """reset_db is a no-op (no error) when nothing exists at the path."""
        from scripts.scrape_phamerator import reset_db

        ghost = tmp_path / "ghost.sqlite"
        self._assert_in_tmp(ghost, tmp_path)

        reset_db(str(ghost))  # should not raise
