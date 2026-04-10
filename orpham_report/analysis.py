"""
analysis.py — orpham identification, synteny scanning, and function tallying.

Public entry points:
  compute_phage_results    – single-phage pipeline (kept for ad-hoc use)
  compute_cluster_results  – batch pipeline; share DB work across many phages

The pipeline for one phage is:

  1. load_phage_genes           – fetch genes from DB, sorted by position
  2. bulk_check_orpham_phams    – for each pham in the phage, is it single-phage?
  3. identify_orphams            – tag orpham genes and record their flanking phams
  4. find_candidate_phages      – which other phages carry any of those flanking phams?
  5. load_candidate_data        – bulk-fetch genes + metadata for candidates
  6. build_pham_index           – invert phage_genes into pham → {phage_ids}
  7. scan_orpham_hits           – per orpham, walk candidate phage genes for matches
  8. compute_function_tallies   – two-flank tally and one-flank tally from hits
  9. passes_filter              – does the orpham have informative evidence?
  10. assemble_orpham_result    – combine everything into one result dict
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable

from .db import normalize_phage_id, sql_norm_phage

UNINFORMATIVE = frozenset(["nkf", "hypothetical protein", "no known function", ""])


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def is_informative(fn: str | None) -> bool:
    return bool(fn) and fn.strip().lower() not in UNINFORMATIVE


def fn_display(fn: str | None) -> str:
    """Human-readable gene function; replaces blanks/NKF with a label."""
    if not fn or fn.strip().lower() in UNINFORMATIVE:
        return fn.strip() if fn and fn.strip() else "NKF / hypothetical"
    return fn.strip()


def _neighbor_indices(idx: int, direction: str) -> tuple[int, int]:
    """Return (up_idx, dn_idx) given gene *idx* and strand *direction*."""
    if direction == "reverse":
        return idx + 1, idx - 1
    return idx - 1, idx + 1


def _safe_pham(genes: list[dict], i: int) -> str | None:
    return genes[i]["pham_name"] if 0 <= i < len(genes) else None


def _safe_func(genes: list[dict], i: int) -> str:
    return genes[i]["gene_function"] if 0 <= i < len(genes) else ""


# ---------------------------------------------------------------------------
# Step 1 — load reference phage genes
# ---------------------------------------------------------------------------


def load_phage_genes(
    conn: sqlite3.Connection, phage_id: str, dataset: str
) -> list[dict]:
    """Return genes for *phage_id* sorted by stop, start, name (matches Observable)."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM genes WHERE phage_id = ? AND dataset = ?"
            " ORDER BY stop, start, name",
            (phage_id, dataset),
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# Step 2 — bulk-check pham membership
# ---------------------------------------------------------------------------


def bulk_check_orpham_phams(
    conn: sqlite3.Connection, pham_names: set[str], dataset: str
) -> dict[str, bool]:
    """Return {pham_name: is_orpham} for each pham in *pham_names*.

    A pham is an orpham (in the given dataset) if it appears in only one
    distinct phage. Phams absent from the DB are treated as orphams.
    """
    if not pham_names:
        return {}
    placeholders = ",".join(["?"] * len(pham_names))
    rows = conn.execute(
        f"""
        SELECT pham_name,
               COUNT(DISTINCT {sql_norm_phage()}) AS n_phages
        FROM genes
        WHERE dataset = ? AND pham_name IN ({placeholders})
        GROUP BY pham_name
        """,
        [dataset] + list(pham_names),
    ).fetchall()
    result = {r["pham_name"]: r["n_phages"] <= 1 for r in rows}
    # Phams not returned by the query have no entries in the DB → orpham
    for p in pham_names:
        result.setdefault(p, True)
    return result


# ---------------------------------------------------------------------------
# Step 3 — identify orphams and flanking phams
# ---------------------------------------------------------------------------


