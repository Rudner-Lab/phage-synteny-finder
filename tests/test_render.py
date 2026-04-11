"""Smoke tests for orpham_report.render."""
import pytest
from tests.conftest import DATASET

from orpham_report.analysis import compute_phage_results
from orpham_report.db import resolve_cluster_phages
from orpham_report.render import render_html, escape


# ---------------------------------------------------------------------------
# escape helper
# ---------------------------------------------------------------------------


class TestEscape:
    def test_escapes_html_chars(self):
        assert "&amp;" in escape("&")
        assert "&lt;" in escape("<")
        assert "&gt;" in escape(">")
        assert "&#x27;" in escape("'") or "&apos;" in escape("'") or "'" in escape("'")

    def test_none_becomes_empty_string(self):
        assert escape(None) == ""


# ---------------------------------------------------------------------------
# render_html smoke tests
# ---------------------------------------------------------------------------


def _build_results(db, patterns):
    """Return (results, phage_is_draft) for the given cluster patterns."""
    phage_rows = resolve_cluster_phages(db, patterns, DATASET)
    results = []
    phage_is_draft = {}
    for phage_id, cluster, cs, is_draft in phage_rows:
        orpham_results, summary = compute_phage_results(db, phage_id, DATASET)
        results.append((phage_id, cluster, cs, orpham_results, summary))
        phage_is_draft[phage_id] = is_draft
    return results, phage_is_draft


class TestRenderHtml:
    def test_returns_string(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        assert isinstance(html, str)

    def test_is_valid_html_structure(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<body" in html
        assert "</body>" in html

    def test_contains_dataset_name(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        assert DATASET in html

    def test_contains_toc(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        assert 'id="toc"' in html

    def test_contains_cluster_sections(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        assert 'class="cluster-section"' in html

    def test_phage_sections_present(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        for phage_id in ("Alpha", "Beta", "Gamma", "Delta"):
            assert phage_id in html

    def test_passing_orpham_shown(self, db):
        # Gamma's gene 3 passes the filter → should appear as an orpham card
        results, phage_is_draft = _build_results(db, ["B"])
        html = render_html(results, DATASET, ["B"], phage_is_draft=phage_is_draft)
        assert "lysin A" in html

    def test_non_passing_orpham_not_shown(self, db):
        # Alpha's orpham doesn't pass → its pham_orpham_A should not appear as a card title
        results, phage_is_draft = _build_results(db, ["A1"])
        html = render_html(results, DATASET, ["A1"], phage_is_draft=phage_is_draft)
        # pham_orpham_A only appears if the card is rendered
        assert "pham_orpham_A" not in html

    def test_no_results_phage_in_omitted_footer(self, db):
        # Alpha has orphams but no informative results → in omitted footer, not a phage section
        results, phage_is_draft = _build_results(db, ["A1"])
        html = render_html(results, DATASET, ["A1"], phage_is_draft=phage_is_draft)
        assert 'id="phage-Alpha"' not in html          # not a phage-details section
        assert "Alpha" in html                          # still mentioned in omitted footer

    def test_phage_sections_always_collapsed(self, db):
        # Phage <details> sections never have the "open" attribute, even with results
        results, phage_is_draft = _build_results(db, ["B"])
        html = render_html(results, DATASET, ["B"], phage_is_draft=phage_is_draft)
        idx = html.find('id="phage-Gamma"')
        assert idx != -1
        tag = html[idx - 50: idx + 100]
        assert "open" not in tag

    def test_empty_results_list(self, db):
        html = render_html([], DATASET, ["ZZZ"])
        assert "<!DOCTYPE html>" in html
        # No phage sections at all
        assert 'class="phage-details"' not in html

    def test_draft_flag_rendered(self, db):
        # Epsilon is a draft phage; if it appears, the draft flag should be renderable
        results, phage_is_draft = _build_results(db, ["C"])
        html = render_html(results, DATASET, ["C"], phage_is_draft=phage_is_draft)
        assert "Epsilon" in html

    def test_title_reflects_pattern(self, db):
        results, phage_is_draft = _build_results(db, ["A1"])
        html = render_html(results, DATASET, ["A1"], phage_is_draft=phage_is_draft)
        assert "Cluster A" in html

    def test_title_all(self, db):
        results, phage_is_draft = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"], phage_is_draft=phage_is_draft)
        assert "All Clusters" in html

    def test_draft_emoji_in_results_table(self, db):
        # Kappa is a draft phage with a passing orpham; 🚧 must appear in the
        # results-at-a-glance table next to its name
        results, phage_is_draft = _build_results(db, ["E1"])
        html = render_html(results, DATASET, ["E1"], phage_is_draft=phage_is_draft)
        assert "🚧" in html

    def test_corroborated_row_highlighted_two_sided(self, db):
        # Gamma's "lysin A" is a genuine two-sided hit; its tally row should carry
        # class="tr-corroborated" and the function should appear nearby
        results, phage_is_draft = _build_results(db, ["B"])
        html = render_html(results, DATASET, ["B"], phage_is_draft=phage_is_draft)
        assert 'class="tr-corroborated"' in html
        idx = html.find('class="tr-corroborated"')
        assert "lysin A" in html[idx:idx + 300]

    def test_corroborated_row_highlighted_chimeric(self, db):
        # Iota's "lysin B" passes via convergent one-sided evidence (no single
        # phage has both flanks); the tally row should still carry tr-corroborated
        results, phage_is_draft = _build_results(db, ["D1"])
        html = render_html(results, DATASET, ["D1"], phage_is_draft=phage_is_draft)
        assert 'class="tr-corroborated"' in html
        idx = html.find('class="tr-corroborated"')
        assert "lysin B" in html[idx:idx + 300]

    def test_gene_function_html_escaped(self, db):
        # Lambda's hit gene has function "terminase & lysin"; the '&' must be
        # escaped to '&amp;' — an unescaped '&' would be invalid HTML
        results, phage_is_draft = _build_results(db, ["E1"])
        html = render_html(results, DATASET, ["E1"], phage_is_draft=phage_is_draft)
        assert "terminase &amp; lysin" in html

    def test_reverse_strand_orpham_in_report(self, db):
        # Kappa's orpham is on the reverse strand; it should appear in the report
        # because Lambda provides a two-sided hit after the strand-aware flank swap
        results, phage_is_draft = _build_results(db, ["E1"])
        html = render_html(results, DATASET, ["E1"], phage_is_draft=phage_is_draft)
        assert 'id="phage-Kappa"' in html
        assert "terminase" in html

    def test_chimeric_orpham_in_report(self, db):
        # Iota's orpham (chimeric evidence) should appear as a phage section
        # with its function in the report
        results, phage_is_draft = _build_results(db, ["D1"])
        html = render_html(results, DATASET, ["D1"], phage_is_draft=phage_is_draft)
        assert 'id="phage-Iota"' in html
        assert "lysin B" in html
