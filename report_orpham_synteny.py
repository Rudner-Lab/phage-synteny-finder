#!/usr/bin/env python3
"""
report_orpham_synteny.py
------------------------
Query the local Phamerator SQLite database and generate a static HTML report
of orpham synteny evidence for a given phage.

Only orphams with strong evidence of a real (non-NKF/hypothetical) function
are shown:
  - Two-flank hits: the central-gene function tally includes at least one
    informative function (i.e. supported by genes that match BOTH the
    upstream and downstream pham context of the orpham).
  - Matching one-flank hits: an informative function appears in BOTH the
    upstream-matched subset AND the downstream-matched subset of one-sided
    hits (convergent evidence from each flank independently).

Orphams with no neighbor phams, no synteny hits, or only NKF/hypothetical
evidence are silently excluded.

Usage
-----
  .venv/bin/python report_orpham_synteny.py \\
    --phage Beanstalk \\
    --dataset Actino_Draft \\
    --db phamerator.sqlite \\
    --out orpham_report.html
"""

from __future__ import annotations

import argparse
import html as _html
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UNINFORMATIVE = frozenset(["nkf", "hypothetical protein", "no known function", ""])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def escape(text: object) -> str:
    return _html.escape(str(text) if text is not None else "")


def normalize_phage_id(phage_id: str) -> str:
    """Lowercase, stripping any trailing _draft (defensive; DB should be clean after migration)."""
    s = phage_id.strip().lower()
    if s.endswith("_draft"):
        s = s[: -len("_draft")]
    return s


def is_informative(fn: str | None) -> bool:
    return bool(fn) and fn.strip().lower() not in UNINFORMATIVE


def fn_display(fn: str | None) -> str:
    """Return a display-ready gene function, substituting a label for blanks."""
    if not fn or fn.strip().lower() in UNINFORMATIVE:
        return fn.strip() if fn and fn.strip() else "NKF / hypothetical"
    return fn.strip()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_phage_id(conn: sqlite3.Connection, phage_name: str, dataset: str) -> str | None:
    """Find the canonical phage_id in the DB.

    After the migration phage_ids are stored without '_Draft', but if the caller
    passes a name with that suffix we strip it before looking up.
    """
    name = normalize_phage_id(phage_name)  # strips _draft, lowercases
    row = conn.execute(
        "SELECT phage_id FROM phages WHERE lower(phage_id) = ? AND dataset = ?",
        (name, dataset),
    ).fetchone()
    return row["phage_id"] if row else None


def _sql_norm_phage(col: str = "phage_id") -> str:
    """Lower-cased phage_id for same-phage comparison.

    After the DB migration phage_ids are stored without '_Draft', so a simple
    lower() is sufficient. The CASE fallback is kept for safety in case the
    migration hasn't been applied yet.
    """
    return (
        f"lower(CASE WHEN lower({col}) LIKE '%_draft'"
        f" THEN substr({col}, 1, length({col})-6)"
        f" ELSE {col} END)"
    )


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------