def identify_orphams(
    genes: list[dict], pham_is_orpham: dict[str, bool]
) -> list[dict]:
    """Return one record per orpham gene with its flanking pham context.

    Each record:
      gene         – the raw gene dict
      ref_up_pham  – pham_name of the upstream neighbour (strand-aware), or None
      ref_dn_pham  – pham_name of the downstream neighbour, or None
      ref_up_func  – gene_function of the upstream neighbour (may be "")
      ref_dn_func  – gene_function of the downstream neighbour
    """
    orphams: list[dict] = []
    for idx, gene in enumerate(genes):
        pham = gene["pham_name"]
        # Non-orpham: pham has members in other phages
        if pham and not pham_is_orpham.get(pham, True):
            continue
        direction = gene["direction"] or "forward"
        up_idx, dn_idx = _neighbor_indices(idx, direction)
        orphams.append(
            {
                "gene": gene,
                "ref_up_pham": _safe_pham(genes, up_idx),
                "ref_dn_pham": _safe_pham(genes, dn_idx),
                "ref_up_func": _safe_func(genes, up_idx),
                "ref_dn_func": _safe_func(genes, dn_idx),
            }
        )
    return orphams


# ---------------------------------------------------------------------------
# Step 4 — find candidate phages
# ---------------------------------------------------------------------------


def find_candidate_phages(
    conn: sqlite3.Connection,
    neighbor_phams: set[str],
    exclude_norm: str,
    dataset: str,
) -> set[str]:
    """Return phage_ids of phages carrying any pham in *neighbor_phams*.

    Excludes *exclude_norm* (the reference phage, normalised).
    """
    if not neighbor_phams:
        return set()
    placeholders = ",".join(["?"] * len(neighbor_phams))
    rows = conn.execute(
        f"""
        SELECT DISTINCT phage_id FROM genes
        WHERE dataset = ? AND pham_name IN ({placeholders})
          AND {sql_norm_phage()} != ?
        """,
        [dataset] + list(neighbor_phams) + [exclude_norm],
    ).fetchall()
    return {r["phage_id"] for r in rows}


# ---------------------------------------------------------------------------
# Step 5 — load candidate phage data in bulk
# ---------------------------------------------------------------------------


