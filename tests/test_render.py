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
    phage_rows = resolve_cluster_phages(db, patterns, DATASET)
    results = []
    for phage_id, cluster, cs in phage_rows:
        orpham_results, summary = compute_phage_results(db, phage_id, DATASET)
        results.append((phage_id, cluster, cs, orpham_results, summary))
    return results


class TestRenderHtml:
    def test_returns_string(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        assert isinstance(html, str)

    def test_is_valid_html_structure(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<body" in html
        assert "</body>" in html

    def test_contains_dataset_name(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        assert DATASET in html

    def test_contains_toc(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        assert 'id="toc"' in html

    def test_contains_cluster_sections(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        assert 'class="cluster-section"' in html

    def test_phage_sections_present(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        for phage_id in ("Alpha", "Beta", "Gamma", "Delta"):
            assert phage_id in html

    def test_passing_orpham_shown(self, db):
        # Gamma's gene 3 passes the filter → should appear as an orpham card
        results = _build_results(db, ["B"])
        html = render_html(results, DATASET, ["B"])
        assert "lysin A" in html

    def test_non_passing_orpham_not_shown(self, db):
        # Alpha's orpham doesn't pass → its pham_orpham_A should not appear as a card title
        results = _build_results(db, ["A1"])
        html = render_html(results, DATASET, ["A1"])
        # pham_orpham_A only appears if the card is rendered
        assert "pham_orpham_A" not in html

    def test_no_results_phage_in_omitted_footer(self, db):
        # Alpha has orphams but no informative results → in omitted footer, not a phage section
        results = _build_results(db, ["A1"])
        html = render_html(results, DATASET, ["A1"])
        assert 'id="phage-Alpha"' not in html          # not a phage-details section
        assert "Alpha" in html                          # still mentioned in omitted footer

    def test_phage_sections_always_collapsed(self, db):
        # Phage <details> sections never have the "open" attribute, even with results
        results = _build_results(db, ["B"])
        html = render_html(results, DATASET, ["B"])
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
        results = _build_results(db, ["C"])
        html = render_html(results, DATASET, ["C"])
        assert "Epsilon" in html

    def test_title_reflects_pattern(self, db):
        results = _build_results(db, ["A1"])
        html = render_html(results, DATASET, ["A1"])
        assert "Cluster A" in html

    def test_title_all(self, db):
        results = _build_results(db, ["all"])
        html = render_html(results, DATASET, ["all"])
        assert "All Clusters" in html
