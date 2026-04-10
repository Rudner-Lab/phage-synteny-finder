"""Unit tests for orpham_report.analysis."""
import pytest
from tests.conftest import DATASET

from orpham_report.analysis import (
    load_phage_genes,
    bulk_check_orpham_phams,
    identify_orphams,
    find_candidate_phages,
    load_candidate_data,
    build_pham_index,
    scan_orpham_hits,
    compute_function_tallies,
    compute_one_flank_tallies,
    passes_filter,
    compute_phage_results,
    is_informative,
    fn_display,
    UNINFORMATIVE,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestIsInformative:
    @pytest.mark.parametrize("fn", ["", "nkf", "NKF", "Hypothetical protein", "no known function"])
    def test_uninformative(self, fn):
        assert not is_informative(fn)

    @pytest.mark.parametrize("fn", ["lysin A", "portal protein", "HNH endonuclease"])
    def test_informative(self, fn):
        assert is_informative(fn)

    def test_none(self):
        assert not is_informative(None)


class TestFnDisplay:
    def test_blank_becomes_label(self):
        assert fn_display("") == "NKF / hypothetical"

    def test_none_becomes_label(self):
        assert fn_display(None) == "NKF / hypothetical"

    def test_nkf_raw_preserved(self):
        # non-empty uninformative strings are returned as-is (stripped);
        # only None / empty map to the "NKF / hypothetical" label
        assert fn_display("nkf") == "nkf"

    def test_informative_stripped(self):
        assert fn_display("  lysin A  ") == "lysin A"


# ---------------------------------------------------------------------------
# load_phage_genes
# ---------------------------------------------------------------------------


class TestLoadPhageGenes:
    def test_count(self, db):
        genes = load_phage_genes(db, "Alpha", DATASET)
        assert len(genes) == 5

    def test_sorted_by_stop(self, db):
        genes = load_phage_genes(db, "Alpha", DATASET)
        stops = [g["stop"] for g in genes]
        assert stops == sorted(stops)

    def test_unknown_phage(self, db):
        assert load_phage_genes(db, "NoSuch", DATASET) == []


# ---------------------------------------------------------------------------
# bulk_check_orpham_phams
# ---------------------------------------------------------------------------


class TestBulkCheckOrphamPhams:
    def test_shared_pham_not_orpham(self, db):
        result = bulk_check_orpham_phams(db, {"pham_shared_up"}, DATASET)
        assert result["pham_shared_up"] is False

    def test_single_phage_pham_is_orpham(self, db):
        result = bulk_check_orpham_phams(db, {"pham_orpham_A"}, DATASET)
        assert result["pham_orpham_A"] is True

    def test_unknown_pham_treated_as_orpham(self, db):
        result = bulk_check_orpham_phams(db, {"nonexistent_pham"}, DATASET)
        assert result["nonexistent_pham"] is True

    def test_empty_input(self, db):
        assert bulk_check_orpham_phams(db, set(), DATASET) == {}

    def test_multiple_phams(self, db):
        result = bulk_check_orpham_phams(
            db, {"pham_shared_up", "pham_orpham_A", "pham_orpham_B"}, DATASET
        )
        assert result["pham_shared_up"] is False
        assert result["pham_orpham_A"] is True
        assert result["pham_orpham_B"] is True


# ---------------------------------------------------------------------------
# identify_orphams
# ---------------------------------------------------------------------------


class TestIdentifyOrphams:
    def _load(self, db, phage_id):
        genes = load_phage_genes(db, phage_id, DATASET)
        phams = {g["pham_name"] for g in genes if g["pham_name"]}
        pham_is_orpham = bulk_check_orpham_phams(db, phams, DATASET)
        return genes, pham_is_orpham

    def test_alpha_has_one_orpham(self, db):
        genes, piam = self._load(db, "Alpha")
        orphams = identify_orphams(genes, piam)
        assert len(orphams) == 1

    def test_alpha_orpham_gene_number(self, db):
        genes, piam = self._load(db, "Alpha")
        o = identify_orphams(genes, piam)[0]
        assert o["gene"]["name"] == "3"

    def test_alpha_orpham_flanks(self, db):
        genes, piam = self._load(db, "Alpha")
        o = identify_orphams(genes, piam)[0]
        assert o["ref_up_pham"] == "pham_shared_up"
        assert o["ref_dn_pham"] == "pham_shared_dn"

    def test_gamma_has_two_orphams(self, db):
        genes, piam = self._load(db, "Gamma")
        orphams = identify_orphams(genes, piam)
        assert len(orphams) == 2

    def test_gene_with_no_pham_is_orpham(self, db):
        # A gene with pham_name=None should be treated as an orpham
        genes = [
            {"pham_name": None, "direction": "forward", "gene_function": ""},
            {"pham_name": "shared_pham", "direction": "forward", "gene_function": ""},
        ]
        pham_map = {"shared_pham": False}
        orphams = identify_orphams(genes, pham_map)
        assert len(orphams) == 1
        assert orphams[0]["gene"]["pham_name"] is None

    def test_reverse_strand_swaps_neighbors(self, db):
        # For a reverse-strand gene, up/dn are swapped relative to array index
        genes = [
            {"pham_name": "A", "direction": "forward", "gene_function": "fn_A"},
            {"pham_name": "solo", "direction": "reverse", "gene_function": ""},
            {"pham_name": "B", "direction": "forward", "gene_function": "fn_B"},
        ]
        pham_map = {"A": False, "B": False, "solo": True}
        orphams = identify_orphams(genes, pham_map)
        assert len(orphams) == 1
        # For reverse strand gene at index 1: up_idx = 2 (B), dn_idx = 0 (A)
        assert orphams[0]["ref_up_pham"] == "B"
        assert orphams[0]["ref_dn_pham"] == "A"


# ---------------------------------------------------------------------------
# find_candidate_phages
# ---------------------------------------------------------------------------


class TestFindCandidatePhages:
    def test_finds_beta_as_candidate_for_alpha(self, db):
        # Alpha's orpham neighbours are pham_shared_up / pham_shared_dn
        # Beta carries both → should be returned
        from orpham_report.db import normalize_phage_id
        candidates = find_candidate_phages(
            db, {"pham_shared_up", "pham_shared_dn"}, normalize_phage_id("Alpha"), DATASET
        )
        assert "Beta" in candidates
        assert "Alpha" not in candidates

    def test_excludes_ref_phage(self, db):
        from orpham_report.db import normalize_phage_id
        candidates = find_candidate_phages(
            db, {"pham_shared_up"}, normalize_phage_id("Alpha"), DATASET
        )
        assert "Alpha" not in candidates

    def test_empty_neighbor_phams(self, db):
        candidates = find_candidate_phages(db, set(), "alpha", DATASET)
        assert candidates == set()


# ---------------------------------------------------------------------------
# load_candidate_data
# ---------------------------------------------------------------------------


class TestLoadCandidateData:
    def test_returns_genes_for_candidates(self, db):
        genes, meta = load_candidate_data(db, {"Beta"}, DATASET)
        assert "Beta" in genes
        assert len(genes["Beta"]) == 5

    def test_returns_meta(self, db):
        _, meta = load_candidate_data(db, {"Beta"}, DATASET)
        assert meta["Beta"]["cluster"] == "A1"
        assert meta["Beta"]["is_draft"] is False

    def test_draft_flag_from_column(self, db):
        _, meta = load_candidate_data(db, {"Epsilon"}, DATASET)
        assert meta["Epsilon"]["is_draft"] is True

    def test_empty_candidates(self, db):
        genes, meta = load_candidate_data(db, set(), DATASET)
        assert genes == {}
        assert meta == {}


# ---------------------------------------------------------------------------
# build_pham_index
# ---------------------------------------------------------------------------


class TestBuildPhamIndex:
    def test_indexes_phams(self, db):
        genes_map = {"Alpha": load_phage_genes(db, "Alpha", DATASET)}
        index = build_pham_index(genes_map)
        assert "pham_shared_up" in index
        assert "Alpha" in index["pham_shared_up"]

    def test_skips_null_pham(self):
        genes_map = {"X": [{"pham_name": None}]}
        index = build_pham_index(genes_map)
        assert index == {}


# ---------------------------------------------------------------------------
# scan_orpham_hits
# ---------------------------------------------------------------------------


class TestScanOrphamHits:
    def _setup_gamma(self, db):
        gamma_genes = load_phage_genes(db, "Gamma", DATASET)
        phams = {g["pham_name"] for g in gamma_genes if g["pham_name"]}
        pham_is_orpham = bulk_check_orpham_phams(db, phams, DATASET)
        orphams = identify_orphams(gamma_genes, pham_is_orpham)
        # orpham at gene 3 (pham_orpham_B, flanked by pham_b_up / pham_b_dn)
        orpham_b = next(o for o in orphams if o["gene"]["name"] == "3")
        delta_genes, delta_meta = load_candidate_data(db, {"Delta"}, DATASET)
        pham_index = build_pham_index(delta_genes)
        return orpham_b, delta_genes, pham_index, delta_meta

    def test_finds_two_sided_hit(self, db):
        orpham, genes, idx, meta = self._setup_gamma(db)
        hits = scan_orpham_hits(orpham, genes, idx, meta)
        two_sided = [h for h in hits if h["two_sided"]]
        assert len(two_sided) == 1

    def test_hit_phage_is_delta(self, db):
        orpham, genes, idx, meta = self._setup_gamma(db)
        hits = scan_orpham_hits(orpham, genes, idx, meta)
        assert all(h["phage"] == "Delta" for h in hits)

    def test_hit_function(self, db):
        orpham, genes, idx, meta = self._setup_gamma(db)
        hits = scan_orpham_hits(orpham, genes, idx, meta)
        two_sided = [h for h in hits if h["two_sided"]]
        assert two_sided[0]["gene_function"] == "lysin A"

    def test_no_hits_when_no_candidates(self, db):
        orpham = {
            "ref_up_pham": "nonexistent_pham",
            "ref_dn_pham": "nonexistent_pham",
        }
        hits = scan_orpham_hits(orpham, {}, {}, {})
        assert hits == []


# ---------------------------------------------------------------------------
# compute_function_tallies
# ---------------------------------------------------------------------------


class TestComputeFunctionTallies:
    def _make_hits(self, pairs):
        """pairs: list of (gene_function, up_match, dn_match)"""
        return [
            {
                "gene_function": fn,
                "up_match": um,
                "dn_match": dm,
                "two_sided": um and dm,
            }
            for fn, um, dm in pairs
        ]

    def test_two_sided_hit_counts(self):
        hits = self._make_hits([("lysin A", True, True)])
        tally, total, both_fns = compute_function_tallies(hits)
        assert dict(tally)["lysin A"] == 1
        assert total == 1
        assert "lysin A" in both_fns

    def test_one_sided_not_in_both_fns(self):
        hits = self._make_hits([("lysin A", True, False)])
        _, _, both_fns = compute_function_tallies(hits)
        assert "lysin A" not in both_fns

    def test_cross_flank_qualification(self):
        # fn appears in one up-only AND one dn-only hit → qualifies for both_fns
        # but tally only counts two_sided hits, so tally total is 0
        hits = self._make_hits([
            ("lysin A", True, False),
            ("lysin A", False, True),
        ])
        tally, total, both_fns = compute_function_tallies(hits)
        assert "lysin A" in both_fns           # qualifies for filtering
        assert total == 0                       # no two_sided hits → tally is empty
        assert dict(tally).get("lysin A", 0) == 0

    def test_empty_hits(self):
        tally, total, both_fns = compute_function_tallies([])
        assert tally == []
        assert total == 0
        assert both_fns == set()

    def test_blank_function_normalised(self):
        hits = self._make_hits([("", True, True)])
        _, _, both_fns = compute_function_tallies(hits)
        assert "Hypothetical protein" in both_fns


# ---------------------------------------------------------------------------
# compute_one_flank_tallies
# ---------------------------------------------------------------------------


class TestComputeOneFlankTallies:
    def _make_hits(self, pairs):
        return [
            {"gene_function": fn, "up_match": um, "dn_match": dm, "two_sided": um and dm}
            for fn, um, dm in pairs
        ]

    def test_counts_up_and_dn_only(self):
        hits = self._make_hits([
            ("lysin A", True, False),   # up-only
            ("lysin B", False, True),   # dn-only
        ])
        one_fns, up_count, dn_count = compute_one_flank_tallies(hits)
        assert up_count == 1
        assert dn_count == 1

    def test_two_sided_excluded(self):
        hits = self._make_hits([("lysin A", True, True)])
        _, up_count, dn_count = compute_one_flank_tallies(hits)
        assert up_count == 0
        assert dn_count == 0

    def test_shared_first_in_sort(self):
        hits = self._make_hits([
            ("lysin A", True, False),
            ("lysin A", False, True),
            ("portal protein", True, False),
        ])
        one_fns, _, _ = compute_one_flank_tallies(hits)
        fns = [fn for fn, _ in one_fns]
        assert fns[0] == "lysin A"  # seen in both subsets → first


# ---------------------------------------------------------------------------
# passes_filter
# ---------------------------------------------------------------------------


class TestPassesFilter:
    def test_informative_two_flank_passes(self):
        assert passes_filter({"lysin A"}, [])

    def test_uninformative_two_flank_fails(self):
        assert not passes_filter({"nkf"}, [])

    def test_informative_convergent_one_flank_passes(self):
        one_fns = [("lysin A", {"up": 1, "dn": 1})]
        assert passes_filter(set(), one_fns)

    def test_informative_one_sided_only_fails(self):
        # informative but only on one flank
        one_fns = [("lysin A", {"up": 1, "dn": 0})]
        assert not passes_filter(set(), one_fns)

    def test_empty_everything_fails(self):
        assert not passes_filter(set(), [])


# ---------------------------------------------------------------------------
# compute_phage_results — integration
# ---------------------------------------------------------------------------


class TestComputePhageResults:
    def test_gamma_has_one_passing_orpham(self, db):
        passing, summary = compute_phage_results(db, "Gamma", DATASET)
        assert len(passing) == 1

    def test_gamma_passing_orpham_gene(self, db):
        passing, _ = compute_phage_results(db, "Gamma", DATASET)
        assert passing[0]["gene_number"] == "3"

    def test_gamma_summary_counts(self, db):
        _, summary = compute_phage_results(db, "Gamma", DATASET)
        assert summary["total_genes"] == 4
        assert summary["total_orphams"] == 2
        assert summary["with_informative"] == 1

    def test_alpha_no_passing_orphams(self, db):
        # Alpha's orpham has only NKF hits → filtered out
        passing, _ = compute_phage_results(db, "Alpha", DATASET)
        assert len(passing) == 0

    def test_alpha_summary_has_orpham(self, db):
        _, summary = compute_phage_results(db, "Alpha", DATASET)
        assert summary["total_orphams"] == 1
        assert summary["with_informative"] == 0

    def test_empty_phage(self, db):
        # Epsilon has is_draft=1 but no genes
        passing, summary = compute_phage_results(db, "Epsilon", DATASET)
        assert passing == []
        assert summary["total_genes"] == 0


# ---------------------------------------------------------------------------
# compute_function_tallies — counting invariants
# ---------------------------------------------------------------------------


class TestComputeFunctionTalliesInvariants:
    """Key invariant: sum(tally) == number of two_sided hits."""

    def _make_hits(self, pairs):
        return [
            {"gene_function": fn, "up_match": um, "dn_match": dm, "two_sided": um and dm}
            for fn, um, dm in pairs
        ]

    def test_tally_total_equals_n_two_sided(self):
        hits = self._make_hits([
            ("lysin A", True,  True),   # two-sided
            ("portal",  True,  True),   # two-sided
            ("nkf",     True,  False),  # up-only
            ("nkf",     False, True),   # dn-only
        ])
        _, total, _ = compute_function_tallies(hits)
        n_two_sided = sum(1 for h in hits if h["two_sided"])
        assert total == n_two_sided  # invariant: tally total == two-sided count

    def test_cross_flank_in_both_fns_but_not_tally(self):
        # fn on both flanks via separate one-sided hits → qualifies filter but not tally
        hits = self._make_hits([
            ("lysin A", True,  False),
            ("lysin A", False, True),
        ])
        tally, total, both_fns = compute_function_tallies(hits)
        assert "lysin A" in both_fns             # cross-flank → filter qualifies
        assert total == 0                         # no two-sided hits
        assert dict(tally).get("lysin A", 0) == 0

    def test_multiple_two_sided_same_function(self):
        hits = self._make_hits([
            ("lysin A", True, True),
            ("lysin A", True, True),
            ("lysin A", True, True),
        ])
        tally, total, _ = compute_function_tallies(hits)
        assert dict(tally)["lysin A"] == 3
        assert total == 3

    def test_mixed_two_sided_and_one_sided_tally_counts_only_two(self):
        # One two-sided + two one-sided hits for the same function: tally = 1
        hits = self._make_hits([
            ("lysin A", True,  True),   # two-sided → counted
            ("lysin A", True,  False),  # up-only → NOT in tally
            ("lysin A", False, True),   # dn-only → NOT in tally
        ])
        tally, total, both_fns = compute_function_tallies(hits)
        assert dict(tally)["lysin A"] == 1
        assert total == 1
        assert "lysin A" in both_fns

    def test_blank_function_normalised_in_tally(self):
        hits = self._make_hits([("", True, True)])
        tally, total, both_fns = compute_function_tallies(hits)
        assert dict(tally).get("Hypothetical protein", 0) == 1
        assert total == 1
        assert "Hypothetical protein" in both_fns

    def test_purely_one_sided_hits_produce_empty_tally(self):
        hits = self._make_hits([
            ("lysin A", True,  False),
            ("portal",  False, True),
        ])
        tally, total, _ = compute_function_tallies(hits)
        assert tally == []
        assert total == 0


# ---------------------------------------------------------------------------
# compute_cluster_results — batch pipeline
# ---------------------------------------------------------------------------


class TestComputeClusterResults:
    def test_returns_all_phages(self, db):
        from orpham_report.analysis import compute_cluster_results
        results = compute_cluster_results(db, ["Alpha", "Beta", "Gamma", "Delta"], DATASET)
        assert len(results) == 4
        assert {r[0] for r in results} == {"Alpha", "Beta", "Gamma", "Delta"}

    def test_results_in_input_order(self, db):
        from orpham_report.analysis import compute_cluster_results
        phage_ids = ["Delta", "Alpha", "Gamma", "Beta"]
        results = compute_cluster_results(db, phage_ids, DATASET)
        assert [r[0] for r in results] == phage_ids

    def test_matches_single_phage_results(self, db):
        # Batch results for Gamma must equal the single-phage pipeline output
        from orpham_report.analysis import compute_cluster_results
        batch = compute_cluster_results(db, ["Gamma"], DATASET)
        single_passing, single_summary = compute_phage_results(db, "Gamma", DATASET)
        _, batch_passing, batch_summary = batch[0]
        assert len(batch_passing) == len(single_passing)
        assert batch_summary == single_summary

    def test_gamma_informative_count_matches(self, db):
        from orpham_report.analysis import compute_cluster_results
        results = compute_cluster_results(db, ["Gamma"], DATASET)
        _, passing, summary = results[0]
        assert summary["with_informative"] == 1
        assert len(passing) == 1

    def test_alpha_zero_informative(self, db):
        from orpham_report.analysis import compute_cluster_results
        results = compute_cluster_results(db, ["Alpha"], DATASET)
        _, passing, summary = results[0]
        assert summary["with_informative"] == 0
        assert passing == []

    def test_callback_called_for_each_phage(self, db):
        from orpham_report.analysis import compute_cluster_results
        seen = []
        compute_cluster_results(
            db, ["Alpha", "Gamma"], DATASET,
            on_phage_done=lambda pid, passing, summary: seen.append(pid),
        )
        assert set(seen) == {"Alpha", "Gamma"}

    def test_callback_receives_correct_summary(self, db):
        from orpham_report.analysis import compute_cluster_results
        summaries = {}
        compute_cluster_results(
            db, ["Gamma"], DATASET,
            on_phage_done=lambda pid, passing, summary: summaries.update({pid: summary}),
        )
        assert summaries["Gamma"]["with_informative"] == 1
        assert summaries["Gamma"]["total_orphams"] == 2

    def test_empty_phage_list(self, db):
        from orpham_report.analysis import compute_cluster_results
        assert compute_cluster_results(db, [], DATASET) == []

    def test_phage_with_no_genes(self, db):
        from orpham_report.analysis import compute_cluster_results
        results = compute_cluster_results(db, ["Epsilon"], DATASET)
        assert len(results) == 1
        _, passing, summary = results[0]
        assert passing == []
        assert summary["total_genes"] == 0