def load_candidate_data(
    conn: sqlite3.Connection, candidate_ids: set[str], dataset: str
) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Bulk-fetch genes and metadata for all candidate phages.

    Returns:
      phage_genes  – {phage_id: [gene_dict, …]}  (sorted by position)
      phage_meta   – {phage_id: {"cluster": str, "is_draft": bool}}
    """
    phage_genes: dict[str, list[dict]] = defaultdict(list)
    phage_meta: dict[str, dict] = {}

    if not candidate_ids:
        return phage_genes, phage_meta

    cand_list = list(candidate_ids)
    placeholders = ",".join(["?"] * len(cand_list))

    for g in conn.execute(
        f"SELECT * FROM genes WHERE dataset = ? AND phage_id IN ({placeholders})"
        " ORDER BY phage_id, stop, start, name",
        [dataset] + cand_list,
    ).fetchall():
        phage_genes[g["phage_id"]].append(dict(g))

    for p in conn.execute(
        f"SELECT phage_id, cluster, subcluster, cluster_subcluster, is_draft"
        f" FROM phages WHERE dataset = ? AND phage_id IN ({placeholders})",
        [dataset] + cand_list,
    ).fetchall():
        phage_meta[p["phage_id"]] = {
            "cluster": p["cluster_subcluster"] or p["cluster"] or "—",
            "is_draft": bool(p["is_draft"]),
        }

    return dict(phage_genes), phage_meta


# ---------------------------------------------------------------------------
# Step 6 — build pham → phage index
# ---------------------------------------------------------------------------


def build_pham_index(
    phage_genes: dict[str, list[dict]]
) -> dict[str, set[str]]:
    """Invert phage_genes into {pham_name: {phage_id, …}}."""
    index: dict[str, set[str]] = defaultdict(set)
    for phage_id, genes in phage_genes.items():
        for g in genes:
            if g["pham_name"]:
                index[g["pham_name"]].add(phage_id)
    return dict(index)


# ---------------------------------------------------------------------------
# Step 7 — scan synteny hits for one orpham
# ---------------------------------------------------------------------------


def scan_orpham_hits(
    orpham: dict,
    phage_genes: dict[str, list[dict]],
    pham_index: dict[str, set[str]],
    phage_meta: dict[str, dict],
) -> list[dict]:
    """Find all syntenic hits across candidate phages for one orpham.

    Each hit dict:
      phage, gene_number, cluster, sort_key, direction, gene_function,
      candidate_pham, is_draft, up_pham, dn_pham, up_match, dn_match, two_sided
    """
    ref_up_pham = orpham["ref_up_pham"]
    ref_dn_pham = orpham["ref_dn_pham"]

    relevant_phages: set[str] = set()
    if ref_up_pham:
        relevant_phages |= pham_index.get(ref_up_pham, set())
    if ref_dn_pham:
        relevant_phages |= pham_index.get(ref_dn_pham, set())

    hits: list[dict] = []
    for phage_id in relevant_phages:
        c_genes = phage_genes.get(phage_id, [])
        meta = phage_meta.get(phage_id, {"cluster": "—", "is_draft": False})

        for ci, cg in enumerate(c_genes):
            direction = cg["direction"] or "forward"
            up_idx, dn_idx = _neighbor_indices(ci, direction)
            up_pham = _safe_pham(c_genes, up_idx)
            dn_pham = _safe_pham(c_genes, dn_idx)

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
                    "direction": direction,
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
    return hits


# ---------------------------------------------------------------------------
# Step 8 — compute function tallies
# ---------------------------------------------------------------------------


def compute_function_tallies(
    hits: list[dict],
) -> tuple[list[tuple[str, int]], int, set[str]]:
    """Compute the two-flank function tally.

    A function qualifies if it appears in at least one up-matched hit AND at
    least one dn-matched hit (two-sided hits count for both flanks).

    Returns:
      tally_sorted  – [(fn, count), …] sorted descending
      tally_total   – sum of qualifying hit counts
      both_fns      – set of function strings that appear on both flanks
    """
    up_fns = {
        (r["gene_function"].strip() or "Hypothetical protein")
        for r in hits if r["up_match"]
    }
    dn_fns = {
        (r["gene_function"].strip() or "Hypothetical protein")
        for r in hits if r["dn_match"]
    }
    both_fns = up_fns & dn_fns

    tally: dict[str, int] = defaultdict(int)
    for r in hits:
        if not r["two_sided"]:
            continue
        fn = r["gene_function"].strip() or "Hypothetical protein"
        tally[fn] += 1

    tally_sorted = sorted(tally.items(), key=lambda x: -x[1])
    return tally_sorted, sum(tally.values()), both_fns


def compute_one_flank_tallies(
    hits: list[dict],
) -> tuple[list[tuple[str, dict]], int, int]:
    """Compute per-function counts split by which flank was matched (one-sided only).

    Returns:
      one_fns_sorted  – [(fn, {"up": n, "dn": n}), …], shared-first then by total
      up_only_count   – number of up-matched-only hits
      dn_only_count   – number of dn-matched-only hits
    """
    up_only = [r for r in hits if r["up_match"] and not r["two_sided"]]
    dn_only = [r for r in hits if r["dn_match"] and not r["two_sided"]]

    one_fns: dict[str, dict] = {}
    for r in up_only:
        fn = r["gene_function"].strip() or "Hypothetical protein"
        one_fns.setdefault(fn, {"up": 0, "dn": 0})["up"] += 1  # type: ignore[index]
    for r in dn_only:
        fn = r["gene_function"].strip() or "Hypothetical protein"
        one_fns.setdefault(fn, {"up": 0, "dn": 0})["dn"] += 1  # type: ignore[index]

    one_fns_sorted = sorted(
        one_fns.items(),
        key=lambda x: (-(x[1]["up"] > 0 and x[1]["dn"] > 0), -(x[1]["up"] + x[1]["dn"])),
    )
    return one_fns_sorted, len(up_only), len(dn_only)


# ---------------------------------------------------------------------------
# Step 9 — filter
# ---------------------------------------------------------------------------


def passes_filter(both_fns: set[str], one_fns: list[tuple[str, dict]]) -> bool:
    """True if the orpham has at least one informative cross-flank function.

    Passes if:
    - any informative function appears in *both_fns* (two-flank support), OR
    - any informative function is seen in both the up-only and dn-only subsets
      of one-flank hits (convergent one-flank support).
    """
    if any(is_informative(fn) for fn in both_fns):
        return True
    return any(
        is_informative(fn) and counts["up"] > 0 and counts["dn"] > 0
        for fn, counts in one_fns
    )


# ---------------------------------------------------------------------------
# Step 10 — assemble result dict for one orpham
# ---------------------------------------------------------------------------


def assemble_orpham_result(
    orpham: dict,
    hits: list[dict],
    tally_sorted: list,
    tally_total: int,
    both_fns: set[str],
    one_fns_sorted: list,
    up_only_count: int,
    dn_only_count: int,
) -> dict:
    gene = orpham["gene"]
    return {
        "gene_number": gene["name"],
        "pham_name": gene["pham_name"],
        "direction": gene["direction"] or "forward",
        "gene_function": gene["gene_function"] or "",
        "gene_length": abs((gene["stop"] or 0) - (gene["start"] or 0)) + 1,
        "start": gene["start"],
        "stop": gene["stop"],
        "ref_up_pham": orpham["ref_up_pham"],
        "ref_dn_pham": orpham["ref_dn_pham"],
        "ref_up_func": orpham["ref_up_func"],
        "ref_dn_func": orpham["ref_dn_func"],
        "hits": hits,
        "tally_sorted": tally_sorted,
        "tally_total": tally_total,
        "both_fns": both_fns,
        "one_fns_sorted": one_fns_sorted,
        "up_only_count": up_only_count,
        "dn_only_count": dn_only_count,
        "passes_filter": passes_filter(both_fns, one_fns_sorted),
        "n_two_sided": sum(1 for r in hits if r["two_sided"]),
        "n_one_sided": sum(1 for r in hits if not r["two_sided"]),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_phage_results(
    conn: sqlite3.Connection, phage_id: str, dataset: str
) -> tuple[list[dict], dict]:
    """Run the full orpham synteny pipeline for one phage.

    Returns:
      passing  – orpham result dicts that pass the informativeness filter
      summary  – counts dict for display
    """
    ref_norm = normalize_phage_id(phage_id)

    # 1. Load reference genes
    ref_genes = load_phage_genes(conn, phage_id, dataset)

    # 2. Classify phams as orpham / non-orpham
    ref_pham_names = {g["pham_name"] for g in ref_genes if g["pham_name"]}
    pham_is_orpham = bulk_check_orpham_phams(conn, ref_pham_names, dataset)

    # 3. Identify orpham genes and their flanking phams
    orpham_data = identify_orphams(ref_genes, pham_is_orpham)

    # 4. Collect all neighbour phams across all orphams
    all_neighbor_phams: set[str] = set()
    for o in orpham_data:
        if o["ref_up_pham"]:
            all_neighbor_phams.add(o["ref_up_pham"])
        if o["ref_dn_pham"]:
            all_neighbor_phams.add(o["ref_dn_pham"])

    # 5. Find and load candidate phage data
    candidate_ids = find_candidate_phages(conn, all_neighbor_phams, ref_norm, dataset)
    phage_genes, phage_meta = load_candidate_data(conn, candidate_ids, dataset)

    # 6. Build pham → phage index
    pham_index = build_pham_index(phage_genes)

    # 7-10. Process each orpham
    all_results: list[dict] = []
    for o in orpham_data:
        hits = scan_orpham_hits(o, phage_genes, pham_index, phage_meta)
        tally_sorted, tally_total, both_fns = compute_function_tallies(hits)
        one_fns_sorted, up_only_count, dn_only_count = compute_one_flank_tallies(hits)
        result = assemble_orpham_result(
            o, hits, tally_sorted, tally_total, both_fns,
            one_fns_sorted, up_only_count, dn_only_count,
        )
        all_results.append(result)

    passing = [r for r in all_results if r["passes_filter"]]
    summary = {
        "total_genes": len(ref_genes),
        "total_orphams": len(all_results),
        "with_any_hits": sum(1 for r in all_results if r["hits"]),
        "with_two_flank": sum(1 for r in all_results if r["n_two_sided"] > 0),
        "with_informative": len(passing),
    }
    return passing, summary


# ---------------------------------------------------------------------------
# Batch entry point (efficient for clusters with many phages)
# ---------------------------------------------------------------------------


def _bulk_load_phage_genes(
    conn: sqlite3.Connection, phage_ids: list[str], dataset: str
) -> dict[str, list[dict]]:
    """Load genes for multiple phages in a single query."""
    if not phage_ids:
        return {}
    placeholders = ",".join("?" * len(phage_ids))
    result: dict[str, list[dict]] = {}
    for row in conn.execute(
        f"SELECT * FROM genes WHERE dataset = ? AND phage_id IN ({placeholders})"
        " ORDER BY phage_id, stop, start, name",
        [dataset] + phage_ids,
    ).fetchall():
        result.setdefault(row["phage_id"], []).append(dict(row))
    return result


def _make_summary(ref_genes: list[dict], all_results: list[dict], passing: list[dict]) -> dict:
    return {
        "total_genes": len(ref_genes),
        "total_orphams": len(all_results),
        "with_any_hits": sum(1 for r in all_results if r["hits"]),
        "with_two_flank": sum(1 for r in all_results if r["n_two_sided"] > 0),
        "with_informative": len(passing),
    }


def compute_cluster_results(
    conn: sqlite3.Connection,
    phage_ids: list[str],
    dataset: str,
    on_phage_done: Callable[[str, list[dict], dict], None] | None = None,
) -> list[tuple[str, list[dict], dict]]:
    """Run the orpham synteny pipeline for a batch of phages efficiently.

    Versus N calls to compute_phage_results this reduces:
      - Reference gene loading:  N queries  → 1
      - Orpham pham check:       N queries  → 1
      - Candidate data loading:  up to N×M  → at most M unique candidates total

    Args:
      on_phage_done  optional callback(phage_id, passing, summary) for progress reporting
    Returns:
      list of (phage_id, passing_results, summary) in input order
    """
    if not phage_ids:
        return []

    # 1. Bulk-load all reference genes in one query
    all_ref_genes = _bulk_load_phage_genes(conn, phage_ids, dataset)

    # 2. Single orpham pham check across all phams seen in any reference phage
    all_phams = {
        g["pham_name"]
        for genes in all_ref_genes.values()
        for g in genes
        if g["pham_name"]
    }
    pham_is_orpham = bulk_check_orpham_phams(conn, all_phams, dataset)

    # 3. Process each phage; candidate data accumulates in a shared cache
    candidate_genes_cache: dict[str, list[dict]] = {}
    candidate_meta_cache: dict[str, dict] = {}
    output: list[tuple[str, list[dict], dict]] = []

    for phage_id in phage_ids:
        ref_norm  = normalize_phage_id(phage_id)
        ref_genes = all_ref_genes.get(phage_id, [])

        orpham_data = identify_orphams(ref_genes, pham_is_orpham)

        all_neighbor_phams: set[str] = {
            p for o in orpham_data
            for p in (o["ref_up_pham"], o["ref_dn_pham"]) if p
        }
        candidate_ids = find_candidate_phages(conn, all_neighbor_phams, ref_norm, dataset)

        new_ids = candidate_ids - set(candidate_genes_cache)
        if new_ids:
            new_genes, new_meta = load_candidate_data(conn, new_ids, dataset)
            candidate_genes_cache.update(new_genes)
            candidate_meta_cache.update(new_meta)

        phage_genes = {pid: candidate_genes_cache[pid] for pid in candidate_ids
                       if pid in candidate_genes_cache}
        phage_meta  = {pid: candidate_meta_cache[pid]  for pid in candidate_ids
                       if pid in candidate_meta_cache}

        pham_index = build_pham_index(phage_genes)

        all_results: list[dict] = []
        for o in orpham_data:
            hits = scan_orpham_hits(o, phage_genes, pham_index, phage_meta)
            tally_sorted, tally_total, both_fns = compute_function_tallies(hits)
            one_fns_sorted, up_only_count, dn_only_count = compute_one_flank_tallies(hits)
            all_results.append(assemble_orpham_result(
                o, hits, tally_sorted, tally_total, both_fns,
                one_fns_sorted, up_only_count, dn_only_count,
            ))

        passing = [r for r in all_results if r["passes_filter"]]
        summary = _make_summary(ref_genes, all_results, passing)

        if on_phage_done:
            on_phage_done(phage_id, passing, summary)

        output.append((phage_id, passing, summary))

    return output
