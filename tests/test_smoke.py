"""
Smoke tests against the real phamerator.sqlite database.

All tests are skipped if the DB file is not present (handled by the
``real_db`` fixture in conftest.py).

These tests check:
  - the full pipeline produces structurally valid output
  - known-good phages (LordVader, Beanstalk) return expected counts
  - cluster/wildcard resolution returns expected phage counts
  - the CLI can be invoked programmatically without crashing
"""
import pytest

REAL_DATASET = "Actino_Draft"


# ---------------------------------------------------------------------------
# DB-level smoke tests
# ---------------------------------------------------------------------------


class TestRealDbAnalysis:
    def test_lordvader_counts(self, real_db):
        from orpham_report.analysis import compute_phage_results
        passing, summary = compute_phage_results(real_db, "LordVader", REAL_DATASET)
        assert summary["total_genes"] == 102
        assert summary["total_orphams"] == 24
        assert summary["with_informative"] == 3

    def test_beanstalk_no_passing(self, real_db):
        from orpham_report.analysis import compute_phage_results
        passing, summary = compute_phage_results(real_db, "Beanstalk", REAL_DATASET)
        assert summary["total_genes"] == 100
        assert summary["total_orphams"] == 5
        assert summary["with_informative"] == 0

    def test_result_fields_present(self, real_db):
        from orpham_report.analysis import compute_phage_results
        passing, _ = compute_phage_results(real_db, "LordVader", REAL_DATASET)
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
