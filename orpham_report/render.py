"""
render.py — HTML rendering for the cluster-level orpham synteny report.

Public entry point: ``render_html(phage_results, dataset, patterns)``

``phage_results`` is a list of PhageResult namedtuples (or equivalent dicts):
  phage_id, cluster, cluster_subcluster, orpham_results, summary
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timezone

from .analysis import fn_display, is_informative

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
.toc-cluster .toc-phages a { color: #475569; font-weight: 400; }
.toc-cluster .toc-phages a.has-results { color: #15803d; font-weight: 600; }

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
.check-yes  { color: #15803d; font-weight: 700; }
.check-one  { color: #5b21b6; font-weight: 700; }
.check-no   { color: #cbd5e1; }

/* ── Cluster sections ── */
.cluster-section { margin-bottom: 40px; }
.cluster-heading {
  font-size: 1.1em; font-weight: 700; color: #1e293b;
  padding: 8px 0 6px; border-bottom: 2px solid #e2e8f0; margin: 0 0 14px;
}
.cluster-heading .cs-badge {
  display: inline-block; padding: 1px 8px; border-radius: 5px;
  background: #f1f5f9; border: 1px solid #cbd5e1;
  font-size: 0.82em; font-weight: 400; color: #475569; margin-left: 8px;
}

/* ── Phage <details> ── */
.phage-details { margin-bottom: 10px; border: 1px solid #e2e8f0; border-radius: 8px; }
.phage-summary {
  padding: 9px 14px; display: flex; justify-content: space-between;
  align-items: center; flex-wrap: wrap; gap: 6px;
  cursor: pointer; user-select: none; list-style: none;
  background: #f8fafc; border-radius: 8px;
}
.phage-summary::-webkit-details-marker { display: none; }
.phage-summary::marker { display: none; }
details[open] > .phage-summary { border-radius: 8px 8px 0 0; }
.phage-name { font-weight: 700; color: #1e293b; }
.phage-cs   { font-size: 0.82em; color: #94a3b8; margin-left: 6px; }
.phage-body { padding: 12px 14px; border-top: 1px solid #e2e8f0; }
.phage-no-results { padding: 8px 0; color: #94a3b8; font-style: italic; font-size: 0.88em; }

/* ── Orpham cards ── */
.orpham-card {
  margin-bottom: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
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
  background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534;
  white-space: nowrap;
}
.badge-two  { background: #ede9fe; border-color: #c4b5fd; color: #5b21b6; }
.badge-one  { background: #f0fdf4; border-color: #a7f3d0; color: #065f46; }
.card-body  { padding: 10px 12px; border-top: 1px solid #e2e8f0; }

/* ── Inline function tally ── */
.tally-inline {
  font-size: 0.82em; margin-bottom: 8px;
  padding: 4px 8px; background: #f0fdf4; border-radius: 4px; border: 1px solid #bbf7d0;
}
.tally-label    { font-weight: 700; margin-right: 6px; color: #166534; }
.tally-fn-strong { font-weight: 700; color: #166534; }
.tally-fn-dim   { color: #94a3b8; font-style: italic; }

/* ── Compact hit chips ── */
.compact-hits   { margin-top: 6px; }
.hits-group     { margin-bottom: 8px; }
.hits-group-label {
  font-size: 0.78em; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; margin-bottom: 4px;
}
.two-label  { color: #5b21b6; }
.one-label  { color: #065f46; cursor: pointer; display: block; }
.one-label::-webkit-details-marker { display: none; }
.one-label::marker { display: none; }
.one-flank-group { border: none; outline: none; }
.flank-sub-label { font-size: 0.78em; color: #64748b; margin: 4px 0 2px 4px; }
.cluster-row {
  display: flex; align-items: flex-start; gap: 5px;
  flex-wrap: wrap; margin-bottom: 3px; padding-left: 4px;
}
.cluster-tag {
  font-size: 0.78em; font-weight: 700; color: #475569;
  background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px;
  padding: 1px 6px; white-space: nowrap; margin-top: 2px; flex-shrink: 0;
}
.chips  { display: flex; flex-wrap: wrap; gap: 4px; }
a.hit-chip {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 7px; background: #f8fafc; border: 1px solid #cbd5e1;
  border-radius: 4px; font-size: 0.82em; text-decoration: none; color: #1e293b;
}
a.hit-chip:hover { background: #e2e8f0; text-decoration: none; }
.chip-fn { color: #64748b; font-style: italic; font-size: 0.9em; }
.no-hits { color: #94a3b8; font-style: italic; font-size: 0.88em; }

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


def _render_inline_tally(tally_sorted: list) -> str:
    """One-line function summary for two-flank hits."""
    if not tally_sorted:
        return ""
    parts = []
    for fn, n in tally_sorted:
        inf = is_informative(fn)
        cls = "tally-fn-strong" if inf else "tally-fn-dim"
        parts.append(
            f'<span class="{cls}">{escape(fn_display(fn))}</span>&thinsp;×{n}'
        )
    return (
        f'<div class="tally-inline">'
        f'<span class="tally-label">↑↓ functions</span>'
        f'{"&ensp;·&ensp;".join(parts)}'
        f'</div>'
    )


def _chips_by_cluster(rows: list[dict]) -> str:
    """Render rows as chip clusters: 'ClusterTag  chip chip chip'."""
    clusters: dict[str, list[dict]] = {}
    for r in rows:
        clusters.setdefault(r["cluster"] or "—", []).append(r)

    out = ""
    for cl, group in sorted(clusters.items()):
        chips = ""
        for r in group:
            fn = fn_display(r["gene_function"]) if r["gene_function"] else ""
            fn_span = f'<span class="chip-fn">{escape(fn)}</span>' if fn else ""
            draft_flag = " 🚧" if r["is_draft"] else ""
            phage_url = _PHAGESDB_PHAGE.format(escape(r["phage"]))
            tag = _gene_tag(r["phage"], r["gene_number"])
            pham_title = f'pham {r["candidate_pham"]}' if r["candidate_pham"] else "orpham"
            chips += (
                f'<a class="hit-chip" href="{phage_url}" target="_blank"'
                f' title="{escape(pham_title)}">'
                f'{escape(tag)}{escape(draft_flag)}'
                f'{fn_span}</a>'
            )
        out += (
            f'<div class="cluster-row">'
            f'<span class="cluster-tag">{escape(cl)}</span>'
            f'<span class="chips">{chips}</span>'
            f'</div>'
        )
    return out


def _render_compact_hits(hits: list[dict]) -> str:
    """Render syntenic hits as compact chips grouped by flank type then cluster."""
    if not hits:
        return '<p class="no-hits">No syntenic hits found.</p>'

    two_sided = [r for r in hits if r["two_sided"]]
    up_only   = [r for r in hits if r["up_match"] and not r["two_sided"]]
    dn_only   = [r for r in hits if r["dn_match"] and not r["two_sided"]]

    out = ""

    if two_sided:
        out += (
            f'<div class="hits-group">'
            f'<div class="hits-group-label two-label">↑↓ two-flank ({len(two_sided)})</div>'
            f'{_chips_by_cluster(two_sided)}'
            f'</div>'
        )

    one_count = len(up_only) + len(dn_only)
    if one_count:
        inner = ""
        if up_only:
            inner += (
                f'<div class="flank-sub-label">↑ upstream-matched ({len(up_only)})</div>'
                f'{_chips_by_cluster(up_only)}'
            )
        if dn_only:
            inner += (
                f'<div class="flank-sub-label">↓ downstream-matched ({len(dn_only)})</div>'
                f'{_chips_by_cluster(dn_only)}'
            )
        out += (
            f'<details class="hits-group one-flank-group">'
            f'<summary class="hits-group-label one-label">'
            f'↑ or ↓ one-flank ({one_count}) ▸</summary>'
            f'{inner}'
            f'</details>'
        )

    return f'<div class="compact-hits">{out}</div>'


def _render_orpham_card(o: dict, phage_id: str) -> str:
    n2, n1    = o["n_two_sided"], o["n_one_sided"]
    direction = o["direction"]
    gene_fn   = escape(fn_display(o["gene_function"])) if o["gene_function"] else ""

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
        (f'<span class="badge badge-two">🔗 {n2} two-flank</span>' if n2 > 0 else "") +
        (f'<span class="badge badge-one">🔀 {n1} one-flank</span>' if n1 > 0 else "")
    )

    gene_fn_span = f'<span class="gene-fn">{gene_fn}</span>' if gene_fn else ""
    anchor = _orpham_anchor(phage_id, o["gene_number"])

    summary_el = (
        f'<summary class="card-header">'
        f'<div>'
        f'<span class="gene-title" id="{anchor}">Gene {escape(o["gene_number"])}</span>'
        f'<span class="gene-pos">{escape(start)}–{escape(stop)} bp</span>'
        f'{_dir_tag(direction)}'
        f'{gene_fn_span}'
        f'{pham_span}'
        f'</div>'
        f'<div class="badges">{up_badge}{dn_badge}{count_badges}</div>'
        f'</summary>'
    )
    body = (
        f'<div class="card-body">'
        f'{_render_inline_tally(o["tally_sorted"])}'
        f'{_render_compact_hits(o["hits"])}'
        f'</div>'
    )
    return f'<div class="orpham-card" id="card-{anchor}"><details open>{summary_el}{body}</details></div>'


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


def _results_table(rows: list[tuple[str, dict]], title: str, title_cls: str) -> str:
    """Render one results sub-table (two-flank or one-flank section)."""
    thead = (
        "<thead><tr>"
        "<th>Phage</th>"
        "<th>Gene (position)</th>"
        "<th>Top function</th>"
        "</tr></thead>"
    )
    tbody = ""
    for phage_id, o in rows:
        anchor = _orpham_anchor(phage_id, o["gene_number"])
        start  = o["start"] if o["start"] is not None else "?"
        stop   = o["stop"]  if o["stop"]  is not None else "?"
        fn     = _top_fn(o)
        fn_cell = f'<td>{escape(fn)}</td>' if fn else '<td class="fn-dim">—</td>'
        tbody += (
            f"<tr>"
            f'<td><a href="#{_phage_anchor(phage_id)}">{escape(phage_id)}</a></td>'
            f'<td><a href="#card-{anchor}">{escape(o["gene_number"])}</a>'
            f' <span class="fn-dim">({escape(str(start))}–{escape(str(stop))} bp)</span></td>'
            f"{fn_cell}"
            f"</tr>"
        )
    return (
        f'<h3 class="section-title {title_cls}">{title} ({len(rows)})</h3>'
        f'<table class="summary-table"><{thead}<tbody>{tbody}</tbody></table>'
    )


def _render_global_results_table(
    cluster_data: dict[str, list[tuple[str, str, list[dict], dict]]]
) -> str:
    all_rows: list[tuple[str, dict]] = [
        (phage_id, o)
        for entries in cluster_data.values()
        for phage_id, _, orpham_results, _ in entries
        for o in orpham_results
    ]

    if not all_rows:
        return ""

    two_rows = [(pid, o) for pid, o in all_rows if o["n_two_sided"] > 0]
    one_rows = [(pid, o) for pid, o in all_rows if o["n_two_sided"] == 0 and o["n_one_sided"] > 0]

    out = ""
    if two_rows:
        out += _results_table(two_rows, "↑↓ Two-flank evidence", "two-label")
    if one_rows:
        out += _results_table(one_rows, "↑ or ↓ One-flank evidence only", "one-label")
    return out


# ---------------------------------------------------------------------------
# Phage section renderer
# ---------------------------------------------------------------------------


def _render_phage_section(phage_id: str, cs: str, orpham_results: list[dict], summary: dict) -> str:
    n_shown   = summary["with_informative"]
    has_results = n_shown > 0

    mini_summary = (
        '<div class="summary">'
        + _stat("stat-slate",  "total genes",   summary["total_genes"])
        + _stat("stat-orange", "orphams",        summary["total_orphams"])
        + _stat("stat-green",  "shown",          n_shown)
        + "</div>"
    )

    if has_results:
        cards = "\n".join(_render_orpham_card(o, phage_id) for o in orpham_results)
        body_content = mini_summary + cards
    else:
        body_content = (
            mini_summary +
            '<p class="phage-no-results">No orphams with strong informative evidence.</p>'
        )

    cs_span = f'<span class="phage-cs">{escape(cs)}</span>' if cs else ""
    orpham_count_span = (
        f' <span style="font-size:0.82em;color:#15803d;font-weight:600">'
        f'→ {n_shown} result{"s" if n_shown != 1 else ""}</span>'
        if has_results else
        f' <span style="font-size:0.82em;color:#94a3b8">(no results)</span>'
    )

    return (
        f'<details class="phage-details" id="{_phage_anchor(phage_id)}"'
        f'{" open" if has_results else ""}>'
        f'<summary class="phage-summary">'
        f'<span><span class="phage-name">{_phage_link(phage_id)}</span>'
        f'{cs_span}{orpham_count_span}</span>'
        f'</summary>'
        f'<div class="phage-body">{body_content}</div>'
        f'</details>'
    )


# ---------------------------------------------------------------------------
# Cluster section renderer
# ---------------------------------------------------------------------------


def _render_cluster_section(cluster: str, phage_entries: list[tuple[str, str, list[dict], dict]]) -> str:
    n_phages = len(phage_entries)
    n_with_results = sum(1 for _, _, results, _ in phage_entries if results)
    cs_badge = (
        f'<span class="cs-badge">{n_phages} phage{"s" if n_phages != 1 else ""}'
        f'{f", {n_with_results} with results" if n_with_results else ""}</span>'
    )
    heading = (
        f'<div class="cluster-heading" id="cluster-{escape(cluster)}">'
        f'Cluster {escape(cluster or "Singletons")}{cs_badge}</div>'
    )
    phage_sections = "\n".join(
        _render_phage_section(pid, cs, results, summary)
        for pid, cs, results, summary in phage_entries
    )
    return f'<div class="cluster-section">{heading}{phage_sections}</div>'


# ---------------------------------------------------------------------------
# TOC
# ---------------------------------------------------------------------------


def _render_toc(cluster_data: dict[str, list[tuple[str, str, list, dict]]]) -> str:
    items = []
    for cluster, phage_entries in cluster_data.items():
        cluster_label = cluster or "Singletons"
        cluster_href = f"#cluster-{cluster_label}"
        phage_links = " · ".join(
            f'<a href="#{_phage_anchor(pid)}"'
            f'{" class=\"has-results\"" if results else ""}>'
            f'{escape(pid)}</a>'
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
        + _stat("stat-orange", "orphams total",              total_orphams)
        + _stat("stat-green",  "orphams shown (informative)", total_shown)
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_html(
    phage_results: list[tuple[str, str, str, list[dict], dict]],
    dataset: str,
    patterns: list[str],
) -> str:
    """Render the full HTML report.

    Args:
      phage_results  list of (phage_id, cluster, cluster_subcluster, orpham_results, summary)
      dataset        dataset name shown in the subtitle
      patterns       the cluster patterns supplied on the CLI (for the subtitle)
    """
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pattern_str = ", ".join(patterns)
    title_str = f"Cluster {pattern_str}" if pattern_str.lower() != "all" else "All Clusters"

    # Group by cluster (preserving order)
    cluster_data: dict[str, list] = {}
    for phage_id, cluster, cs, orpham_results, summary in phage_results:
        cluster_data.setdefault(cluster, []).append((phage_id, cs, orpham_results, summary))

    overall_html       = _render_overall_summary(cluster_data)
    results_table_html = _render_global_results_table(cluster_data)
    toc_html           = _render_toc(cluster_data)
    body_html          = "\n".join(
        _render_cluster_section(cluster, entries)
        for cluster, entries in cluster_data.items()
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Orpham Synteny Report — {escape(title_str)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<h1>🧬 Orpham Synteny Report</h1>\n"
        f'<h2 class="subtitle">{escape(title_str)}'
        f' &nbsp;·&nbsp; Dataset: {escape(dataset)}'
        f' &nbsp;·&nbsp; <span style="font-size:0.88em;color:#94a3b8">Generated {generated}</span>'
        f"</h2>\n"
        f"{overall_html}\n"
        f"{results_table_html}\n"
        f"{toc_html}\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>"
    )
