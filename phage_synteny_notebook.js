// Phage Genome Annotation – Synteny Helper
// Observable notebook source — paste each cell into a new cell in observablehq.com
// ─────────────────────────────────────────────────────────────────────────────

// ── CELL 1: title ──────────────────────────────────────────────────────────
md`# 🧬 Phage Genome Annotation – Synteny Helper

Query [PhagesDB](https://phagesdb.org) for genes with matching phams in the
same genomic neighbourhood as your gene of interest.

> **Two-sided synteny** – pham of the gene *and* both neighbours match.
> **One-sided synteny** – pham of the gene matches, and *at least one* neighbour matches.`


// ── CELL 2: inputs ─────────────────────────────────────────────────────────
viewof inputs = Inputs.form({
  phageName: Inputs.text({
    label: "Phage name",
    placeholder: "e.g. L5",
    value: ""
  }),
  geneNumber: Inputs.number({
    label: "Gene number",
    placeholder: "e.g. 12",
    min: 1,
    step: 1,
    value: null
  })
})


// ── CELL 3: run button ─────────────────────────────────────────────────────
viewof runBtn = Inputs.button("🔍 Find syntenic genes")


// ── CELL 4: helper ───────────────────────────────────────────────────

async function phagesdbGet(path) {
  const sep = path.includes("?") ? "&" : "?";
  const url = `https://phagesdb.org/api${path}${sep}format=json`;
  const resp = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${path}`);
  return resp.json();
}


// ── CELL 5: core data-fetching logic ───────────────────────────────────────
result = {
  const { phageName, geneStop } = inputs;
  if (!phageName || !geneStop) return { status: "idle" };

  try {
    // 1. Fetch the reference phage
    const refPhage = await phagesdbGet(`/sequencedphages/${encodeURIComponent(phageName.trim())}/`);
    if (!refPhage || !refPhage.phage_name) {
      return { status: "error", message: `Phage "${phageName}" not found on PhagesDB.` };
    }

    // 2. Fetch genes for the reference phage
    // PhagesDB returns paginated gene lists; we ask for a large page so we
    // get the whole genome in one call for typical phage sizes (< 500 genes).
    const refGenes = await phagesdbGet(
      `/genesbyphage/${encodeURIComponent(phageName.trim())}/&page_size=1000`
    );
    const genes = refGenes.results || refGenes;
    if (!genes || genes.length === 0) {
      return { status: "error", message: `No gene data found for "${phageName}". The genome may not be phamerated yet.` };
    }

    // Sort by gene number
    genes.sort((a, b) => (a.Stop || 0) - (b.Stop || 0));

    const geneIdx = genes.findIndex(g => Number(g.Stop) === Number(geneStop));
    if (geneIdx === -1) {
      return {
        status: "error",
        message: `Gene with stop at ${geneStop} not found in ${phageName}.`
      };
    }

    const refGene    = genes[geneIdx];
    const refPham    = refGene.PhamID;
    const geneNumber = refGene.Name;
    const refUpPham  = geneIdx > 0              ? genes[geneIdx - 1].PhamID : null;
    const refDnPham  = geneIdx < genes.length-1 ? genes[geneIdx + 1].PhamID : null;

    if (!refPham) {
      return { status: "error", message: `Gene ${geneNumber} in ${phageName} has no pham assignment yet.` };
    }

    // 3. Fetch all genes in the same pham to find candidate phages
    const phamGenes = await phagesdbGet(
      `/phamphages/${refPham}/&page_size=1000`
    );
    const members = (phamGenes.results || phamGenes).filter(
      g => g.phage_name !== phageName.trim()
    );

    if (members.length === 0) {
      return {
        status: "ok",
        refPham, refUpPham, refDnPham,
        rows: [],
        message: `Pham ${refPham} has no members in other phages.`
      };
    }

    // 4. For each candidate gene, fetch the gene's upstream/downstream phams.
    // To avoid thousands of requests we group by phage, then fetch each phage's
    // gene list once (cached).
    const phageCache = new Map();

    async function getPhageGenes(name) {
      if (phageCache.has(name)) return phageCache.get(name);
      const data = await phagesdbGet(
        `/genes/?phage_name=${encodeURIComponent(name)}&page_size=1000`
      );
      const list = (data.results || data).sort(
        (a, b) => (a.gene_number || 0) - (b.gene_number || 0)
      );
      phageCache.set(name, list);
      return list;
    }

    // Fetch phage metadata (cluster/subcluster) in parallel, deduped by phage
    const uniquePhageNames = [...new Set(members.map(g => g.phage_name))];

    // PhagesDB phage endpoint returns cluster/subcluster
    const phageMeta = new Map();
    await Promise.all(
      uniquePhageNames.map(async name => {
        try {
          const meta = await phagesdbGet(`/phages/${encodeURIComponent(name)}/`);
          phageMeta.set(name, {
            cluster:    meta.cluster    || meta.cluster_id    || "—",
            subcluster: meta.subcluster || meta.subcluster_id || null
          });
        } catch { phageMeta.set(name, { cluster: "—", subcluster: null }); }
      })
    );

    // 5. Evaluate synteny for each member gene
    const rows = [];
    await Promise.all(
      members.map(async candidate => {
        const cGenes = await getPhageGenes(candidate.phage_name);
        const ci = cGenes.findIndex(g => Number(g.gene_number) === Number(candidate.gene_number));
        if (ci === -1) return;

        const upPham = ci > 0              ? cGenes[ci - 1].pham_id : null;
        const dnPham = ci < cGenes.length-1 ? cGenes[ci + 1].pham_id : null;

        const upMatch = refUpPham !== null && upPham === refUpPham;
        const dnMatch = refDnPham !== null && dnPham === refDnPham;

        // Must have at least one-sided synteny
        if (!upMatch && !dnMatch) return;

        const meta = phageMeta.get(candidate.phage_name) || { cluster: "—", subcluster: null };
        rows.push({
          phage:       candidate.phage_name,
          geneNumber:  candidate.gene_number,
          cluster:     meta.cluster,
          subcluster:  meta.subcluster,
          sortKey:     meta.subcluster || meta.cluster || "~",
          upPham,
          dnPham,
          upMatch,
          dnMatch,
          twoSided:    upMatch && dnMatch
        });
      })
    );

    // Sort by subcluster (fall back to cluster), then phage name
    rows.sort((a, b) =>
      a.sortKey.localeCompare(b.sortKey) || a.phage.localeCompare(b.phage)
    );

    // Fetch all pham genes (including the ref gene) for metadata analysis
    const allPhamGenes = (phamGenes.results || phamGenes);
    const refGeneLength = refGene.gene_length || 0;
    const refPhageCluster = refPhage.cluster || refPhage.cluster_id || null;

    // Compute pham-wide statistics
    const allLengths = allPhamGenes.map(g => g.gene_length || 0).filter(l => l > 0);
    const clusterLengths = allPhamGenes
      .filter(g => {
        const gPhageMeta = phageMeta.get(g.phage_name);
        return gPhageMeta && gPhageMeta.cluster === refPhageCluster;
      })
      .map(g => g.gene_length || 0)
      .filter(l => l > 0);

    const computeStats = (lengths) => {
      if (lengths.length === 0) return null;
      const sorted = [...lengths].sort((a, b) => a - b);
      const mean = sorted.reduce((a, b) => a + b, 0) / sorted.length;
      // Mode: most frequent value
      const freq = {};
      let mode = sorted[0], maxFreq = 0;
      for (const v of sorted) {
        freq[v] = (freq[v] || 0) + 1;
        if (freq[v] > maxFreq) { maxFreq = freq[v]; mode = v; }
      }
      return {
        count: sorted.length,
        min: sorted[0],
        max: sorted[sorted.length - 1],
        mean: Math.round(mean),
        mode: mode
      };
    };

    const phamStats = computeStats(allLengths);
    const clusterStats = computeStats(clusterLengths);

    return {
      status: "ok",
      refPham, refUpPham, refDnPham,
      refGeneLength, refPhageCluster,
      phamStats, clusterStats,
      rows
    };

  } catch (err) {
    return { status: "error", message: err.message };
  }
}

// ── CELL 6: summary badges ─────────────────────────────────────────────────
html`${(() => {
  if (result.status === "idle")
    return `<p style="color:#888">Enter a phage name and gene number, then click <strong>Find syntenic genes</strong>.</p>`;
  if (result.status === "error")
    return `<div style="padding:10px;background:#fee2e2;border-radius:6px;color:#b91c1c">⚠️ ${result.message}</div>`;

  const { rows, refPham, refUpPham, refDnPham } = result;
  const two = rows.filter(r => r.twoSided).length;
  const one = rows.length - two;

  return `
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
    <div style="padding:8px 16px;background:#eff6ff;border-radius:8px;border:1px solid #bfdbfe">
      <b>Pham of interest:</b> ${refPham}
    </div>
    <div style="padding:8px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0">
      <b>Upstream pham:</b> ${refUpPham ?? "—"}
    </div>
    <div style="padding:8px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0">
      <b>Downstream pham:</b> ${refDnPham ?? "—"}
    </div>
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap">
    <div style="padding:8px 16px;background:#faf5ff;border-radius:8px;border:1px solid #e9d5ff">
      🔗 <b>${two}</b> two-sided syntenic genes
    </div>
    <div style="padding:8px 16px;background:#fff7ed;border-radius:8px;border:1px solid #fed7aa">
      🔀 <b>${one}</b> one-sided syntenic genes
    </div>
    <div style="padding:8px 16px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0">
      <b>${rows.length}</b> total syntenic genes across <b>${new Set(rows.map(r=>r.phage)).size}</b> phages
    </div>
  </div>`;
})()}`


// ── CELL 7: the table ──────────────────────────────────────────────────────
html`${(() => {
  if (result.status !== "ok" || result.rows.length === 0) return "";

  const { rows, refUpPham, refDnPham } = result;

  // Group by subcluster (or cluster)
  const groups = new Map();
  for (const r of rows) {
    const key = r.subcluster || r.cluster || "Unknown";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }

  const cellStyle = (match, pham, refPham) => {
    if (refPham === null) return `style="color:#94a3b8"`;  // grey – no neighbour
    const bg = match ? "#dcfce7" : "#fee2e2";
    const col = match ? "#166534" : "#991b1b";
    return `style="background:${bg};color:${col};font-weight:600;text-align:center"`;
  };

  const badgeStyle = twoSided =>
    twoSided
      ? `style="display:inline-block;padding:1px 7px;border-radius:9999px;background:#ede9fe;color:#5b21b6;font-size:0.75em"`
      : `style="display:inline-block;padding:1px 7px;border-radius:9999px;background:#ffedd5;color:#9a3412;font-size:0.75em"`;

  let html_out = `
  <style>
    .syn-table { border-collapse: collapse; width: 100%; font-size: 0.88em; }
    .syn-table th { padding: 7px 12px; background: #1e293b; color: #f8fafc;
                    text-align: left; position: sticky; top: 0; z-index: 1; }
    .syn-table td { padding: 6px 12px; border-bottom: 1px solid #e2e8f0; }
    .syn-table tr:hover td { background: #f1f5f9 !important; }
    .group-header td { background: #f1f5f9; font-weight: 700;
                       color: #334155; padding: 4px 12px;
                       border-top: 2px solid #cbd5e1; font-size:0.85em; }
    .syn-table td a { color: #2563eb; text-decoration: none; }
    .syn-table td a:hover { text-decoration: underline; }
  </style>
  <div style="overflow-x:auto;max-height:70vh;overflow-y:auto">
  <table class="syn-table">
    <thead>
      <tr>
        <th>Phage</th>
        <th>Gene #</th>
        <th>Subcluster</th>
        <th>Upstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refUpPham ?? "—"}</small></th>
        <th>Downstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refDnPham ?? "—"}</small></th>
        <th>Synteny</th>
      </tr>
    </thead>
    <tbody>`;

  for (const [groupKey, groupRows] of groups) {
    html_out += `
      <tr class="group-header">
        <td colspan="6">📁 ${groupKey} (${groupRows.length} gene${groupRows.length>1?"s":""})</td>
      </tr>`;

    for (const r of groupRows) {
      const upDisplay = r.upPham ?? "—";
      const dnDisplay = r.dnPham ?? "—";
      html_out += `
      <tr>
        <td><a href="https://phagesdb.org/phages/${r.phage}/" target="_blank">${r.phage}</a></td>
        <td style="text-align:center">${r.geneNumber}</td>
        <td>${r.subcluster || r.cluster || "—"}</td>
        <td ${cellStyle(r.upMatch, r.upPham, refUpPham)}>${upDisplay}</td>
        <td ${cellStyle(r.dnMatch, r.dnPham, refDnPham)}>${dnDisplay}</td>
        <td style="text-align:center">
          <span ${badgeStyle(r.twoSided)}>${r.twoSided ? "two-sided" : "one-sided"}</span>
        </td>
      </tr>`;
    }
  }

  html_out += `</tbody></table></div>`;
  return html_out;
})()}`


// ── CELL 8: pham metadata summary ─────────────────────────────────────────
html`${(() => {
  if (result.status !== "ok" || !result.phamStats) return "";

  const { refGeneLength, refPhageCluster, phamStats, clusterStats } = result;
  const formatLen = (len) => len ? \`\${len} bp\` : "N/A";

  let summary = \`<div style="padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:0.9em;line-height:1.6">\`;
  summary += \`<strong>Pham \${result.refPham} metadata:</strong> \`;
  summary += \`\${phamStats.count} genes across the pham. \`;
  summary += \`Length range: \${formatLen(phamStats.min)}–\${formatLen(phamStats.max)}; mean \${formatLen(phamStats.mean)}; mode \${formatLen(phamStats.mode)}. \`;

  if (refPhageCluster && clusterStats && clusterStats.count > 0) {
    summary += \`Within <strong>\${refPhageCluster}</strong> cluster: \${clusterStats.count} genes; range \${formatLen(clusterStats.min)}–\${formatLen(clusterStats.max)}; mean \${formatLen(clusterStats.mean)}; mode \${formatLen(clusterStats.mode)}. \`;
  }

  // Determine similarity to pham
  let similarity = "";
  if (refGeneLength && phamStats) {
    const phamMean = phamStats.mean;
    const lengths = result.rows.map(r => r.gene_length || 0).filter(l => l > 0);
    lengths.push(refGeneLength);
    const phamStdDev = Math.sqrt(
      lengths.reduce((sum, l) => sum + Math.pow(l - phamMean, 2), 0) / Math.max(lengths.length - 1, 1)
    ) || 1;
    const zScore = (refGeneLength - phamMean) / phamStdDev;

    if (Math.abs(zScore) < 0.5) similarity = "very similar in length to other pham members.";
    else if (Math.abs(zScore) < 1.0) similarity = "slightly shorter/longer than typical pham members.";
    else similarity = "notably different in length from typical pham members.";

    if (clusterStats && clusterStats.count > 1) {
      const clusterMean = clusterStats.mean;
      const clusterLengths = result.rows
        .filter(r => {
          const rPhageMeta = phageMeta.get(r.phage);
          return rPhageMeta && rPhageMeta.cluster === refPhageCluster;
        })
        .map(r => r.gene_length || 0)
        .filter(l => l > 0);
      clusterLengths.push(refGeneLength);
      const clusterStdDev = Math.sqrt(
        clusterLengths.reduce((sum, l) => sum + Math.pow(l - clusterMean, 2), 0) / Math.max(clusterLengths.length - 1, 1)
      ) || 1;
      const clusterZScore = (refGeneLength - clusterMean) / clusterStdDev;
      if (Math.abs(clusterZScore) < 0.5) similarity += \` Particularly similar to \${refPhageCluster} cluster members.\`;
    }
  }

  summary += \`Your gene (\${formatLen(refGeneLength)}) is \${similarity}\`;
  summary += \`</div>\`;
  return summary;
})()}\`


// ── CELL 9: loading indicator ──────────────────────────────────────────────
// Observable shows a loading spinner automatically while \`result\` is pending,
// but this cell provides a friendlier status line.
html\`<div style="color:#64748b;font-size:0.85em;margin-top:8px">
  \${result.status === "idle"   ? "" :
    result.status === "error"  ? "" :
    result.rows.length === 0   ? "✅ Done — no syntenic genes found." :
    \`✅ Loaded \${result.rows.length} syntenic gene(s).\`}
</div>\`
