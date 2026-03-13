# Phage Genome Annotation – Synteny Helper
Observable notebook source — paste each cell into a new cell in observablehq.com

## ── CELL 1: title ──────────────────────────────────────────────────────────

```md
# 🧬 Phage Genome Annotation – Synteny Helper

Query [PhagesDB](https://phagesdb.org) for genes with matching phams in the
same genomic neighbourhood as your gene of interest.

> **Two-sided synteny** – pham of the gene *and* both neighbours match.
> **One-sided synteny** – pham of the gene matches, and *at least one* neighbour matches.`
```

## ── CELL 2: inputs ─────────────────────────────────────────────────────────

```js
viewof inputs = Inputs.form({
  phageName: Inputs.text({
    label: "Phage name",
    placeholder: "e.g. L5",
    value: ""
  }),
  geneNumber: Inputs.number({
    label: "Stop number",
    placeholder: "e.g. 35,982",
    min: 3,
    step: 1,
    value: null
  })
})
```

## ── CELL 3: core data-fetching logic ───────────────────────────────────────
```js
result = {
  var { phageName, geneStop } = inputs;
  if (!phageName || !geneStop) return { status: "idle" };
  phageName = phageName.trim()
  var genomeIsDraft=false;

  try {
    // 1. Fetch the reference phage
    var refPhage = await getPhameratorData(dataset, `/genome/${encodeURIComponent(phageName.trim())}/`, user.email, user.password);
    if (!refPhage) {
      refPhage = await getPhameratorData(dataset, `/genome/${encodeURIComponent(phageName.trim())}_Draft/`, user.email, user.password);
      if (!refPhage) {
        return { status: "error", message: `Phage '${phageName}' not found on Phamerator.` };
      }
      genomeIsDraft=true;
      phageName=`${phageName}_Draft`
    }
    const genes = refPhage.genes;
    if (!genes || genes.length === 0) {
      return { status: "error", message: `No gene data found for "${phageName}". The genome may not be phamerated yet.` };
    }

    // 2. Sort by gene number
    genes.sort((a, b) => (a.stop || 0) - (b.stop || 0));

    const geneIdx = genes.findIndex(g => Number(g.stop) === Number(geneStop));
    if (geneIdx === -1) {
      return {
        status: "error",
        message: `Gene with stop at ${geneStop} not found in ${phageName}.`
      };
    }

    const refGene    = genes[geneIdx];
    const refPham    = refGene.phamName;
    const geneNumber = refGene.name;
    const refUpPham  = geneIdx > 0              ? genes[geneIdx - 1].phamName : null;
    const refDnPham  = geneIdx < genes.length-1 ? genes[geneIdx + 1].phamName : null;

    if (!refPham) {
      return { status: "error", message: `Gene ${geneNumber} in ${phageName} has no pham assignment yet.` };
    }

    // 3. Fetch all genes in the same pham to find candidate phages
    const phamGenes = await getPhameratorData(
      dataset, `/phamily/${refPham}`, user.email, user.password
    );
    const members = (phamGenes).filter(
      g => g.phageID !== phageName
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

    // Fetch phage metadata (cluster/genes) in parallel, deduped by phage
    const uniquePhageNames = [...new Set(members.map(g => g.phageID))];
    const phageData = new Map();
    await Promise.all(
      uniquePhageNames.map(async name => {
        try {
          const data = await  getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}/`, user.email, user.password);
          phageData.set(name, {
            cluster:    data.clusterSubcluster    || "—",
            genes: data.genes,
          });
        } catch { phageData.set(name, { cluster: "—", genes: []}); }
      })
    );

    // 5. Evaluate synteny for each member gene
    const rows = [];
    await Promise.all(
      members.map(async candidate => {
        const cGenes = phageData.get(candidate.phageID)?.genes;
        if (!cGenes) return;
        const ci = cGenes.findIndex(g => Number(g.name) === Number(candidate.name));
        if (ci === -1) return;

        const upPham = ci > 0              ? cGenes[ci - 1].phamName : null;
        const dnPham = ci < cGenes.length-1 ? cGenes[ci + 1].phamName : null;

        const upMatch = refUpPham !== null && upPham === refUpPham;
        const dnMatch = refDnPham !== null && dnPham === refDnPham;

        // Must have at least one-sided synteny
        if (!upMatch && !dnMatch) return;

        const meta = phageData.get(candidate.phageID) || { cluster: "—" };
        rows.push({
          phage:       candidate.phageID,
          geneNumber:  candidate.name,
          cluster:     meta.cluster,
          sortKey:     meta.cluster || "~",
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
    const refGeneLength = refGene.stop - refGene.start;
    const refPhageCluster = refPhage.clusterSubcluster || refPhage.cluster || null;

    // Compute pham-wide statistics
    const allLengths = phamGenes.map(g => g.stop - g.start).filter(l => l > 0);
    const clusterLengths = phamGenes
      .filter(g => {
        const gPhageMeta = phageData.get(g.phageID);
        return gPhageMeta && gPhageMeta.cluster === refPhageCluster;
      })
      .map(g => g.stop - g.start)
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
      const stdDev = Math.sqrt(
        sorted.reduce((s, v) => s + Math.pow(v - mean, 2), 0) / Math.max(sorted.length - 1, 1)
      );
      return {
        count: sorted.length,
        min: sorted[0],
        max: sorted[sorted.length - 1],
        mean: Math.round(mean),
        mode: mode,
        modeFreqPct: Math.round(100 * maxFreq / sorted.length),
        stdDev: Math.round(stdDev)
      };
    };

    const phamStats = computeStats(allLengths);
    const clusterStats = computeStats(clusterLengths);

    return {
      status: "ok",
      phageName, geneNumber,
      refPham, refUpPham, refDnPham,
      refGeneLength, refPhageCluster,
      phamStats, clusterStats,
      rows
    };

  } catch (err) {
    return { status: "error", message: err.message };
  }
}
```

## ── CELL 6: summary badges ─────────────────────────────────────────────────

```js
html`${(() => {
  if (result.status === "idle")
    return `<p style="color:#888">Enter a phage name and gene number, then click <strong>Find syntenic genes</strong>.</p>`;
  if (result.status === "error")
    return `<div style="padding:10px;background:#fee2e2;border-radius:6px;color:#b91c1c">⚠️ ${result.message}</div>`;

  const { rows, phageName, geneNumber, refPham, refUpPham, refDnPham } = result;
  const two = rows.filter(r => r.twoSided).length;
  const one = rows.length - two;
  const phageUrl = `https://phagesdb.org/phages/${encodeURIComponent(phageName)}/`;
  const phamUrl  = (p) => `https://phagesdb.org/phamily/${encodeURIComponent(p)}/`;

  return `
  <div style="margin-bottom:6px;font-size:0.88em;color:#475569">
    Phage: <a href="${phageUrl}" target="_blank" style="color:#2563eb;font-weight:600">${phageName}</a>
    &nbsp;·&nbsp; Gene #${geneNumber}
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
    <div style="padding:8px 16px;background:#eff6ff;border-radius:8px;border:1px solid #bfdbfe">
      <b>Pham of interest:</b> <a href="${phamUrl(refPham)}" target="_blank" style="color:#1d4ed8">${refPham}</a>
    </div>
    <div style="padding:8px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0">
      <b>Upstream pham:</b> ${refUpPham ? `<a href="${phamUrl(refUpPham)}" target="_blank" style="color:#15803d">${refUpPham}</a>` : "—"}
    </div>
    <div style="padding:8px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0">
      <b>Downstream pham:</b> ${refDnPham ? `<a href="${phamUrl(refDnPham)}" target="_blank" style="color:#15803d">${refDnPham}</a>` : "—"}
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
```

## ── CELL 7: the table ──────────────────────────────────────────────────────

```js
{
  if (result.status !== "ok" || result.rows.length === 0) return html``;

  const { rows, refUpPham, refDnPham } = result;

  const nTwo  = rows.filter(r => r.twoSided).length;
  const nUp   = rows.filter(r => !r.twoSided && r.upMatch).length;
  const nDown = rows.filter(r => !r.twoSided && r.dnMatch).length;

  // Group by cluster for display
  const groups = new Map();
  for (const r of rows) {
    const key = r.cluster || "Unknown";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }

  const cellStyle = (match, refPham) => {
    if (refPham === null) return `style="color:#94a3b8;text-align:center"`;
    const bg = match ? "#dcfce7" : "#fee2e2";
    const col = match ? "#166534" : "#991b1b";
    return `style="background:${bg};color:${col};font-weight:600;text-align:center"`;
  };

  const synTag = r => {
    if (r.twoSided) return `<span style="display:inline-block;padding:1px 7px;border-radius:9999px;background:#ede9fe;color:#5b21b6;font-size:0.75em">two-sided</span>`;
    if (r.upMatch)  return `<span style="display:inline-block;padding:1px 7px;border-radius:9999px;background:#dbeafe;color:#1e40af;font-size:0.75em">↑ upstream</span>`;
                    return `<span style="display:inline-block;padding:1px 7px;border-radius:9999px;background:#fef9c3;color:#854d0e;font-size:0.75em">↓ downstream</span>`;
  };

  // Build HTML (no <script> tags — event listeners attached via JS below)
  let html_out = `
  <style>
    .syn-tbl { border-collapse: collapse; width: 100%; font-size: 0.88em; }
    .syn-tbl th { padding: 7px 12px; background: #1e293b; color: #f8fafc;
                  text-align: left; position: sticky; top: 0; z-index: 1; }
    .syn-tbl td { padding: 6px 12px; border-bottom: 1px solid #e2e8f0; }
    .syn-tbl tr:hover td { background: #f1f5f9 !important; }
    .syn-tbl .grp-hdr td { background: #f1f5f9; font-weight: 700; cursor: pointer;
                            color: #334155; padding: 4px 12px;
                            border-top: 2px solid #cbd5e1; font-size:0.85em; user-select:none; }
    .syn-tbl .grp-hdr:hover td { background: #e2e8f0 !important; }
    .syn-tbl td a { color: #2563eb; text-decoration: none; }
    .syn-tbl td a:hover { text-decoration: underline; }
    .sfbtn { padding:4px 12px; border-radius:6px; border:1px solid #cbd5e1;
             background:#f8fafc; cursor:pointer; font-size:0.82em; font-weight:600; }
    .sfbtn.active { background:#1e293b; color:#f8fafc; border-color:#1e293b; }
  </style>
  <div class="sfbar" style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
    <span style="font-size:0.82em;color:#64748b;margin-right:2px">Show:</span>
    <button class="sfbtn active" data-filter="all" >All (${rows.length})</button>
    <button class="sfbtn"        data-filter="two" >🔗 Two-sided (${nTwo})</button>
    <button class="sfbtn"        data-filter="up"  >↑ Upstream only (${nUp})</button>
    <button class="sfbtn"        data-filter="down">↓ Downstream only (${nDown})</button>
  </div>
  <div style="overflow-x:auto;max-height:70vh;overflow-y:auto">
  <table class="syn-tbl">
    <thead><tr>
      <th>Phage</th><th>Gene #</th><th>Cluster</th>
      <th>Upstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refUpPham ?? "—"}</small></th>
      <th>Downstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refDnPham ?? "—"}</small></th>
      <th>Synteny</th>
    </tr></thead>
    <tbody>`;

  let gi = 0;
  for (const [groupKey, groupRows] of groups) {
    const gid = `g${gi++}`;
    html_out += `<tr class="grp-hdr" data-gid="${gid}">
      <td colspan="6"><span class="chev">▾</span> ${groupKey} (${groupRows.length} gene${groupRows.length>1?"s":""})</td></tr>`;
    for (const r of groupRows) {
      const syn = r.twoSided ? "two" : r.upMatch ? "up" : "down";
      html_out += `
      <tr data-group="${gid}" data-syn="${syn}">
        <td><a href="https://phagesdb.org/phages/${r.phage}/" target="_blank">${r.phage}</a></td>
        <td style="text-align:center">${r.geneNumber}</td>
        <td>${r.cluster || "—"}</td>
        <td ${cellStyle(r.upMatch, refUpPham)}>${r.upPham ?? "—"}</td>
        <td ${cellStyle(r.dnMatch, refDnPham)}>${r.dnPham ?? "—"}</td>
        <td style="text-align:center">${synTag(r)}</td>
      </tr>`;
    }
  }
  html_out += `</tbody></table></div>`;

  // Create DOM node and wire up event listeners (avoids <script> injection issues)
  const wrap = document.createElement('div');
  wrap.innerHTML = html_out;
  const tbody = wrap.querySelector('tbody');

  // Filter buttons
  wrap.querySelectorAll('.sfbtn').forEach(btn => {
    btn.addEventListener('click', function() {
      wrap.querySelectorAll('.sfbtn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      const filter = this.dataset.filter;
      tbody.querySelectorAll('tr[data-syn]').forEach(row => {
        row.style.display = (filter === 'all' || row.dataset.syn === filter) ? '' : 'none';
      });
      tbody.querySelectorAll('tr.grp-hdr').forEach(hdr => {
        const gid = hdr.dataset.gid;
        const any = [...tbody.querySelectorAll(`tr[data-group="${gid}"]`)].some(r => r.style.display !== 'none');
        hdr.style.display = any ? '' : 'none';
      });
    });
  });

  // Group collapse/expand
  tbody.querySelectorAll('tr.grp-hdr').forEach(hdr => {
    hdr.addEventListener('click', function() {
      const gid = this.dataset.gid;
      const rs = [...tbody.querySelectorAll(`tr[data-group="${gid}"]`)];
      const collapsed = rs[0] && rs[0].style.display === 'none';
      rs.forEach(r => r.style.display = collapsed ? '' : 'none');
      this.querySelector('.chev').textContent = collapsed ? '▾' : '▸';
    });
  });

  return wrap;
}
```

## ── CELL 8: pham metadata summary ─────────────────────────────────────────

```js
html`${(() => {
  if (result.status !== "ok" || !result.phamStats) return "";

  const { refGeneLength, refPhageCluster, phamStats, clusterStats } = result;
  const fmt  = (n) => n != null ? `${n} bp` : "—";
  const fmtZ = (z) => (z >= 0 ? "+" : "") + z.toFixed(1);

  // Pick the most relevant comparitor (cluster preferred if available)
  const cmpStats = (clusterStats && clusterStats.count > 1) ? clusterStats : phamStats;
  const cmpLabel = (clusterStats && clusterStats.count > 1) ? refPhageCluster : `pham ${result.refPham}`;
  let sentence = "";
  if (refGeneLength && cmpStats) {
    if (refGeneLength === cmpStats.mode) {
      // Mode match is the most meaningful result — lead with it
      sentence = `Your gene (${fmt(refGeneLength)}) <strong>matches the mode</strong> for ${cmpLabel} — `
               + `${cmpStats.modeFreqPct}% of members share this exact length.`;
    } else if (cmpStats.stdDev > 0) {
      const z = (refGeneLength - cmpStats.mean) / cmpStats.stdDev;
      const verdict = Math.abs(z) < 0.5 ? "typical for"
                    : Math.abs(z) < 1.0 ? "slightly atypical for"
                    : "notably atypical for";
      sentence = `Your gene (${fmt(refGeneLength)}) is <strong>${verdict} ${cmpLabel}</strong> `
               + `(mean ${fmt(cmpStats.mean)} ± ${fmt(cmpStats.stdDev)}, z = ${fmtZ(z)}).`;
    }
  }

  const row = (label, ps, cs) => `
    <tr>
      <td style="padding:5px 10px;color:#475569">${label}</td>
      <td style="padding:5px 10px;text-align:right">${ps}</td>
      <td style="padding:5px 10px;text-align:right">${cs}</td>
    </tr>`;

  const cs = clusterStats;
  let out = `
  <div style="padding:12px 16px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:0.88em;line-height:1.6">
    <p style="margin:0 0 8px 0">${sentence}</p>
    <table style="border-collapse:collapse;width:100%">
      <thead>
        <tr style="border-bottom:2px solid #cbd5e1;font-weight:700;color:#1e293b">
          <th style="padding:5px 10px;text-align:left;font-weight:600;color:#64748b"> </th>
          <th style="padding:5px 10px;text-align:right">All pham ${result.refPham}</th>
          <th style="padding:5px 10px;text-align:right">${refPhageCluster ? refPhageCluster + " cluster" : "—"}</th>
        </tr>
      </thead>
      <tbody style="color:#334155">
        ${row("Genes (n)",       phamStats.count,                       cs ? cs.count : "—")}
        ${row("Range",           `${fmt(phamStats.min)}–${fmt(phamStats.max)}`, cs ? `${fmt(cs.min)}–${fmt(cs.max)}` : "—")}
        ${row("Mean ± SD",       `${fmt(phamStats.mean)} ± ${fmt(phamStats.stdDev)}`, cs ? `${fmt(cs.mean)} ± ${fmt(cs.stdDev)}` : "—")}
        ${row("Mode (freq)",      `${fmt(phamStats.mode)} (${phamStats.modeFreqPct}%)`, cs ? `${fmt(cs.mode)} (${cs.modeFreqPct}%)` : "—")}
        ${row("Your gene",       `<strong>${fmt(refGeneLength)}</strong>`, `<strong>${fmt(refGeneLength)}</strong>`)}
      </tbody>
    </table>
  </div>`;
  return out;
})()}`
```

## ── CELL 9: loading indicator ──────────────────────────────────────────────

Observable shows a loading spinner automatically while \`result\` is pending, but this cell provides a friendlier status line.
```html
<div style="color:#64748b;font-size:0.85em;margin-top:8px">
  \${result.status === "idle"   ? "" :
    result.status === "error"  ? "" :
    result.rows.length === 0   ? "✅ Done — no syntenic genes found." :
    \`✅ Loaded \${result.rows.length} syntenic gene(s).\`}
</div>\`
```
