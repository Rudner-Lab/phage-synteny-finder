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

    def test_no_draft_stripping(self):
        # normalize_phage_id only lowercases; _Draft suffix is no longer stripped
        assert normalize_phage_id("Beanstalk_Draft") == "beanstalk_draft"

    def test_strips_whitespace(self):
        assert normalize_phage_id("  Alpha  ") == "alpha"

    def test_empty(self):
        assert normalize_phage_id("") == ""

    def test_mixed_case(self):
        assert normalize_phage_id("FooBAR") == "foobar"


# ---------------------------------------------------------------------------
# resolve_phage_id
# ---------------------------------------------------------------------------


class TestResolvePhageId:
    def test_exact_match(self, db):
        assert resolve_phage_id(db, "Alpha", DATASET) == "Alpha"

    def test_case_insensitive(self, db):
        assert resolve_phage_id(db, "ALPHA", DATASET) == "Alpha"

    def test_draft_suffix_not_resolved(self, db):
        # normalize_phage_id no longer strips _Draft, so "Alpha_Draft" won't match "Alpha"
        assert resolve_phage_id(db, "Alpha_Draft", DATASET) is None

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
        assert self._ids(rows) == {"Alpha", "Beta", "Zeta", "Gamma", "Delta", "Epsilon", "Iota", "Eta", "Theta"}

    def test_exact_subcluster(self, db):
        # "A1" matches cluster_subcluster = "A1" exactly
        rows = resolve_cluster_phages(db, ["A1"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta"}

    def test_bare_cluster_returns_unsubclustered(self, db):
        # "A" matches cluster=A with no subcluster assigned → Zeta only
        rows = resolve_cluster_phages(db, ["A"], DATASET)
        assert self._ids(rows) == {"Zeta"}

    def test_wildcard_cluster(self, db):
        # "A*" matches all phages in cluster A regardless of subcluster
        rows = resolve_cluster_phages(db, ["A*"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta", "Zeta"}

    def test_multiple_patterns_union(self, db):
        # "A*" (all of A) + "B" (cluster_subcluster="B") → union of both
        rows = resolve_cluster_phages(db, ["A*", "B"], DATASET)
        assert self._ids(rows) == {"Alpha", "Beta", "Zeta", "Gamma", "Delta"}

    def test_bare_cluster_b_includes_subclustered(self, db):
        # Gamma/Delta have cluster_subcluster="B" → matched by exact "B"
        rows = resolve_cluster_phages(db, ["B"], DATASET)
        assert self._ids(rows) == {"Gamma", "Delta"}

    def test_no_match(self, db):
        rows = resolve_cluster_phages(db, ["ZZZ"], DATASET)
        assert rows == []

    def test_deduplication(self, db):
        # "A*" and "A1" both match Alpha and Beta; results must not be duplicated
        rows = resolve_cluster_phages(db, ["A*", "A1"], DATASET)
        ids = [r[0] for r in rows]
        assert len(ids) == len(set(ids))

    def test_returns_cluster_info(self, db):
        rows = resolve_cluster_phages(db, ["A1"], DATASET)
        for phage_id, cluster, cs, is_draft in rows:
            assert cluster == "A"
            assert cs == "A1"

    def test_unsubclustered_cluster_info(self, db):
        rows = resolve_cluster_phages(db, ["A"], DATASET)
        assert len(rows) == 1
        phage_id, cluster, cs, is_draft = rows[0]
        assert phage_id == "Zeta"
        assert cluster == "A"
        assert cs == ""