def compute_results(
    conn: sqlite3.Connection, ref_phage_id: str, dataset: str
) -> tuple[list[dict], dict]:
    """
    Run the orpham synteny scan and return (orpham_results, summary).

    Each orpham_result has:
      gene_number, pham_name, direction, gene_function, gene_length,
      start, stop, ref_up_pham, ref_dn_pham, ref_up_func, ref_dn_func,
      hits, tally_sorted, tally_total, both_fns,
      one_fns_sorted, up_only_count, dn_only_count,
      passes_filter, n_two_sided, n_one_sided
    """
    ref_norm = normalize_phage_id(ref_phage_id)

    # ── Load reference phage genes (same sort order as the Observable notebook) ──
    ref_genes = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM genes WHERE phage_id = ? AND dataset = ?"
            " ORDER BY stop, start, name",
            (ref_phage_id, dataset),
        ).fetchall()
    ]

    # ── Bulk-check pham membership for all phams in the ref phage ────────────
    ref_pham_names = {g["pham_name"] for g in ref_genes if g["pham_name"]}
    pham_is_orpham: dict[str, bool] = {}  # pham_name → True if only 1 distinct phage

    if ref_pham_names:
        placeholders = ",".join(["?"] * len(ref_pham_names))
        rows = conn.execute(
            f"""
            SELECT pham_name,
                   COUNT(DISTINCT {_sql_norm_phage()}) AS n_phages
            FROM genes
            WHERE dataset = ? AND pham_name IN ({placeholders})
            GROUP BY pham_name
            """,
            [dataset] + list(ref_pham_names),
        ).fetchall()
        for r in rows:
            pham_is_orpham[r["pham_name"]] = r["n_phages"] <= 1

    # ── Identify orphams and their genomic neighbours ─────────────────────────
    orpham_data: list[dict] = []
    all_neighbor_phams: set[str] = set()

    for idx, gene in enumerate(ref_genes):
        pham_name = gene["pham_name"]
        # Genes whose pham has members in other phages are not orphams.
        # Genes with no pham assignment are treated as orphams.
        if pham_name and not pham_is_orpham.get(pham_name, True):
            continue

        ref_dir = gene["direction"] or "forward"
        if ref_dir == "reverse":
            up_idx, dn_idx = idx + 1, idx - 1
        else:
            up_idx, dn_idx = idx - 1, idx + 1

        def _pham(i: int) -> str | None:
            return ref_genes[i]["pham_name"] if 0 <= i < len(ref_genes) else None

        def _func(i: int) -> str:
            return ref_genes[i]["gene_function"] if 0 <= i < len(ref_genes) else ""

        ref_up_pham = _pham(up_idx)
        ref_dn_pham = _pham(dn_idx)

        orpham_data.append(
            {
                "gene": gene,
                "ref_up_pham": ref_up_pham,
                "ref_dn_pham": ref_dn_pham,
                "ref_up_func": _func(up_idx),
                "ref_dn_func": _func(dn_idx),
            }
        )

        if ref_up_pham:
            all_neighbor_phams.add(ref_up_pham)
        if ref_dn_pham:
            all_neighbor_phams.add(ref_dn_pham)

    # ── Find candidate phage IDs that carry any neighbour pham ───────────────
    candidate_phage_ids: set[str] = set()
    if all_neighbor_phams:
        placeholders = ",".join(["?"] * len(all_neighbor_phams))
        rows = conn.execute(
            f"""
            SELECT DISTINCT phage_id FROM genes
            WHERE dataset = ? AND pham_name IN ({placeholders})
              AND {_sql_norm_phage()} != ?
            """,
            [dataset] + list(all_neighbor_phams) + [ref_norm],
        ).fetchall()
        candidate_phage_ids = {r["phage_id"] for r in rows}

    # ── Load genes and metadata for all candidate phages in one pass ──────────
    phage_genes: dict[str, list[dict]] = defaultdict(list)
    phage_meta: dict[str, dict] = {}

    if candidate_phage_ids:
        cand_list = list(candidate_phage_ids)
        placeholders = ",".join(["?"] * len(cand_list))

        for g in conn.execute(
            f"""
            SELECT * FROM genes WHERE dataset = ? AND phage_id IN ({placeholders})
            ORDER BY phage_id, stop, start, name
            """,
            [dataset] + cand_list,
        ).fetchall():
            phage_genes[g["phage_id"]].append(dict(g))

        for p in conn.execute(
            f"""
            SELECT phage_id, cluster, subcluster, cluster_subcluster, is_draft
            FROM phages WHERE dataset = ? AND phage_id IN ({placeholders})
            """,
            [dataset] + cand_list,
        ).fetchall():
            phage_meta[p["phage_id"]] = {
                "cluster": p["cluster_subcluster"] or p["cluster"] or "—",
                "is_draft": bool(p["is_draft"]),
            }

    # Pre-build pham → phage_ids index for fast per-orpham lookup
    pham_to_phages: dict[str, set[str]] = defaultdict(set)
    for phage_id, genes in phage_genes.items():
        for g in genes:
            if g["pham_name"]:
                pham_to_phages[g["pham_name"]].add(phage_id)

    # ── Compute synteny hits and function tallies for each orpham ─────────────
    results: list[dict] = []

    for o in orpham_data:
        ref_up_pham = o["ref_up_pham"]
        ref_dn_pham = o["ref_dn_pham"]

        # Phages relevant to this orpham (those carrying either neighbour pham)
        my_phage_ids: set[str] = set()
        if ref_up_pham:
            my_phage_ids |= pham_to_phages.get(ref_up_pham, set())
        if ref_dn_pham:
            my_phage_ids |= pham_to_phages.get(ref_dn_pham, set())

        hits: list[dict] = []

        for phage_id in my_phage_ids:
            c_genes = phage_genes.get(phage_id, [])
            meta = phage_meta.get(phage_id, {"cluster": "—", "is_draft": False})

            for ci, cg in enumerate(c_genes):
                c_dir = cg["direction"] or "forward"
                if c_dir == "reverse":
                    c_up_idx, c_dn_idx = ci + 1, ci - 1
                else:
                    c_up_idx, c_dn_idx = ci - 1, ci + 1

                up_pham = c_genes[c_up_idx]["pham_name"] if 0 <= c_up_idx < len(c_genes) else None
                dn_pham = c_genes[c_dn_idx]["pham_name"] if 0 <= c_dn_idx < len(c_genes) else None

                up_match = ref_up_pham is not None and up_pham == ref_up_pham
                dn_match = ref_dn_pham is not None and dn_pham == ref_dn_pham

                if not up_match and not dn_match:
                    continue

                hits.append(
                    {
                        "phage": phage_id,
                        "gene_number": cg["name"],
                        "cluster": meta["cluster"],
                        "sort_key": meta["cluster"] or "~",
                        "direction": c_dir,
                        "gene_function": cg["gene_function"] or "",
                        "candidate_pham": cg["pham_name"],
                        "is_draft": meta["is_draft"],
                        "up_pham": up_pham,
                        "dn_pham": dn_pham,
                        "up_match": up_match,
                        "dn_match": dn_match,
                        "two_sided": up_match and dn_match,
                    }
                )

        hits.sort(key=lambda r: (r["sort_key"], r["phage"]))

        # ── Two-flank function tally ──────────────────────────────────────────
        # A function qualifies if it appears in at least one up-matched hit AND
        # at least one dn-matched hit. Two-sided hits count for both.
        up_fns = {
            (r["gene_function"].strip() or "Hypothetical protein")
            for r in hits
            if r["up_match"]
        }
        dn_fns = {
            (r["gene_function"].strip() or "Hypothetical protein")
            for r in hits
            if r["dn_match"]
        }
        both_fns = up_fns & dn_fns

        tally: dict[str, int] = defaultdict(int)
        for r in hits:
            fn = r["gene_function"].strip() or "Hypothetical protein"
            if fn in both_fns:
                tally[fn] += 1
        tally_sorted = sorted(tally.items(), key=lambda x: -x[1])
        tally_total = sum(tally.values())

        # ── One-flank function tallies ────────────────────────────────────────
        up_only = [r for r in hits if r["up_match"] and not r["two_sided"]]
        dn_only = [r for r in hits if r["dn_match"] and not r["two_sided"]]

        one_fns: dict[str, dict] = {}
        for r in up_only:
            fn = r["gene_function"].strip() or "Hypothetical protein"
            one_fns.setdefault(fn, {"up": 0, "dn": 0})["up"] += 1  # type: ignore[index]
        for r in dn_only:
            fn = r["gene_function"].strip() or "Hypothetical protein"
            one_fns.setdefault(fn, {"up": 0, "dn": 0})["dn"] += 1  # type: ignore[index]

        # Sort: functions appearing in both subsets first, then by total count
        one_fns_sorted = sorted(
            one_fns.items(),
            key=lambda x: (-(x[1]["up"] > 0 and x[1]["dn"] > 0), -(x[1]["up"] + x[1]["dn"])),
        )

        # ── Filter: must have informative evidence ────────────────────────────
        has_informative_two_flank = any(is_informative(fn) for fn in both_fns)
        has_informative_one_flank_matching = any(
            is_informative(fn)
            for fn, counts in one_fns.items()
            if counts["up"] > 0 and counts["dn"] > 0
        )
        passes_filter = has_informative_two_flank or has_informative_one_flank_matching

        gene = o["gene"]
        results.append(
            {
                "gene_number": gene["name"],
                "pham_name": gene["pham_name"],
                "direction": gene["direction"] or "forward",
                "gene_function": gene["gene_function"] or "",
                "gene_length": abs((gene["stop"] or 0) - (gene["start"] or 0)) + 1,
                "start": gene["start"],
                "stop": gene["stop"],
                "ref_up_pham": ref_up_pham,
                "ref_dn_pham": ref_dn_pham,
                "ref_up_func": o["ref_up_func"],
                "ref_dn_func": o["ref_dn_func"],
                "hits": hits,
                "tally_sorted": tally_sorted,
                "tally_total": tally_total,
                "both_fns": both_fns,
                "one_fns_sorted": one_fns_sorted,
                "up_only_count": len(up_only),
                "dn_only_count": len(dn_only),
                "passes_filter": passes_filter,
                "n_two_sided": sum(1 for r in hits if r["two_sided"]),
                "n_one_sided": sum(1 for r in hits if not r["two_sided"]),
            }
        )

    total_orphams = len(results)
    passing = [r for r in results if r["passes_filter"]]
    summary = {
        "total_genes": len(ref_genes),
        "total_orphams": total_orphams,
        "with_any_hits": sum(1 for r in results if r["hits"]),
        "with_two_flank": sum(1 for r in results if r["n_two_sided"] > 0),
        "with_informative": len(passing),
    }
    return passing, summary


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: #1e293b;
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 20px 48px;
}
h1 { font-size: 1.4em; margin: 0 0 4px; }
h2 { font-size: 1.05em; margin: 0 0 16px; color: #475569; font-weight: 400; }

/* ── Summary bar ── */
.summary { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 24px; }
.stat { padding: 6px 14px; border-radius: 6px; border: 1px solid; font-size: 0.88em; }
.stat b { font-size: 1.1em; }
.stat-orange { background: #fff7ed; border-color: #fed7aa; }
.stat-purple { background: #faf5ff; border-color: #e9d5ff; }
.stat-green  { background: #f0fdf4; border-color: #bbf7d0; }
.stat-blue   { background: #eff6ff; border-color: #bfdbfe; }
.stat-slate  { background: #f8fafc; border-color: #e2e8f0; }

/* ── Orpham cards ── */
.orpham-card {
  margin-bottom: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}
.card-header {
  padding: 10px 14px;
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
.card-header .gene-title { font-weight: 700; color: #1e293b; font-size: 1em; }
.card-header .gene-pos   { color: #64748b; margin-left: 8px; }
.card-header .gene-fn    { color: #475569; margin-left: 8px; font-style: italic; }
.card-header .dir-fwd    { color: #2563eb; font-weight: 700; margin-left: 4px; }
.card-header .dir-rev    { color: #dc2626; font-weight: 700; margin-left: 4px; }
.badges { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 4px; }
.badge {
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 0.8em;
  border: 1px solid;
  white-space: nowrap;
}
.badge-flank  { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
.badge-two    { background: #ede9fe; border-color: #c4b5fd; color: #5b21b6; }
.badge-one    { background: #f0fdf4; border-color: #a7f3d0; color: #065f46; }
.badge-toggle { background: #f8fafc; border-color: #cbd5e1; color: #334155; cursor: pointer; }
.card-body { padding: 12px 14px; border-top: 1px solid #e2e8f0; }

/* ── Tables ── */
table { border-collapse: collapse; width: 100%; font-size: 0.85em; margin-bottom: 10px; }
th {
  padding: 6px 10px;
  background: #1e293b;
  color: #f8fafc;
  text-align: left;
  font-weight: 600;
}
td { padding: 5px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.group-row td {
  background: #f1f5f9;
  font-weight: 700;
  color: #334155;
  font-size: 0.82em;
  padding: 3px 10px;
  border-top: 2px solid #cbd5e1;
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
.section-label {
  font-size: 0.82em; color: #64748b; margin: 0 0 6px;
}
.no-hits { padding: 8px 0; color: #94a3b8; font-style: italic; font-size: 0.88em; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
.draft-flag { font-size: 0.75em; color: #64748b; }
.one-wrap { margin-top: 10px; }

/* ── Print ── */
@media print {
  body { font-size: 12px; padding: 0; max-width: none; }
  details { display: block !important; }
  details > summary.card-header { cursor: default; }
  .orpham-card { page-break-inside: avoid; border: 1px solid #ccc; }
  a { color: inherit; text-decoration: none; }
  .badge-toggle { display: none; }
  .one-wrap { display: block !important; }
}
"""

_PHAGESDB_PHAGE = "https://phagesdb.org/phages/{}/"
_PHAGESDB_PHAM  = "https://phagesdb.org/phams/{}/"


def _dir_tag(direction: str) -> str:
    if direction == "reverse":
        return '<span class="dir-rev" title="Reverse strand">←</span>'
    return '<span class="dir-fwd" title="Forward strand">→</span>'


def _pham_link(pham: str | None) -> str:
    if not pham:
        return "—"
    return f'<a href="{_PHAGESDB_PHAM.format(escape(pham))}" target="_blank">{escape(pham)}</a>'


def _phage_link(phage_id: str, is_draft: bool = False) -> str:
    clean = phage_id
    if clean.lower().endswith("_draft"):
        clean = clean[: -len("_draft")]
    draft_flag = ' <span class="draft-flag">🚧</span>' if is_draft else ""
    return (
        f'<a href="{_PHAGESDB_PHAGE.format(escape(clean))}" target="_blank">'
        f"{escape(phage_id)}</a>{draft_flag}"
    )


def _render_tally(tally_sorted: list, tally_total: int) -> str:
    if not tally_sorted:
        return ""
    rows_html = ""
    for fn, n in tally_sorted:
        v = n / tally_total if tally_total else 0
        inf = is_informative(fn)
        if inf and v > 0.50:
            bg_cls = "bg-strong"
        elif inf and v > 0.25:
            bg_cls = "bg-medium"
        elif inf and v > 0.10:
            bg_cls = "bg-light"
        else:
            bg_cls = ""
        td_cls = f' class="{bg_cls}"' if bg_cls else ""
        strong = ' class="fn-strong"' if inf and v > 0.25 else ""
        fn_cls = "" if inf else ' class="fn-dim"'
        rows_html += (
            f"<tr{td_cls}>"
            f'<td{fn_cls}><span{strong}>{escape(fn_display(fn))}</span></td>'
            f'<td class="td-right">{n} <span class="fn-pct">({round(100*v)}%)</span></td>'
            f"</tr>"
        )
    return f"""
<p class="section-label">
  Central-gene functions with support from <strong>both flanks</strong>
  (n={tally_total} qualifying hits)
</p>
<table>
  <thead><tr><th>Function</th><th style="text-align:right">Hits</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""


def _render_one_flank_section(
    one_fns_sorted: list, up_count: int, dn_count: int
) -> str:
    """HTML for the one-flank matching function table (inside a toggle wrapper)."""
    if not one_fns_sorted or (up_count == 0 and dn_count == 0):
        return ""

    rows_html = ""
    for fn, counts in one_fns_sorted:
        shared = counts["up"] > 0 and counts["dn"] > 0
        inf = is_informative(fn)
        row_cls = ' class="bg-light"' if shared and inf else ""
        fn_strong = " fn-strong" if shared and inf else ""
        fn_cls = f' class="fn-dim"' if not inf else (f' class="{fn_strong.strip()}"' if fn_strong else "")
        tick = "✓ " if shared else ""

        def pct_cell(n: int, total: int) -> str:
            if total == 0:
                return '<td class="td-right fn-dim">n/a</td>'
            if n == 0:
                return '<td class="td-right fn-dim">—</td>'
            return f'<td class="td-right">{n} <span class="fn-pct">({round(100*n/total)}%)</span></td>'

        rows_html += (
            f"<tr{row_cls}>"
            f"<td{fn_cls}>{escape(tick)}{escape(fn_display(fn))}</td>"
            f"{pct_cell(counts['up'], up_count)}"
            f"{pct_cell(counts['dn'], dn_count)}"
            f"</tr>"
        )

    total_hits = up_count + dn_count
    return f"""
<div class="one-wrap" style="display:none">
  <p class="section-label">
    Central-gene functions from <strong>one-flank</strong> hits
    (✓ = function seen in both the upstream-matched and downstream-matched subsets)
  </p>
  <table>
    <thead><tr>
      <th>Function</th>
      <th style="text-align:right">↑ upstream flank only (n={up_count})</th>
      <th style="text-align:right">↓ downstream flank only (n={dn_count})</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>
<button class="badge badge-toggle one-toggle"
        onclick="(function(btn){{
          var w=btn.previousElementSibling;
          var open=w.style.display==='none';
          w.style.display=open?'':'none';
          btn.textContent=open
            ?'▾ Hide one-flank functions ({total_hits} hit{("s" if total_hits != 1 else "")})'
            :'▸ Show one-flank functions ({total_hits} hit{("s" if total_hits != 1 else "")})';
        }})(this)">▸ Show one-flank functions ({total_hits} hit{"s" if total_hits != 1 else ""})</button>"""


def _render_hits_table(
    hits: list[dict], ref_up_pham: str | None, ref_dn_pham: str | None
) -> str:
    two_sided = [r for r in hits if r["two_sided"]]
    one_sided  = [r for r in hits if not r["two_sided"]]

    if not hits:
        return '<p class="no-hits">No syntenic hits found.</p>'

    def _row(r: dict, highlight: bool = False) -> str:
        row_cls = ' class="two-sided-row"' if highlight else ""
        up_td = (
            f'<td class="flank-match">{escape(r["up_pham"] or "—")}</td>'
            if r["up_match"]
            else f'<td class="flank-miss">{escape(r["up_pham"] or "—")}</td>'
        )
        dn_td = (
            f'<td class="flank-match">{escape(r["dn_pham"] or "—")}</td>'
            if r["dn_match"]
            else f'<td class="flank-miss">{escape(r["dn_pham"] or "—")}</td>'
        )
        pham_td = (
            f'<td class="td-center">{_pham_link(r["candidate_pham"])}</td>'
            if r["candidate_pham"]
            else '<td class="td-center fn-dim">orpham</td>'
        )
        fn_span = (
            f'<br><span class="fn-dim" style="font-size:0.82em">{escape(r["gene_function"])}</span>'
            if r["gene_function"]
            else ""
        )
        return (
            f"<tr{row_cls}>"
            f"<td>{_phage_link(r['phage'], r['is_draft'])}{fn_span}</td>"
            f'<td class="td-center">{escape(r["gene_number"])}</td>'
            f"{pham_td}"
            f"<td>{escape(r['cluster'])}</td>"
            f'<td class="td-center">{_dir_tag(r["direction"])}</td>'
            f"{up_td}{dn_td}"
            f"</tr>"
        )

    def _group_rows(rows: list[dict], highlight: bool = False) -> str:
        groups: dict[str, list] = {}
        for r in rows:
            groups.setdefault(r["cluster"] or "Unknown", []).append(r)
        out = ""
        for cluster, group in sorted(groups.items()):
            label = f"{cluster} ({len(group)} gene{'s' if len(group) != 1 else ''})"
            out += f'<tr class="group-row"><td colspan="7">{escape(label)}</td></tr>'
            out += "".join(_row(r, highlight) for r in group)
        return out

    thead = f"""<thead><tr>
      <th>Phage</th><th class="td-center">Gene #</th>
      <th class="td-center">Gene pham</th><th>Cluster</th>
      <th class="td-center">Dir.</th>
      <th>↑ upstream pham<br><small style="font-weight:400;opacity:.7">ref: {escape(ref_up_pham or "—")}</small></th>
      <th>↓ downstream pham<br><small style="font-weight:400;opacity:.7">ref: {escape(ref_dn_pham or "—")}</small></th>
    </tr></thead>"""

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


def render_html(
    phage_name: str,
    dataset: str,
    results: list[dict],
    summary: dict,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Summary bar
    def stat(cls: str, label: str, n: int) -> str:
        return f'<div class="stat {cls}"><b>{n}</b> {label}</div>'

    summary_html = (
        '<div class="summary">'
        + stat("stat-slate",  "total genes",       summary["total_genes"])
        + stat("stat-orange", "orphams",            summary["total_orphams"])
        + stat("stat-blue",   "with any hits",      summary["with_any_hits"])
        + stat("stat-purple", "with two-flank hits",summary["with_two_flank"])
        + stat("stat-green",  "shown (informative evidence)", summary["with_informative"])
        + "</div>"
    )

    # Orpham cards
    cards_html = ""
    for o in results:
        n2 = o["n_two_sided"]
        n1 = o["n_one_sided"]
        direction = o["direction"]
        gene_fn_display = escape(fn_display(o["gene_function"])) if o["gene_function"] else ""

        # Header badges
        up_badge = (
            f'<span class="badge badge-flank">↑ {_pham_link(o["ref_up_pham"])}'
            + (f' <span class="fn-dim">{escape(o["ref_up_func"])}</span>' if o["ref_up_func"] else "")
            + "</span>"
            if o["ref_up_pham"]
            else '<span class="badge badge-flank fn-dim">↑ —</span>'
        )
        dn_badge = (
            f'<span class="badge badge-flank">↓ {_pham_link(o["ref_dn_pham"])}'
            + (f' <span class="fn-dim">{escape(o["ref_dn_func"])}</span>' if o["ref_dn_func"] else "")
            + "</span>"
            if o["ref_dn_pham"]
            else '<span class="badge badge-flank fn-dim">↓ —</span>'
        )
        count_badges = ""
        if n2 > 0:
            count_badges += f'<span class="badge badge-two">🔗 {n2} two-flank</span>'
        if n1 > 0:
            count_badges += f'<span class="badge badge-one">🔀 {n1} one-flank</span>'

        header_html = f"""<summary class="card-header">
  <div>
    <span class="gene-title">Gene {escape(o["gene_number"])}</span>
    <span class="gene-pos">{escape(str(o["start"]).replace("None","?"))}–{escape(str(o["stop"]).replace("None","?"))} bp</span>
    {_dir_tag(direction)}
    {f'<span class="gene-fn">{gene_fn_display}</span>' if gene_fn_display else ""}
    {f'<span style="margin-left:8px;font-size:0.82em;color:#94a3b8">pham {_pham_link(o["pham_name"])}</span>' if o["pham_name"] else ""}
  </div>
  <div class="badges">{up_badge}{dn_badge}{count_badges}</div>
</summary>"""

        tally_html = _render_tally(o["tally_sorted"], o["tally_total"])
        one_flank_html = _render_one_flank_section(
            o["one_fns_sorted"], o["up_only_count"], o["dn_only_count"]
        )
        hits_table = _render_hits_table(o["hits"], o["ref_up_pham"], o["ref_dn_pham"])

        cards_html += f"""<div class="orpham-card">
<details open>
{header_html}
<div class="card-body">
{tally_html}
{one_flank_html}
{hits_table}
</div>
</details>
</div>
"""

    if not results:
        cards_html = (
            '<p style="color:#64748b;font-style:italic">'
            "No orphams with strong informative evidence found.</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orpham Synteny Report — {escape(phage_name)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>🧬 Orpham Synteny Report</h1>
<h2>Phage: <strong>{escape(phage_name)}</strong> &nbsp;·&nbsp; Dataset: {escape(dataset)}
&nbsp;·&nbsp; <span style="font-size:0.88em;color:#94a3b8">Generated {generated}</span></h2>

{summary_html}

<p style="font-size:0.82em;color:#64748b;margin:-12px 0 20px">
  Showing only orphams with informative (non-NKF/hypothetical) evidence from
  <strong>two-flank</strong> hits or convergent <strong>matching one-flank</strong> hits.
  Click a card header to collapse it. Rows highlighted in green have two-flank support.
</p>

{cards_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an HTML orpham synteny report from a local Phamerator SQLite database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--phage",   required=True, help="Phage name (e.g. Beanstalk)")
    parser.add_argument("--dataset", default="Actino_Draft", help="Dataset name")
    parser.add_argument("--db",      default="phamerator.sqlite", help="SQLite database path")
    parser.add_argument("--out",     default=None,
                        help="Output HTML file (default: <phage>_orpham_report.html)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"ERROR: Database not found: {db_path}")

    out_path = Path(
        args.out
        or f"{args.phage.replace(' ', '_')}_orpham_report.html"
    ).expanduser().resolve()

    conn = open_db(db_path)
    try:
        phage_id = resolve_phage_id(conn, args.phage, args.dataset)
        if not phage_id:
            avail = sorted(
                r["phage_id"]
                for r in conn.execute(
                    "SELECT phage_id FROM phages WHERE dataset = ? LIMIT 20", (args.dataset,)
                ).fetchall()
            )
            raise SystemExit(
                f"ERROR: Phage '{args.phage}' not found in dataset '{args.dataset}'.\n"
                f"Sample phage IDs: {', '.join(avail)}"
            )

        print(f"Phage   : {phage_id}")
        print(f"Dataset : {args.dataset}")
        print(f"DB      : {db_path}")
        print("Scanning…")

        results, summary = compute_results(conn, phage_id, args.dataset)

        print(f"  Total genes   : {summary['total_genes']}")
        print(f"  Orphams found : {summary['total_orphams']}")
        print(f"  With any hits : {summary['with_any_hits']}")
        print(f"  Two-flank     : {summary['with_two_flank']}")
        print(f"  In report     : {summary['with_informative']}")

        html_content = render_html(phage_id, args.dataset, results, summary)
        out_path.write_text(html_content, encoding="utf-8")
        print(f"\nReport written to: {out_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
