"""Unit tests for orpham_report.db."""
import pytest
from tests.conftest import DATASET
from orpham_report.db import normalize_phage_id, resolve_phage_id, resolve_cluster_phages


# ---------------------------------------------------------------------------
# normalize_phage_id
# ---------------------------------------------------------------------------


class TestNormalizePhageId:
    def test_plain(self):
        assert normalize_phage_id("LordVader") == "lordvader"

    def test_strips_draft_suffix(self):
        assert normalize_phage_id("Beanstalk_Draft") == "beanstalk"

    def test_case_insensitive_draft(self):
        assert normalize_phage_id("Foo_DRAFT") == "foo"

    def test_strips_whitespace(self):
        assert normalize_phage_id("  Alpha  ") == "alpha"

    def test_empty(self):
        assert normalize_phage_id("") == ""


# ---------------------------------------------------------------------------
# resolve_phage_id
# ---------------------------------------------------------------------------


class TestResolvePhageId:
    def test_exact_match(self, db):
        assert resolve_phage_id(db, "Alpha", DATASET) == "Alpha"

    def test_case_insensitive(self, db):
        assert resolve_phage_id(db, "ALPHA", DATASET) == "Alpha"

    def test_strips_draft_before_lookup(self, db):
        # "Alpha_Draft" should resolve to "Alpha" (which exists without suffix)
        assert resolve_phage_id(db, "Alpha_Draft", DATASET) == "Alpha"

    def test_missing_phage(self, db):
        assert resolve_phage_id(db, "NoSuchPhage", DATASET) is None

    def test_wrong_dataset(self, db):
        assert resolve_phage_id(db, "Alpha", "WrongDataset") is None


# ---------------------------------------------------------------------------
# resolve_cluster_phages
# ---------------------------------------------------------------------------


class TestResolveClusterPhages:
    def _ids(self, rows):
        return {r[0] for r in rows}

    def test_all(self, db):
        rows = resolve_cluster_phages(db, ["all"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta", "Gamma", "Delta", "Epsilon"}

    def test_exact_cluster(self, db):
        # "A" matches the cluster column → all A subclusters (A1 here)
        rows = resolve_cluster_phages(db, ["A"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta"}

    def test_exact_subcluster(self, db):
        # "A1" matches cluster_subcluster exactly
        rows = resolve_cluster_phages(db, ["A1"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta"}

    def test_multiple_patterns_union(self, db):
        rows = resolve_cluster_phages(db, ["A", "B"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta", "Gamma", "Delta"}

    def test_no_match(self, db):
        rows = resolve_cluster_phages(db, ["ZZZ"], DATASET)
        assert rows == []

    def test_deduplication(self, db):
        # "A" and "A1" both match the same phages; results must not be duplicated
        rows = resolve_cluster_phages(db, ["A", "A1"], DATASET)
        ids = [r[0] for r in rows]
        assert len(ids) == len(set(ids))

    def test_returns_cluster_info(self, db):
        rows = resolve_cluster_phages(db, ["A"], DATASET)
        for phage_id, cluster, cs in rows:
            assert cluster == "A"
            assert cs == "A1"
