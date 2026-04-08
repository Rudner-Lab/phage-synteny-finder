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

/* ── Orpham cards (nested inside phage) ── */
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
.dir-fwd    { color: #2563eb; font-weight: 700; margin-left: 4px; }
.dir-rev    { color: #dc2626; font-weight: 700; margin-left: 4px; }
.badges { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 4px; }
.badge {
  padding: 2px 8px; border-radius: 5px; font-size: 0.8em;
  border: 1px solid; white-space: nowrap;
}
.badge-flank  { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
.badge-two    { background: #ede9fe; border-color: #c4b5fd; color: #5b21b6; }
.badge-one    { background: #f0fdf4; border-color: #a7f3d0; color: #065f46; }
.badge-toggle { background: #f8fafc; border-color: #cbd5e1; color: #334155; cursor: pointer; }
.card-body { padding: 10px 12px; border-top: 1px solid #e2e8f0; }

/* ── Tables ── */
table { border-collapse: collapse; width: 100%; font-size: 0.84em; margin-bottom: 10px; }
th {
  padding: 5px 9px; background: #1e293b; color: #f8fafc;
  text-align: left; font-weight: 600;
}
td { padding: 4px 9px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.group-row td {
  background: #f1f5f9; font-weight: 700; color: #334155;
  font-size: 0.82em; padding: 3px 9px; border-top: 2px solid #cbd5e1;
}
.fn-strong { font-weight: 700; }
.fn-dim    { color: #94a3b8; font-style: italic; }
.fn-pct    { color: #94a3b8; font-weight: 400; }
.td-right  { text-align: right; }
.td-center { text-align: center; }
.flank-match { background: #dcfce7; color: #166534; font-weight: 600; text-align: center; }
.flank-miss  { color: #94a3b8; text-align: center; font-style: italic; }
.two-sided-row td { background: #f0fdf4 !important; }
.bg-strong { background: #bbf7d0; }
.bg-medium { background: #dcfce7; }
.bg-light  { background: #f0fdf4; }
.section-label { font-size: 0.82em; color: #64748b; margin: 0 0 5px; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
.draft-flag { font-size: 0.75em; color: #64748b; }
.one-wrap { margin-top: 10px; }

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
  .badge-toggle { display: none; }
  .one-wrap { display: block !important; }
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


# ---------------------------------------------------------------------------
# Orpham-card sub-renderers
# ---------------------------------------------------------------------------


def _render_tally(tally_sorted: list, tally_total: int) -> str:
    if not tally_sorted:
        return ""
    rows_html = ""
    for fn, n in tally_sorted:
        v = n / tally_total if tally_total else 0
        inf = is_informative(fn)
        bg = "bg-strong" if inf and v > 0.50 else "bg-medium" if inf and v > 0.25 else "bg-light" if inf and v > 0.10 else ""
        td_cls = f' class="{bg}"' if bg else ""
        strong = ' class="fn-strong"' if inf and v > 0.25 else ""
        fn_cls = "" if inf else ' class="fn-dim"'
        rows_html += (
            f"<tr{td_cls}>"
            f'<td{fn_cls}><span{strong}>{escape(fn_display(fn))}</span></td>'
            f'<td class="td-right">{n} <span class="fn-pct">({round(100*v)}%)</span></td>'
            f"</tr>"
        )
    return (
        f'<p class="section-label">Central-gene functions with support from'
        f' <strong>both flanks</strong> (n={tally_total} qualifying hits)</p>'
        f"<table><thead><tr><th>Function</th>"
        f'<th style="text-align:right">Hits</th></tr></thead>'
        f"<tbody>{rows_html}</tbody></table>"
    )


def _render_one_flank_section(one_fns_sorted: list, up_count: int, dn_count: int) -> str:
    if not one_fns_sorted or (up_count == 0 and dn_count == 0):
        return ""
    rows_html = ""
    for fn, counts in one_fns_sorted:
        shared = counts["up"] > 0 and counts["dn"] > 0
        inf = is_informative(fn)
        row_cls = ' class="bg-light"' if shared and inf else ""
        fn_cls = ' class="fn-dim"' if not inf else (' class="fn-strong"' if shared else "")
        tick = "✓ " if shared else ""

        def _pct(n: int, total: int) -> str:
            if total == 0:
                return '<td class="td-right fn-dim">n/a</td>'
            if n == 0:
                return '<td class="td-right fn-dim">—</td>'
            return f'<td class="td-right">{n} <span class="fn-pct">({round(100*n/total)}%)</span></td>'

        rows_html += (
            f"<tr{row_cls}><td{fn_cls}>{escape(tick)}{escape(fn_display(fn))}</td>"
            f"{_pct(counts['up'], up_count)}{_pct(counts['dn'], dn_count)}</tr>"
        )
    total_hits = up_count + dn_count
    s = "s" if total_hits != 1 else ""
    label_show = f"▸ Show one-flank functions ({total_hits} hit{s})"
    label_hide = f"▾ Hide one-flank functions ({total_hits} hit{s})"
    onclick = (
        "(function(b){"
        "var w=b.previousElementSibling;"
        "var o=w.style.display==='none';"
        "w.style.display=o?'':'none';"
        f"b.textContent=o?'{label_hide}':'{label_show}';"
        "})(this)"
    )
    return (
        f'<div class="one-wrap" style="display:none">'
        f'<p class="section-label">Central-gene functions from <strong>one-flank</strong>'
        f' hits (✓ = seen in both upstream-matched and downstream-matched subsets)</p>'
        f"<table><thead><tr>"
        f"<th>Function</th>"
        f'<th style="text-align:right">↑ upstream only (n={up_count})</th>'
        f'<th style="text-align:right">↓ downstream only (n={dn_count})</th>'
        f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
        f'<button class="badge badge-toggle one-toggle" onclick="{onclick}">'
        f"{label_show}</button>"
    )


def _render_hits_table(hits: list[dict], ref_up_pham: str | None, ref_dn_pham: str | None) -> str:
    if not hits:
        return '<p style="color:#94a3b8;font-style:italic;font-size:0.88em">No syntenic hits found.</p>'

    two_sided = [r for r in hits if r["two_sided"]]
    one_sided  = [r for r in hits if not r["two_sided"]]

    def _row(r: dict, highlight: bool) -> str:
        row_cls = ' class="two-sided-row"' if highlight else ""
        up_td = (
            f'<td class="flank-match">{escape(r["up_pham"] or "—")}</td>'
            if r["up_match"] else
            f'<td class="flank-miss">{escape(r["up_pham"] or "—")}</td>'
        )
        dn_td = (
            f'<td class="flank-match">{escape(r["dn_pham"] or "—")}</td>'
            if r["dn_match"] else
            f'<td class="flank-miss">{escape(r["dn_pham"] or "—")}</td>'
        )
        pham_td = (
            f'<td class="td-center">{_pham_link(r["candidate_pham"])}</td>'
            if r["candidate_pham"] else
            '<td class="td-center fn-dim">orpham</td>'
        )
        fn_span = (
            f'<br><span class="fn-dim" style="font-size:0.82em">{escape(r["gene_function"])}</span>'
            if r["gene_function"] else ""
        )
        return (
            f"<tr{row_cls}>"
            f"<td>{_phage_link(r['phage'], r['is_draft'])}{fn_span}</td>"
            f'<td class="td-center">{escape(r["gene_number"])}</td>'
            f"{pham_td}"
            f"<td>{escape(r['cluster'])}</td>"
            f'<td class="td-center">{_dir_tag(r["direction"])}</td>'
            f"{up_td}{dn_td}</tr>"
        )

    def _group_rows(rows: list[dict], highlight: bool) -> str:
        groups: dict[str, list] = {}
        for r in rows:
            groups.setdefault(r["cluster"] or "Unknown", []).append(r)
        out = ""
        for cluster, group in sorted(groups.items()):
            label = f"{cluster} ({len(group)} gene{'s' if len(group) != 1 else ''})"
            out += f'<tr class="group-row"><td colspan="7">{escape(label)}</td></tr>'
            out += "".join(_row(r, highlight) for r in group)
        return out

    thead = (
        "<thead><tr>"
        "<th>Phage</th>"
        '<th class="td-center">Gene #</th>'
        '<th class="td-center">Gene pham</th>'
        "<th>Cluster</th>"
        '<th class="td-center">Dir.</th>'
        f'<th>↑ upstream pham<br><small style="font-weight:400;opacity:.7">ref: {escape(ref_up_pham or "—")}</small></th>'
        f'<th>↓ downstream pham<br><small style="font-weight:400;opacity:.7">ref: {escape(ref_dn_pham or "—")}</small></th>'
        "</tr></thead>"
    )

    tbody = ""
    if two_sided:
        tbody += _group_rows(two_sided, highlight=True)
    if one_sided:
        if two_sided:
            tbody += (
                '<tr class="group-row"><td colspan="7">'
                f"── One-flank hits ({len(one_sided)}) ──</td></tr>"
            )
        tbody += _group_rows(one_sided, highlight=False)

    return f"<table>{thead}<tbody>{tbody}</tbody></table>"


def _render_orpham_card(o: dict) -> str:
    n2, n1 = o["n_two_sided"], o["n_one_sided"]
    direction = o["direction"]
    gene_fn = escape(fn_display(o["gene_function"])) if o["gene_function"] else ""

    up_badge = (
        f'<span class="badge badge-flank">↑ {_pham_link(o["ref_up_pham"])}'
        + (f' <span class="fn-dim">{escape(o["ref_up_func"])}</span>' if o["ref_up_func"] else "")
        + "</span>"
        if o["ref_up_pham"] else
        '<span class="badge badge-flank fn-dim">↑ —</span>'
    )
    dn_badge = (
        f'<span class="badge badge-flank">↓ {_pham_link(o["ref_dn_pham"])}'
        + (f' <span class="fn-dim">{escape(o["ref_dn_func"])}</span>' if o["ref_dn_func"] else "")
        + "</span>"
        if o["ref_dn_pham"] else
        '<span class="badge badge-flank fn-dim">↓ —</span>'
    )
    count_badges = (
        (f'<span class="badge badge-two">🔗 {n2} two-flank</span>' if n2 > 0 else "") +
        (f'<span class="badge badge-one">🔀 {n1} one-flank</span>' if n1 > 0 else "")
    )

    start = str(o["start"]).replace("None", "?")
    stop  = str(o["stop"]).replace("None", "?")
    pham_span = (
        f'<span style="margin-left:8px;font-size:0.82em;color:#94a3b8">'
        f'pham {_pham_link(o["pham_name"])}</span>'
        if o["pham_name"] else ""
    )

    gene_fn_span = f'<span class="gene-fn">{gene_fn}</span>' if gene_fn else ""
    summary_el = (
        f'<summary class="card-header">'
        f'<div>'
        f'<span class="gene-title">Gene {escape(o["gene_number"])}</span>'
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
        f'{_render_tally(o["tally_sorted"], o["tally_total"])}'
        f'{_render_one_flank_section(o["one_fns_sorted"], o["up_only_count"], o["dn_only_count"])}'
        f'{_render_hits_table(o["hits"], o["ref_up_pham"], o["ref_dn_pham"])}'
        f'</div>'
    )
    return f'<div class="orpham-card"><details open>{summary_el}{body}</details></div>'


# ---------------------------------------------------------------------------
# Phage section renderer
# ---------------------------------------------------------------------------


def _phage_anchor(phage_id: str) -> str:
    return f"phage-{phage_id.replace(' ', '-')}"


def _render_phage_section(phage_id: str, cs: str, orpham_results: list[dict], summary: dict) -> str:
    n_shown = summary["with_informative"]
    has_results = n_shown > 0

    mini_summary = (
        '<div class="summary">'
        + _stat("stat-slate",  "total genes",   summary["total_genes"])
        + _stat("stat-orange", "orphams",        summary["total_orphams"])
        + _stat("stat-green",  "shown",          n_shown)
        + "</div>"
    )

    if has_results:
        cards = "\n".join(_render_orpham_card(o) for o in orpham_results)
        body_content = mini_summary + cards
    else:
        body_content = (
            mini_summary +
            '<p class="phage-no-results">No orphams with strong informative evidence.</p>'
        )

    phage_link = _phage_link(phage_id)
    phagesdb_url = f"https://phagesdb.org/phages/{escape(phage_id)}/"
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
        f'<span><span class="phage-name">{phage_link}</span>{cs_span}{orpham_count_span}</span>'
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

    toc_html     = _render_toc(cluster_data)
    overall_html = _render_overall_summary(cluster_data)
    body_html    = "\n".join(
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
        '<p style="font-size:0.82em;color:#64748b;margin:-12px 0 24px">'
        "Showing only orphams with informative (non-NKF/hypothetical) evidence from "
        "<strong>two-flank</strong> hits or convergent <strong>matching one-flank</strong> hits. "
        "Green TOC links = phages with results. Phage rows with green background = two-flank support."
        "</p>\n"
        f"{toc_html}\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>"
    )
