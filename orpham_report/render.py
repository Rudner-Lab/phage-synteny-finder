"""
render.py — HTML rendering for the cluster-level orpham synteny report.

Public entry point: ``render_html(phage_results, dataset, patterns)``

``phage_results`` is a list of PhageResult namedtuples (or equivalent dicts):
  phage_id, cluster, cluster_subcluster, orpham_results, summary
"""
from __future__ import annotations

import base64
import csv
import html as _html
import io
from datetime import datetime, timezone
from pathlib import Path

from .analysis import fn_display, is_informative

# ---------------------------------------------------------------------------
# Favicon (embedded as base64 to keep the report self-contained)
# ---------------------------------------------------------------------------

_FAVICON_PATH = Path(__file__).parent / "images" / "phage favicon.png"
_FAVICON_B64  = (
    "data:image/png;base64,"
    + base64.b64encode(_FAVICON_PATH.read_bytes()).decode()
    if _FAVICON_PATH.exists() else None
)

# ---------------------------------------------------------------------------
# Link templates
# ---------------------------------------------------------------------------

_PHAGESDB_PHAGE = "https://phagesdb.org/phages/{}/"
_PHAGESDB_PHAM  = "https://phagesdb.org/phams/{}/"


# ---------------------------------------------------------------------------
# Inline CSS
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: #1e293b;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 20px 64px;
}
h1 { font-size: 1.4em; margin: 0 0 4px; }
h2.subtitle { font-size: 1.05em; margin: 0 0 20px; color: #475569; font-weight: 400; }
h3.section-title { font-size: 0.95em; color: #475569; margin: 24px 0 8px; font-weight: 600; }

/* ── TOC ── */
#toc { margin: 0 0 32px; padding: 16px 20px; background: #f8fafc;
       border: 1px solid #e2e8f0; border-radius: 8px; }
#toc h3 { margin: 0 0 10px; font-size: 0.95em; color: #475569; }
.toc-clusters { display: flex; flex-wrap: wrap; gap: 8px 20px; }
.toc-cluster  { font-size: 0.88em; }
.toc-cluster a { color: #2563eb; font-weight: 600; }
.toc-cluster .toc-phages { margin-left: 12px; color: #64748b; font-size: 0.92em; }
.toc-cluster .toc-phages a.has-results { color: #15803d; font-weight: 600; }
.toc-phage-omitted { color: #cbd5e1; }

/* ── Summary bar ── */
.summary { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 20px; }
.stat { padding: 6px 14px; border-radius: 6px; border: 1px solid; font-size: 0.88em; }
.stat b { font-size: 1.1em; }
.stat-orange { background: #fff7ed; border-color: #fed7aa; }
.stat-purple { background: #faf5ff; border-color: #e9d5ff; }
.stat-green  { background: #f0fdf4; border-color: #bbf7d0; }
.stat-blue   { background: #eff6ff; border-color: #bfdbfe; }
.stat-slate  { background: #f8fafc; border-color: #e2e8f0; }

/* ── Global results table ── */
.summary-table { margin-bottom: 28px; }

/* ── Cluster sections ── */
.cluster-section {
  margin-bottom: 12px; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;
  content-visibility: auto;
  contain-intrinsic-size: auto 400px;
}
.cluster-heading {
  font-size: 1.05em; font-weight: 700; color: #1e293b;
  padding: 8px 14px; background: #f1f5f9;
  cursor: pointer; user-select: none; list-style: none;
  display: flex; align-items: center; gap: 8px;
}
.cluster-heading::-webkit-details-marker { display: none; }
.cluster-heading::marker { display: none; }
details.cluster-section[open] > .cluster-heading { border-bottom: 2px solid #cbd5e1; }
.cluster-heading .cs-badge {
  display: inline-block; padding: 1px 8px; border-radius: 5px;
  background: #e2e8f0; border: 1px solid #cbd5e1;
  font-size: 0.82em; font-weight: 400; color: #475569; margin-left: auto;
}
.cluster-content { padding: 10px 12px; }

/* ── Phage <details> ── */
.phage-details {
  margin-bottom: 8px; border: 1px solid #e2e8f0; border-radius: 8px;
  content-visibility: auto;
  contain-intrinsic-size: auto 60px;
}
.phage-summary {
  padding: 8px 12px; display: flex; justify-content: space-between;
  align-items: center; flex-wrap: wrap; gap: 6px;
  cursor: pointer; user-select: none; list-style: none;
  background: #f8fafc; border-radius: 8px;
}
.phage-summary::-webkit-details-marker { display: none; }
.phage-summary::marker { display: none; }
details[open] > .phage-summary { border-radius: 8px 8px 0 0; }
.phage-name { font-weight: 700; color: #1e293b; }
.phage-cs   { font-size: 0.82em; color: #94a3b8; margin-left: 6px; }
.phage-stats { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.phage-stat {
  padding: 1px 7px; border-radius: 5px; font-size: 0.78em;
  border: 1px solid #e2e8f0; background: #f8fafc; color: #64748b; white-space: nowrap;
}
.phage-stat-orange { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
.phage-stat-purple { background: #faf5ff; border-color: #e9d5ff; color: #6d28d9; }
.phage-stat-green  { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
.phage-body { padding: 10px 12px; border-top: 1px solid #e2e8f0; }
.phage-no-results { padding: 8px 0; color: #94a3b8; font-style: italic; font-size: 0.88em; }

/* ── Orpham cards ── */
.orpham-card {
  margin-bottom: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
  content-visibility: auto;
  contain-intrinsic-size: auto 50px;
}
.card-header {
  padding: 8px 12px;
  background: #f8fafc;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  list-style: none;
}
.card-header::-webkit-details-marker { display: none; }
.card-header::marker { display: none; }
.gene-title { font-weight: 700; color: #1e293b; }
.gene-pos   { color: #64748b; margin-left: 8px; font-size: 0.9em; }
.assigned-function   { color: #713f12; margin-left: 8px; font-size: 0.9em; }
.gene-fn    { color: #475569; margin-left: 8px; font-style: italic; }
.gene-pham  { font-size: 0.8em; color: #94a3b8; margin-left: 8px; }
.dir-fwd    { color: #2563eb; font-weight: 700; margin-left: 4px; }
.dir-rev    { color: #dc2626; font-weight: 700; margin-left: 4px; }
.badges { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 4px; }
.badge {
  padding: 2px 8px; border-radius: 5px; font-size: 0.8em;
  border: 1px solid; white-space: nowrap;
}
.flank-badge {
  padding: 2px 8px; border-radius: 5px; font-size: 0.8em;
  background: #f8fafc; border: 1px solid #e2e8f0; color: #64748b;
  white-space: nowrap;
}
.badge-two  { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
.badge-one  { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
.card-body  { padding: 10px 12px; border-top: 1px solid #e2e8f0; }

/* ── Function tally table ── */
.tally-section { margin-bottom: 10px; }
.tally-section-label {
  font-size: 0.78em; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: #5b21b6; margin-bottom: 3px;
}
.tally-fn-strong { font-weight: 700; }
.td-right { text-align: right; }

/* ── Evidence tables ── */
.hits-section   { margin-top: 10px; }
.hits-group     { margin-bottom: 10px; }
.hits-group-label {
  font-size: 0.78em; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; margin-bottom: 3px;
}
.two-label  { color: #5b21b6; }
.one-label  { color: #065f46; }
.hits-table { margin-bottom: 0; }
.hits-table td { padding: 3px 8px; }
.no-hits { color: #94a3b8; font-style: italic; font-size: 0.88em; }
.hidden-note { font-size: 0.8em; color: #94a3b8; font-style: italic; padding: 2px 8px; }

/* ── Omitted phages footer ── */
.omitted-details { margin-top: 8px; }
.omitted-summary {
  font-size: 0.78em; color: #94a3b8; cursor: pointer; list-style: none;
  padding: 4px 2px;
}
.omitted-summary::-webkit-details-marker { display: none; }
.omitted-summary::marker { display: none; }
.omitted-body { font-size: 0.78em; color: #64748b; padding: 4px 2px 0; }
.omitted-row { margin-bottom: 3px; }
.omitted-label { font-weight: 600; color: #94a3b8; margin-right: 4px; }

/* ── Section headings ── */
.section-heading {
  font-size: 0.72em; font-weight: 700; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.08em;
  margin: 28px 0 10px; padding-bottom: 5px;
  border-bottom: 1px solid #e2e8f0;
}
.section-heading:first-child { margin-top: 0; }

/* ── Intro paragraph ── */
.report-intro {
  font-size: 0.88em; color: #475569; line-height: 1.65;
  margin: 0 0 24px; max-width: 820px;
}
.report-intro strong { color: #334155; }

/* ── Shared ── */
table { border-collapse: collapse; width: 100%; font-size: 0.84em; margin-bottom: 10px; }
th {
  padding: 5px 9px; background: #1e293b; color: #f8fafc;
  text-align: left; font-weight: 600;
}
td { padding: 4px 9px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.fn-dim    { color: #94a3b8; font-style: italic; }
.td-center { text-align: center; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
.draft-flag { font-size: 0.75em; color: #64748b; }

/* ── Corroborated function row (appears on both flanks, real or chimeric) ── */
.tr-corroborated td { background: #f0fdf4; }

/* ── Sortable tables ── */
th { cursor: pointer; user-select: none; }
th[data-sort="asc"]::after  { content: ' ▲'; font-size: 0.75em; opacity: 0.7; }
th[data-sort="desc"]::after { content: ' ▼'; font-size: 0.75em; opacity: 0.7; }

/* ── Print ── */
@media print {
  body { font-size: 11px; padding: 0; max-width: none; }
  #toc { display: none; }
  details, .phage-details { display: block !important; }
  .card-header, .phage-summary { cursor: default; }
  .orpham-card { page-break-inside: avoid; }
  .phage-details { page-break-inside: avoid; border: 1px solid #ccc; }
  .cluster-section { page-break-before: always; }
  .cluster-section:first-child { page-break-before: auto; }
  a { color: inherit; text-decoration: none; }
  .one-flank-group { display: block !important; }
}
"""


# ---------------------------------------------------------------------------
# Small rendering helpers
# ---------------------------------------------------------------------------


def escape(text: object) -> str:
    return _html.escape(str(text) if text is not None else "")


def _dir_tag(direction: str) -> str:
    if direction == "reverse":
        return '<span class="dir-rev" title="Reverse strand">←</span>'
    return '<span class="dir-fwd" title="Forward strand">→</span>'


def _pham_link(pham: str | None) -> str:
    if not pham:
        return "—"
    url = _PHAGESDB_PHAM.format(escape(pham))
    return f'<a href="{url}" target="_blank">{escape(pham)}</a>'


def _phage_link(phage_id: str, is_draft: bool = False) -> str:
    url = _PHAGESDB_PHAGE.format(escape(phage_id))
    draft = ' <span class="draft-flag">🚧</span>' if is_draft else ""
    return f'<a href="{url}" target="_blank">{escape(phage_id)}</a>{draft}'


def _section_heading(text: str) -> str:
    return f'<h3 class="section-heading">{escape(text)}</h3>'


def _stat(cls: str, label: str, n: int) -> str:
    return f'<div class="stat {cls}"><b>{n}</b> {label}</div>'


def _phage_anchor(phage_id: str) -> str:
    return f"phage-{phage_id.replace(' ', '-')}"


def _orpham_anchor(phage_id: str, gene_number: str) -> str:
    safe = f"{phage_id}-{gene_number}".replace(" ", "-")
    return f"orpham-{safe}"


def _gene_tag(phage_id: str, gene_number: str) -> str:
    """Compact 'Phage_Gene' identifier e.g. 'Trixie_7'."""
    return f"{phage_id}_{gene_number}"


# ---------------------------------------------------------------------------
# Orpham-card sub-renderers
# ---------------------------------------------------------------------------


def _render_tally_table(tally_sorted: list, one_fns_sorted: list, both_fns: set) -> str:
    """Compact table of hit counts broken down by two-sided / ↑ only / ↓ only."""
    two_dict = dict(tally_sorted)
    one_dict = dict(one_fns_sorted)
    all_fns  = list(dict.fromkeys(
        [fn for fn, _ in tally_sorted] +
        [fn for fn, _ in one_fns_sorted]
    ))
    if not all_fns:
        return ""

    col_two = sum(two_dict.values())
    col_up  = sum(c["up"] for c in one_dict.values())
    col_dn  = sum(c["dn"] for c in one_dict.values())
    total   = col_two + col_up + col_dn

    def _n(v: int, col_total: int) -> str:
        if not v:
            return '<span class="fn-dim">—</span>'
        pct = round(100 * v / col_total) if col_total else 0
        return f'{v} <span class="fn-dim">({pct}%)</span>'

    rows_html = ""
    for fn in all_fns:
        inf  = is_informative(fn)
        two  = two_dict.get(fn, 0)
        up   = one_dict.get(fn, {}).get("up", 0)
        dn   = one_dict.get(fn, {}).get("dn", 0)
        fn_cls  = ' class="tally-fn-strong"' if inf else ' class="fn-dim"'
        row_cls = ' class="tr-corroborated"' if (inf and fn in both_fns) else ""
        rows_html += (
            f"<tr{row_cls}>"
            f"<td{fn_cls}>{escape(fn_display(fn))}</td>"
            f'<td class="td-right">{_n(two, col_two)}</td>'
            f'<td class="td-right">{_n(up, col_up)}</td>'
            f'<td class="td-right">{_n(dn, col_dn)}</td>'
            f"</tr>"
        )
    return (
        f'<div class="tally-section">'
        f'<div class="tally-section-label">Function tally (n={total})</div>'
        f'<table class="hits-table"><thead><tr>'
        f'<th>Function</th>'
        f'<th class="td-right">Two-sided</th>'
        f'<th class="td-right">↑ only</th>'
        f'<th class="td-right">↓ only</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table>'
        f'</div>'
    )


def _hit_rows(rows: list[dict], show_flank: bool = False) -> tuple[str, int]:
    """Render informative hits as <tr> elements; return (html, n_hidden)."""
    informative = [r for r in rows if is_informative(r["gene_function"])]
    hidden = len(rows) - len(informative)
    tbody = ""
    for r in informative:
        flank_td = ""
        if show_flank:
            sym = "↑" if r["up_match"] else "↓"
            flank_td = f'<td class="td-center fn-dim">{sym}</td>'
        phage_url = _PHAGESDB_PHAGE.format(escape(r["phage"]))
        tag = _gene_tag(r["phage"], r["gene_number"])
        pham_title = f'pham {r["candidate_pham"]}' if r["candidate_pham"] else "orpham"
        draft_flag = " 🚧" if r["is_draft"] else ""
        tbody += (
            f"<tr>{flank_td}"
            f'<td class="fn-dim" style="white-space:nowrap">{escape(r["cluster"])}</td>'
            f'<td style="white-space:nowrap">'
            f'<a href="{phage_url}" target="_blank" title="{escape(pham_title)}">'
            f'{escape(tag)}</a>{escape(draft_flag)}</td>'
            f'<td class="fn-dim">{_pham_link(r["candidate_pham"])}</td>'
            f"<td>{escape(fn_display(r['gene_function']))}</td>"
            f"</tr>"
        )
    return tbody, hidden


def _render_hits_table(hits: list[dict]) -> str:
    """Render syntenic hits as simple tables, informative-only, by flank type."""
    if not hits:
        return '<p class="no-hits">No syntenic hits found.</p>'

    two_sided = [r for r in hits if r["two_sided"]]
    up_only   = [r for r in hits if r["up_match"] and not r["two_sided"]]
    dn_only   = [r for r in hits if r["dn_match"] and not r["two_sided"]]

    out = ""

    if two_sided:
        tbody, hidden = _hit_rows(two_sided)
        hidden_note = (
            f'<tr><td colspan="4" class="hidden-note">'
            f'+ {hidden} NKF/hypothetical hit{"s" if hidden != 1 else ""} not shown'
            f'</td></tr>' if hidden else ""
        )
        out += (
            f'<div class="hits-group">'
            f'<div class="hits-group-label two-label">↑↓ two-flank ({len(two_sided)})</div>'
            f'<table class="hits-table"><thead><tr>'
            f'<th>Subcluster</th><th>Gene</th><th>Pham</th><th>Function</th>'
            f'</tr></thead><tbody>{tbody}{hidden_note}</tbody></table>'
            f'</div>'
        )

    one_count = len(up_only) + len(dn_only)
    if one_count:
        up_body, up_hidden = _hit_rows(up_only, show_flank=True)
        dn_body, dn_hidden = _hit_rows(dn_only, show_flank=True)
        tbody  = up_body + dn_body
        hidden = up_hidden + dn_hidden
        hidden_note = (
            f'<tr><td colspan="5" class="hidden-note">'
            f'+ {hidden} NKF/hypothetical hit{"s" if hidden != 1 else ""} not shown'
            f'</td></tr>' if hidden else ""
        )
        inner = (
            f'<table class="hits-table"><thead><tr>'
            f'<th>Flank</th><th>Subcluster</th><th>Gene</th><th>Pham</th><th>Function</th>'
            f'</tr></thead><tbody>{tbody}{hidden_note}</tbody></table>'
            if tbody or hidden_note else
            '<p class="no-hits" style="margin:4px 0">All one-flank hits are NKF/hypothetical.</p>'
        )
        out += (
            f'<div class="hits-group">'
            f'<div class="hits-group-label one-label">↑ or ↓ one-flank ({one_count})</div>'
            f'{inner}'
            f'</div>'
        )

    return f'<div class="hits-section">{out}</div>'


def _render_orpham_card(o: dict, phage_id: str) -> str:
    n2, n1    = o["n_two_sided"], o["n_one_sided"]
    direction = o["direction"]
    start = str(o["start"]).replace("None", "?")
    stop  = str(o["stop"]).replace("None", "?")

    pham_span = (
        f'<span class="gene-pham">pham {_pham_link(o["pham_name"])}</span>'
        if o["pham_name"] else ""
    )
    up_badge = (
        f'<span class="flank-badge">↑ {_pham_link(o["ref_up_pham"])}'
        + (f'<span class="fn-dim"> {escape(o["ref_up_func"])}</span>' if o["ref_up_func"] else "")
        + "</span>"
        if o["ref_up_pham"] else
        '<span class="flank-badge fn-dim">↑ —</span>'
    )
    dn_badge = (
        f'<span class="flank-badge">↓ {_pham_link(o["ref_dn_pham"])}'
        + (f'<span class="fn-dim"> {escape(o["ref_dn_func"])}</span>' if o["ref_dn_func"] else "")
        + "</span>"
        if o["ref_dn_pham"] else
        '<span class="flank-badge fn-dim">↓ —</span>'
    )
    count_badges = (
        (f'<span class="badge badge-two">{n2} two-flank</span>' if n2 > 0 else "") +
        (f'<span class="badge badge-one">{n1} one-flank</span>' if n1 > 0 else "")
    )

    assigned_fn_badge = (
        f'<span class="assigned-function">{escape(fn_display(o["gene_function"]))}</span>'
        if is_informative(o["gene_function"]) else ""
    )
    anchor = _orpham_anchor(phage_id, o["gene_number"])

    summary_el = (
        f'<summary class="card-header">'
        f'<div>'
        f'<span class="gene-title" id="{anchor}">Gene {escape(o["gene_number"])}</span>'
        f'{assigned_fn_badge}'
        f'<span class="gene-pos">{escape(start)}–{escape(stop)} bp</span>'
        f'{_dir_tag(direction)}'
        f'{pham_span}'
        f'</div>'
        f'<div class="badges">{up_badge}{dn_badge}{count_badges}</div>'
        f'</summary>'
    )
    body = (
        f'<div class="card-body">'
        f'{_render_tally_table(o["tally_sorted"], o["one_fns_sorted"], o["both_fns"])}'
        f'{_render_hits_table(o["hits"])}'
        f'</div>'
    )
    return f'<div class="orpham-card" id="card-{anchor}"><details>{summary_el}{body}</details></div>'


# ---------------------------------------------------------------------------
# Global results summary table
# ---------------------------------------------------------------------------


def _top_fn(o: dict) -> str:
    """Return the top informative function for an orpham result, or ''."""
    for fn, _ in o["tally_sorted"]:
        if is_informative(fn):
            return fn_display(fn)
    for fn, counts in o["one_fns_sorted"]:
        if is_informative(fn) and counts["up"] > 0 and counts["dn"] > 0:
            return fn_display(fn)
    return ""


def _results_table(
    rows: list[tuple[str, str, dict]],
    title: str,
    title_cls: str,
    phage_is_draft: dict[str, bool],
) -> str:
    """Render one results sub-table (two-flank or one-flank section).

    Each row is (phage_id, subcluster, orpham_result_dict).
    """
    thead = (
        "<thead><tr>"
        "<th>Subcluster</th>"
        "<th>Phage</th>"
        "<th>Gene (position)</th>"
        "<th>Assigned function</th>"
        "<th>Synteny-suggested function</th>"
        "</tr></thead>"
    )
    tbody = ""
    for phage_id, subcluster, o in rows:
        anchor      = _orpham_anchor(phage_id, o["gene_number"])
        start       = o["start"] if o["start"] is not None else "?"
        stop        = o["stop"]  if o["stop"]  is not None else "?"
        draft_em    = " 🚧" if phage_is_draft.get(phage_id, False) else ""
        assigned    = o.get("gene_function", "")
        assigned_cell = (
            f'<td>{escape(fn_display(assigned))}</td>'
            if is_informative(assigned)
            else '<td class="fn-dim">—</td>'
        )
        top_fn      = _top_fn(o)
        top_fn_cell = f'<td>{escape(top_fn)}</td>' if top_fn else '<td class="fn-dim">—</td>'
        tbody += (
            f"<tr>"
            f'<td class="fn-dim" style="white-space:nowrap">{escape(subcluster)}</td>'
            f'<td><a href="#{_phage_anchor(phage_id)}">{escape(phage_id)}</a>{draft_em}</td>'
            f'<td><a href="#card-{anchor}">{escape(o["gene_number"])}</a>'
            f' <span class="fn-dim">({escape(str(start))}–{escape(str(stop))} bp)</span></td>'
            f"{assigned_cell}"
            f"{top_fn_cell}"
            f"</tr>"
        )
    return (
        f'<h3 class="section-title {title_cls}">{title} ({len(rows)})</h3>'
        f'<table class="summary-table">{thead}<tbody>{tbody}</tbody></table>'
    )


def _render_global_results_table(
    cluster_data: dict[str, list[tuple[str, str, list[dict], dict]]],
    phage_is_draft: dict[str, bool],
) -> str:
    all_rows: list[tuple[str, str, dict]] = [
        (phage_id, cs or cluster, o)
        for cluster, entries in cluster_data.items()
        for phage_id, cs, orpham_results, _ in entries
        for o in orpham_results
    ]

    if not all_rows:
        return ""

    two_rows = [(pid, sc, o) for pid, sc, o in all_rows if o["n_two_sided"] > 0]
    one_rows = [(pid, sc, o) for pid, sc, o in all_rows if o["n_two_sided"] == 0 and o["n_one_sided"] > 0]

    out = ""
    if two_rows:
        out += _results_table(two_rows, "↑↓ Two-flank evidence", "two-label", phage_is_draft)
    if one_rows:
        out += _results_table(one_rows, "↑ or ↓ One-flank evidence only", "one-label", phage_is_draft)
    return out


# ---------------------------------------------------------------------------
# Phage section renderer
# ---------------------------------------------------------------------------


def _phage_mini_stats(summary: dict, n_shown: int) -> str:
    stats = (
        f'<span class="phage-stat">{summary["total_genes"]} genes</span>'
        f'<span class="phage-stat phage-stat-purple">{summary["total_orphams"]} orphams</span>'
    )
    if n_shown:
        stats += f'<span class="phage-stat phage-stat-green">{n_shown} insight{"s" if n_shown != 1 else ""}</span>'
    return f'<span class="phage-stats">{stats}</span>'


def _render_phage_section(phage_id: str, cs: str, orpham_results: list[dict], summary: dict) -> str:
    n_shown     = summary["with_informative"]
    has_results = n_shown > 0

    if has_results:
        cards = "\n".join(_render_orpham_card(o, phage_id) for o in orpham_results)
        body_content = cards
    else:
        body_content = '<p class="phage-no-results">No orphams with strong informative evidence.</p>'

    cs_span = f'<span class="phage-cs">{escape(cs)}</span>' if cs else ""

    return (
        f'<details class="phage-details" id="{_phage_anchor(phage_id)}">'
        f'<summary class="phage-summary">'
        f'<span><span class="phage-name">{_phage_link(phage_id)}</span>{cs_span}</span>'
        f'{_phage_mini_stats(summary, n_shown)}'
        f'</summary>'
        f'<div class="phage-body">{body_content}</div>'
        f'</details>'
    )


# ---------------------------------------------------------------------------
# Cluster section renderer
# ---------------------------------------------------------------------------


def _render_omitted_footer(
    no_orphams: list[str], no_results: list[str]
) -> str:
    """Collapsed footer listing phages omitted from the evidence section."""
    if not no_orphams and not no_results:
        return ""
    total = len(no_orphams) + len(no_results)
    parts = []
    if no_orphams:
        parts.append(f"{len(no_orphams)} with no orphams")
    if no_results:
        parts.append(f"{len(no_results)} with orphams but no informative results")
    summary_text = f"{total} phage{'s' if total != 1 else ''} omitted — {', '.join(parts)}"

    body = ""
    if no_orphams:
        names = ", ".join(escape(p) for p in no_orphams)
        body += (
            f'<div class="omitted-row">'
            f'<span class="omitted-label">No orphams:</span>{names}'
            f'</div>'
        )
    if no_results:
        names = ", ".join(escape(p) for p in no_results)
        body += (
            f'<div class="omitted-row">'
            f'<span class="omitted-label">Orphams, no informative results:</span>{names}'
            f'</div>'
        )
    return (
        f'<details class="omitted-details">'
        f'<summary class="omitted-summary">{escape(summary_text)}</summary>'
        f'<div class="omitted-body">{body}</div>'
        f'</details>'
    )


def _render_cluster_section(cluster: str, phage_entries: list[tuple[str, str, list[dict], dict]]) -> str:
    shown      = [(pid, cs, r, s) for pid, cs, r, s in phage_entries if s["with_informative"] > 0]
    no_orphams = [pid for pid, _, _, s in phage_entries if s["total_orphams"] == 0]
    no_results = [pid for pid, _, _, s in phage_entries
                  if s["total_orphams"] > 0 and s["with_informative"] == 0]

    n_phages = len(phage_entries)
    n_shown  = len(shown)
    cs_badge = (
        f'<span class="cs-badge">{n_phages} phage{"s" if n_phages != 1 else ""}'
        f'{f", {n_shown} with results" if n_shown else ""}</span>'
    )
    phage_sections = "\n".join(
        _render_phage_section(pid, cs, results, summary)
        for pid, cs, results, summary in shown
    )
    omitted = _render_omitted_footer(no_orphams, no_results)
    return (
        f'<details class="cluster-section" id="cluster-{escape(cluster)}" open>'
        f'<summary class="cluster-heading">'
        f'Cluster {escape(cluster or "Singletons")}{cs_badge}'
        f'</summary>'
        f'<div class="cluster-content">{phage_sections}{omitted}</div>'
        f'</details>'
    )


# ---------------------------------------------------------------------------
# TOC
# ---------------------------------------------------------------------------


def _render_toc(cluster_data: dict[str, list[tuple[str, str, list, dict]]]) -> str:
    items = []
    for cluster, phage_entries in cluster_data.items():
        cluster_label = cluster or "Singletons"
        cluster_href = f"#cluster-{cluster_label}"
        phage_links = " · ".join(
            f'<a href="#{_phage_anchor(pid)}" class="has-results">{escape(pid)}</a>'
            if results else
            f'<span class="toc-phage-omitted">{escape(pid)}</span>'
            for pid, _, results, _ in phage_entries
        )
        items.append(
            f'<div class="toc-cluster">'
            f'<a href="{cluster_href}">{escape(cluster_label)}</a>'
            f'<div class="toc-phages">{phage_links}</div>'
            f'</div>'
        )
    return (
        f'<div id="toc"><h3>Contents</h3>'
        f'<div class="toc-clusters">{"".join(items)}</div></div>'
    )


# ---------------------------------------------------------------------------
# Overall summary bar
# ---------------------------------------------------------------------------


def _render_overall_summary(cluster_data: dict[str, list[tuple[str, str, list, dict]]]) -> str:
    total_phages = sum(len(v) for v in cluster_data.values())
    phages_with = sum(
        1 for entries in cluster_data.values()
        for _, _, results, _ in entries if results
    )
    total_orphams = sum(
        s["total_orphams"]
        for entries in cluster_data.values()
        for _, _, _, s in entries
    )
    total_shown = sum(
        s["with_informative"]
        for entries in cluster_data.values()
        for _, _, _, s in entries
    )
    return (
        '<div class="summary">'
        + _stat("stat-slate",  "phages scanned",             total_phages)
        + _stat("stat-blue",   "phages with results",        phages_with)
        + _stat("stat-orange", "orphams analyzed",            total_orphams)
        + _stat("stat-green",  "orphams with informative results", total_shown)
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_CSV_FIELDS = [
    "phage_id", "cluster", "subcluster", "is_draft",
    "gene_number", "pham_name", "direction", "start", "stop", "gene_length",
    "ref_up_pham", "ref_dn_pham", "ref_up_func", "ref_dn_func",
    "n_two_flank", "n_one_flank",
    "assigned_function", "synteny_suggested_function", "syntenic_functions",
]


def render_csv(
    phage_results: list[tuple[str, str, str, list[dict], dict]],
    phage_is_draft: dict[str, bool] | None = None,
) -> str:
    """Return CSV text with one row per passing orpham gene across all phages.

    Columns
    -------
    phage_id, cluster, subcluster, is_draft
    gene_number, pham_name, direction, start, stop, gene_length
    ref_up_pham, ref_dn_pham, ref_up_func, ref_dn_func
    n_two_flank, n_one_flank
    assigned_function         — gene's own phamerator annotation (blank if NKF/hypothetical)
    synteny_suggested_function — top-ranked informative function from the synteny analysis
    syntenic_functions        — pipe-separated set of all corroborating functions (both_fns)
    """
    _is_draft = phage_is_draft or {}
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for phage_id, cluster, cs, orpham_results, _ in phage_results:
        for o in orpham_results:
            assigned = o.get("gene_function", "")
            both_sorted = sorted(o["both_fns"])
            writer.writerow({
                "phage_id":                   phage_id,
                "cluster":                    cluster,
                "subcluster":                 cs,
                "is_draft":                   int(_is_draft.get(phage_id, False)),
                "gene_number":                o["gene_number"],
                "pham_name":                  o["pham_name"],
                "direction":                  o["direction"],
                "start":                      o["start"] if o["start"] is not None else "",
                "stop":                       o["stop"]  if o["stop"]  is not None else "",
                "gene_length":                o["gene_length"],
                "ref_up_pham":                o["ref_up_pham"] or "",
                "ref_dn_pham":                o["ref_dn_pham"] or "",
                "ref_up_func":                fn_display(o["ref_up_func"]) if o["ref_up_func"] else "",
                "ref_dn_func":                fn_display(o["ref_dn_func"]) if o["ref_dn_func"] else "",
                "n_two_flank":                o["n_two_sided"],
                "n_one_flank":                o["n_one_sided"],
                "assigned_function":          fn_display(assigned) if is_informative(assigned) else "",
                "synteny_suggested_function": _top_fn(o),
                "syntenic_functions":         "|".join(fn_display(f) for f in both_sorted),
            })
    return buf.getvalue()


def render_html(
    phage_results: list[tuple[str, str, str, list[dict], dict]],
    dataset: str,
    patterns: list[str],
    phage_is_draft: dict[str, bool] | None = None,
) -> str:
    """Render the full HTML report.

    Args:
      phage_results  list of (phage_id, cluster, cluster_subcluster, orpham_results, summary)
      dataset        dataset name shown in the subtitle
      patterns       the cluster patterns supplied on the CLI (for the subtitle)
    """
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pattern_str = ", ".join(patterns)
    if len(phage_results) == 1 and phage_results[0][0] == pattern_str:
        title_str = f"Phage {pattern_str}"
    elif pattern_str.lower() == "all":
        title_str = "All Clusters"
    else:
        title_str = f"Cluster {pattern_str}"

    # Group by cluster (preserving order)
    cluster_data: dict[str, list] = {}
    for phage_id, cluster, cs, orpham_results, summary in phage_results:
        cluster_data.setdefault(cluster, []).append((phage_id, cs, orpham_results, summary))

    _is_draft = phage_is_draft or {}
    overall_html       = _render_overall_summary(cluster_data)
    results_table_html = _render_global_results_table(cluster_data, _is_draft)
    toc_html           = _render_toc(cluster_data)
    body_html          = "\n".join(
        _render_cluster_section(cluster, entries)
        for cluster, entries in cluster_data.items()
    )

    intro = (
        '<p class="report-intro">'
        "<strong>Orpham genes</strong> are phage-encoded genes whose protein family (pham) "
        "is found in only one phage in the dataset — they have no known homologs and carry "
        "no direct function annotation. This report searches for <strong>syntenic evidence</strong> "
        "of their putative function: for each orpham, the upstream and downstream flanking phams "
        "are identified, and all other phages carrying those phams are scanned for a gene at the "
        "equivalent syntenic position. The function of that neighboring gene is used as a proxy "
        "for what the orpham might encode. Hits where <strong>both flanks match</strong> "
        "(two-flank) are stronger evidence; hits where <strong>one flank matches</strong> "
        "(one-flank) are also reported. Only orphams with at least one informative "
        "(non-NKF/hypothetical) function assignment are shown."
        "</p>"
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Orpham Synteny Report — {escape(title_str)}</title>\n"
        + (f'<link rel="icon" type="image/png" href="{_FAVICON_B64}">\n' if _FAVICON_B64 else "")
        + f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<h1>🧬 Orpham Synteny Report</h1>\n"
        f'<h2 class="subtitle">{escape(title_str)}'
        f' &nbsp;·&nbsp; Dataset: {escape(dataset)}'
        f' &nbsp;·&nbsp; <span style="font-size:0.88em;color:#94a3b8">Generated {generated}</span>'
        f"</h2>\n"
        f"{_section_heading('Overview')}\n"
        f"{overall_html}\n"
        f"{intro}\n"
        f"{_section_heading('Phage Index')}\n"
        f"{toc_html}\n"
        f"{_section_heading('Results at a Glance')}\n"
        f"{results_table_html}\n"
        f"{_section_heading('Evidence by Phage')}\n"
        f"{body_html}\n"
        "<script>\n"
        "function openTarget(id) {\n"
        "  var target = document.getElementById(id);\n"
        "  if (!target) return null;\n"
        "  var cluster = target.closest('details.cluster-section');\n"
        "  if (cluster) cluster.open = true;\n"
        "  if (target.classList.contains('phage-details')) {\n"
        "    target.open = true;\n"
        "  } else if (target.classList.contains('orpham-card')) {\n"
        "    var phage = target.closest('details.phage-details');\n"
        "    if (phage) phage.open = true;\n"
        "    var gene = target.querySelector('details');\n"
        "    if (gene) gene.open = true;\n"
        "  }\n"
        "  return target;\n"
        "}\n"
        "function scrollTo(target, smooth) {\n"
        "  setTimeout(function() {\n"
        "    target.scrollIntoView({behavior: smooth ? 'smooth' : 'instant', block: 'start'});\n"
        "  }, 50);\n"
        "}\n"
        "document.addEventListener('click', function(e) {\n"
        "  var a = e.target.closest('a[href^=\"#\"]');\n"
        "  if (!a) return;\n"
        "  var id = a.getAttribute('href').slice(1);\n"
        "  var target = openTarget(id);\n"
        "  if (!target) return;\n"
        "  e.preventDefault();\n"
        "  history.pushState(null, '', '#' + id);\n"
        "  scrollTo(target, true);\n"
        "});\n"
        "document.addEventListener('DOMContentLoaded', function() {\n"
        "  var hash = window.location.hash.slice(1);\n"
        "  var target = hash ? openTarget(hash) : null;\n"
        "  if (target) scrollTo(target, false);\n"
        "});\n"
        "// Sortable tables\n"
        "document.querySelectorAll('table').forEach(function(tbl) {\n"
        "  tbl.querySelectorAll('th').forEach(function(th, colIdx) {\n"
        "    th.title = 'Click to sort';\n"
        "    var dir = 0;\n"
        "    th.addEventListener('click', function() {\n"
        "      var asc = dir !== 1;\n"
        "      tbl.querySelectorAll('th').forEach(function(h) {\n"
        "        h._sortDir = 0; h.removeAttribute('data-sort');\n"
        "      });\n"
        "      dir = asc ? 1 : -1;\n"
        "      th.setAttribute('data-sort', asc ? 'asc' : 'desc');\n"
        "      var tbody = tbl.querySelector('tbody');\n"
        "      if (!tbody) return;\n"
        "      var rows = Array.from(tbody.querySelectorAll('tr'));\n"
        "      rows.sort(function(a, b) {\n"
        "        var aText = (a.cells[colIdx] ? a.cells[colIdx].textContent : '').trim();\n"
        "        var bText = (b.cells[colIdx] ? b.cells[colIdx].textContent : '').trim();\n"
        "        var aNum = parseFloat(aText), bNum = parseFloat(bText);\n"
        "        var cmp = (!isNaN(aNum) && !isNaN(bNum))\n"
        "          ? aNum - bNum\n"
        "          : aText.localeCompare(bText, undefined, {numeric: true, sensitivity: 'base'});\n"
        "        return asc ? cmp : -cmp;\n"
        "      });\n"
        "      rows.forEach(function(r) { tbody.appendChild(r); });\n"
        "    });\n"
        "  });\n"
        "});\n"
        "</script>\n"
        "</body>\n"
        "</html>"
    )
