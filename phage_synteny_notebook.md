# Phage Genome Annotation – Synteny Helper
Observable notebook source — paste each cell into a new cell in observablehq.com

## ── CELL 1: title ──────────────────────────────────────────────────────────

```md
# 🧬 Phage Genome Annotation – Synteny Helper
Enter a phage name and select a gene. This tool queries [Phamerator](https://phamerator.org) to find every other phage in the database that shares the same pham in a conserved genomic neighbourhood, then summarises the results for annotation.

**What you get:**
- **Synteny table** — all syntenic genes grouped by cluster, filterable by synteny type and strand direction. Draft genomes are flagged 🚧.
- **Gene length statistics** — pham-wide and cluster-specific distributions (mean, mode, SD), with context on how typical your gene's length is.
- **Suggested annotation statement** — auto-generated from neighbour gene functions, ready to copy.

## Step 1: Log in to phamerator
```

## ── CELL 2: Phamerator imports  ───────────────────────────────────────────────
```js
import {
  terms,
  getPhameratorData,
  user,
  formWithSubmit,
  styles
} with { formData } from "@scresawn/phamerator-api-utilities"
```

## ── CELL 3: Phamerator terms ───────────────────────────────────────────────

```js
terms
```

## ── CELL 4: Phamerator login ───────────────────────────────────────────────
```js
viewof formData = {
  let formData = "Signed In";
  formData = formWithSubmit(html`
  <form id="login-form" class="login-form">
  <h4>Phamerator.org Login</h4>
    <div class="flex-input">
      <label for="email">Email</label>
      <input name="email" type="email" value="">
    </div>
    <div class="flex-input">
      <label for="password">Password</label>
      <input name="password" type="password" value="">
    </div>
    <div><input name="submit" type="submit" value="LOGIN"></div>
  </form>
`);
  return formData;
}
```

## ── CELL 5: phage name input ───────────────────────────────────────────────
```md
Once you've logged in, you should see a selector appear below:
```

## ── CELL 6: Phage selection heading ─────────────────────────────────────────

```md
## Step 2: Select your gene of interest
```

## ── CELL 7: phage name input ───────────────────────────────────────────────

```js
viewof phageName = Inputs.text({
  label: "Phage name",
  placeholder: "e.g. Beanstalk",
  value: ""
})
```


## ── CELL 8: fetch reference phage ─────────────────────────────────────────

```js
refPhageResult = {
  const fetchGenome = async (name) => {
    const data = await getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}/`, user.email, user.password);
    if (data) return { data, isDraft: false };
    const draftData = await getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}_Draft/`, user.email, user.password);
    return { data: draftData, isDraft: !!draftData };
  };
  const pn = phageName?.trim().replace(/_Draft$/i, "");
  const mkEl = (d, label, color) => {
    const el = html`<span style="font-size:0.75em;color:${color}">${label}</span>`;
    Object.assign(el, d);
    return el;
  };
  if (!pn)
    return mkEl({ data: null, isDraft: false }, "─ enter a phage name", "#94a3b8");
  const r = await fetchGenome(pn);
  return r?.data
    ? mkEl({ data: r.data, isDraft: r.isDraft }, `✓ ${pn} loaded`, "#16a34a")
    : mkEl({ data: null, isDraft: false }, `✗ ${pn} not found on Phamerator`, "#dc2626");
}
```

## ── CELL 9: gene selector ──────────────────────────────────────────────────

```js
viewof selectedGene = {
  const genes = refPhageResult?.data?.genes
    ? [...refPhageResult.data.genes].sort((a, b) => (a.stop || 0) - (b.stop || 0))
    : [];
  return Inputs.select(genes, {
    label: "Gene",
    format: g => `Gene ${g.name}  (${Number(g.start).toLocaleString()}–${Number(g.stop).toLocaleString()})`
  });
}
```

## ── CELL 10: start site override ───────────────────────────────────────────

```js
viewof customStart = {
  // Auto-populates from the selected gene; annotator can override.
  // Resets automatically whenever a different gene is selected.
  const apiStart = selectedGene?.start ?? null;
  const wrap = document.createElement('div');
  wrap.style.cssText = "display:flex;flex-direction:column;gap:2px";

  const input = Inputs.number({
    label: "Start site",
    value: apiStart,
    step: 1,
    min: 0
  });
  wrap.appendChild(input);

  if (apiStart != null) {
    const hint = document.createElement('span');
    hint.style.cssText = "font-size:0.75em;color:#94a3b8;margin-left:2px";
    hint.textContent = `API value: ${Number(apiStart).toLocaleString()} — edit to override for length calculation`;
    wrap.appendChild(hint);
  }

  // Forward the input's value and events through the wrapper
  wrap.value = input.value;
  input.addEventListener('input', () => { wrap.value = input.value; wrap.dispatchEvent(new Event('input')); });
  return wrap;
}
```

## ── CELL 11: core data-fetching logic ───────────────────────────────────────
```js
result = {
  const pn = phageName?.trim().replace(/_Draft$/i, "");

  const fetchGenome = async (name) => {
    const data = await getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}/`, user.email, user.password);
    if (data) return { data, isDraft: false };
    const draftData = await getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}_Draft/`, user.email, user.password);
    return { data: draftData, isDraft: !!draftData };
  };

  // Returns a compact <span> that also carries all data properties.
  // Downstream cells read result.status, result.rows, etc. off the element.
  const mkEl = (d) => {
    const idle = d.status === "idle";
    const ok   = d.status === "ok";
    const n    = (d.rows || []).length;
    const label = idle ? "─ waiting for input"
                : ok   ? `✓ ${n} syntenic gene${n !== 1 ? "s" : ""} found`
                       : `✗ ${d.message}`;
    const color = idle ? "#94a3b8" : ok ? "#16a34a" : "#dc2626";
    const el = html`<span style="font-size:0.75em;color:${color}">${label}</span>`;
    Object.assign(el, d);
    return el;
  };

  if (!pn || !selectedGene) return mkEl({ status: "idle" });

  let data;
  try {
    // 1. Use the already-fetched reference phage
    const refPhage = refPhageResult?.data;
    if (!refPhage)
      throw new Error(`Phage '${pn}' not found on Phamerator.`);
    const genes = refPhage.genes;
    if (!genes || genes.length === 0)
      throw new Error(`No gene data found for "${pn}". The genome may not be phamerated yet.`);

    // 2. Sort and locate the selected gene by its stop position
    genes.sort((a, b) => (a.stop || 0) - (b.stop || 0));
    const geneIdx = genes.findIndex(g => g.stop === selectedGene.stop);
    if (geneIdx === -1)
      throw new Error(`Selected gene not found in sorted gene list.`);

    const refGene     = genes[geneIdx];
    const refPham     = refGene.phamName;
    const geneNumber  = refGene.name;
    const refDir      = refGene.direction || "forward";
    const refGeneFunc = refGene.genefunction || "";

    // Upstream/downstream in transcription order (swap for reverse-strand genes)
    const upIdx = refDir === "reverse" ? geneIdx + 1 : geneIdx - 1;
    const dnIdx = refDir === "reverse" ? geneIdx - 1 : geneIdx + 1;
    const refUpPham = (upIdx >= 0 && upIdx < genes.length) ? genes[upIdx].phamName : null;
    const refDnPham = (dnIdx >= 0 && dnIdx < genes.length) ? genes[dnIdx].phamName : null;
    const refUpFunc = (upIdx >= 0 && upIdx < genes.length) ? (genes[upIdx].genefunction || "") : "";
    const refDnFunc = (dnIdx >= 0 && dnIdx < genes.length) ? (genes[dnIdx].genefunction || "") : "";

    const effectiveStart  = (customStart != null && !isNaN(customStart)) ? customStart : refGene.start;
    const refGeneLength   = Math.abs(refGene.stop - effectiveStart) + 1;
    const refPhageCluster       = refPhage.clusterSubcluster || refPhage.cluster || null;
    const refPhageParentCluster = refPhage.cluster || null;
    var isOrpham    = false;
    const base = {
      status: "ok", phageName: pn, geneNumber, refDir, isOrpham,
      refGeneFunc, refUpFunc, refDnFunc,
      refPham, refUpPham, refDnPham,
      refGeneLength, refPhageCluster, refPhageParentCluster
    };

    const phageData = new Map();
    const rows = [];
    let phamStats = null, clusterStats = null, phamExactCount = 0, clusterExactCount = 0;

    const phamGenes = await getPhameratorData(
      dataset, `/phamily/${refPham}`, user.email, user.password
    );
    const members = phamGenes.filter(g => g.phageID !== pn);

    if (members.length === 0) {
      base.isOrpham = true;
      // 3a. Orpham mode — no pham to search by; find phages that share the same
      //     upstream and/or downstream pham landmarks, then identify the gene in between.
      if (!refUpPham && !refDnPham)
        return mkEl({ ...base, phamStats: null, clusterStats: null,
                      phamExactCount: 0, clusterExactCount: 0, rows: [] });

      const [upPhamGenes, dnPhamGenes] = await Promise.all([
        refUpPham ? getPhameratorData(dataset, `/phamily/${refUpPham}`, user.email, user.password) : Promise.resolve([]),
        refDnPham ? getPhameratorData(dataset, `/phamily/${refDnPham}`, user.email, user.password) : Promise.resolve([])
      ]);

      const candidatePhageIds = [...new Set([
        ...(upPhamGenes || []).map(g => g.phageID),
        ...(dnPhamGenes || []).map(g => g.phageID)
      ].filter(id => id !== pn))];

      // Fetch all candidate phage genomes in parallel
      await Promise.all(
        candidatePhageIds.map(async name => {
          try {
            const { data, isDraft } = await fetchGenome(name);
            phageData.set(name, data
              ? { cluster: data.clusterSubcluster || data.cluster || "—", parentCluster: data.cluster || null, genes: data.genes, isDraft }
              : { cluster: "—", parentCluster: null, genes: [], isDraft: false }
            );
          } catch { phageData.set(name, { cluster: "—", genes: [], isDraft: false }); }
        })
      );

      // Scan every gene in each candidate phage for a matching neighborhood
      for (const phageId of candidatePhageIds) {
        const meta   = phageData.get(phageId) || { cluster: "—", genes: [], isDraft: false };
        const cGenes = meta.genes;
        if (!cGenes || cGenes.length === 0) continue;
        for (let ci = 0; ci < cGenes.length; ci++) {
          const cDir   = cGenes[ci].direction || "forward";
          const cUpIdx = cDir === "reverse" ? ci + 1 : ci - 1;
          const cDnIdx = cDir === "reverse" ? ci - 1 : ci + 1;
          const upPham = (cUpIdx >= 0 && cUpIdx < cGenes.length) ? cGenes[cUpIdx].phamName : null;
          const dnPham = (cDnIdx >= 0 && cDnIdx < cGenes.length) ? cGenes[cDnIdx].phamName : null;
          const upMatch = refUpPham !== null && upPham === refUpPham;
          const dnMatch = refDnPham !== null && dnPham === refDnPham;
          if (!upMatch && !dnMatch) continue;
          rows.push({
            phage:         phageId,
            geneNumber:    cGenes[ci].name,
            cluster:       meta.cluster,
            parentCluster: meta.parentCluster || null,
            sortKey:       meta.cluster || "~",
            direction:     cDir,
            genefunction:  cGenes[ci].genefunction || "",
            candidatePham: cGenes[ci].phamName || null,
            isDraft:       meta.isDraft || false,
            upPham, dnPham, upMatch, dnMatch,
            twoSided:      upMatch && dnMatch
          });
        }
      }

    } else {
      // Fetch phage metadata (cluster/genes) in parallel, deduped by phage
      const uniquePhageNames = [...new Set(members.map(g => g.phageID))];
      await Promise.all(
        uniquePhageNames.map(async name => {
          try {
            const { data, isDraft } = await fetchGenome(name);
            phageData.set(name, data
              ? { cluster: data.clusterSubcluster || data.cluster || "—", parentCluster: data.cluster || null, genes: data.genes, isDraft }
              : { cluster: "—", parentCluster: null, genes: [], isDraft: false }
            );
          } catch { phageData.set(name, { cluster: "—", genes: [] }); }
        })
      );

      // Evaluate synteny for each member gene
      await Promise.all(
        members.map(async candidate => {
          const cGenes = phageData.get(candidate.phageID)?.genes;
          if (!cGenes) return;
          const ci = cGenes.findIndex(g => Number(g.name) === Number(candidate.name));
          if (ci === -1) return;
          const cDir   = cGenes[ci].direction || "forward";
          const cUpIdx = cDir === "reverse" ? ci + 1 : ci - 1;
          const cDnIdx = cDir === "reverse" ? ci - 1 : ci + 1;
          const upPham = (cUpIdx >= 0 && cUpIdx < cGenes.length) ? cGenes[cUpIdx].phamName : null;
          const dnPham = (cDnIdx >= 0 && cDnIdx < cGenes.length) ? cGenes[cDnIdx].phamName : null;
          const upMatch = refUpPham !== null && upPham === refUpPham;
          const dnMatch = refDnPham !== null && dnPham === refDnPham;
          if (!upMatch && !dnMatch) return;
          const meta = phageData.get(candidate.phageID) || { cluster: "—" };
          rows.push({
            phage:        candidate.phageID,
            geneNumber:   candidate.name,
            cluster:      meta.cluster,
            parentCluster: meta.parentCluster || null,
            sortKey:      meta.cluster || "~",
            direction:    cDir,
            genefunction: cGenes[ci].genefunction || "",
            isDraft:      meta.isDraft || false,
            upPham, dnPham, upMatch, dnMatch,
            twoSided:     upMatch && dnMatch
          });
        })
      );

      // Compute pham-wide statistics
      const allLengths = phamGenes.map(g => Math.abs(g.stop - g.start) + 1).filter(l => l > 0);
      const clusterLengths = phamGenes
        .filter(g => {
          if (g.phageID === pn) return true;
          const m = phageData.get(g.phageID);
          return m && m.cluster === refPhageCluster;
        })
        .map(g => Math.abs(g.stop - g.start) + 1)
        .filter(l => l > 0);

      const computeStats = (lengths) => {
        if (lengths.length === 0) return null;
        const sorted = [...lengths].sort((a, b) => a - b);
        const mean = sorted.reduce((a, b) => a + b, 0) / sorted.length;
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
          count: sorted.length, min: sorted[0], max: sorted[sorted.length - 1],
          mean: Math.round(mean), mode,
          modeFreqPct: Math.round(100 * maxFreq / sorted.length),
          stdDev: Math.round(stdDev)
        };
      };

      phamStats    = computeStats(allLengths);
      clusterStats = computeStats(clusterLengths);
      phamExactCount    = allLengths.filter(l => l === refGeneLength).length;
      clusterExactCount = clusterLengths.filter(l => l === refGeneLength).length;
    }

    rows.sort((a, b) =>
      a.sortKey.localeCompare(b.sortKey) || a.phage.localeCompare(b.phage)
    );

    data = {
      ...base, phamStats, clusterStats, rows,
      phamExactCount, clusterExactCount
    };

  } catch (err) {
    data = { status: "error", message: err.message };
  }

  return mkEl(data);
}
```

## ── CELL 12: results heading ─────────────────────────────────────────────────

```md
## Results
```


## ── CELL 13: summary badges ─────────────────────────────────────────────────

```js
html`${(() => {
  if (result.status === "idle")
    return `<p style="color:#888">Enter a phage name and gene number, then click <strong>Find syntenic genes</strong>.</p>`;
  if (result.status === "error")
    return `<div style="padding:10px;background:#fee2e2;border-radius:6px;color:#b91c1c">⚠️ ${result.message}</div>`;

  const { rows, phageName, geneNumber, refPham, refUpPham, refDnPham, isOrpham } = result;
  const two = rows.filter(r => r.twoSided).length;
  const one = rows.length - two;
  const phageUrl = `https://phagesdb.org/phages/${encodeURIComponent(phageName.replace(/_Draft$/i, ""))}/`;
  const phamUrl  = (p) => `https://phagesdb.org/phams/${encodeURIComponent(p)}/`;

  return `
  <div style="margin-bottom:6px;font-size:0.88em;color:#475569">
    Phage: <a href="${phageUrl}" target="_blank" style="color:#2563eb;font-weight:600">${phageName}</a>
    &nbsp;·&nbsp; Gene #${geneNumber}
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
    <div style="padding:8px 16px;background:${isOrpham ? '#fff7ed' : '#eff6ff'};border-radius:8px;border:1px solid ${isOrpham ? '#fed7aa' : '#bfdbfe'}">
      <b>Pham of interest:</b> <a href="${phamUrl(refPham)}" target="_blank" style="color:#1d4ed8">${refPham}</a>
      ${isOrpham ? '<br><p style="margin:0;padding:0;font-size:0.75em;">⚠️ This is an orpham</p>' : ''}
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

## ── CELL 14: pham metadata summary ─────────────────────────────────────────

```js
html`${(() => {
  if (result.status !== "ok") return "";
  if (!result.phamStats) {
    if (result.isOrpham)
      return `<div style="padding:8px 12px;border-radius:6px;color:#92400e;font-size:0.85em">ℹ Gene length statistics are not available for orpham genes — there is no pham distribution to compare against.</div>`;
    return `<div style="padding:8px 12px;background:#fef9c3;border-radius:6px;color:#854d0e;font-size:0.85em">⚠ Gene length stats unavailable — pham may have no members with valid coordinates.</div>`;
  }
  try {

  const { refGeneLength, refPhageCluster, phamStats, clusterStats, phamExactCount, clusterExactCount } = result;
  const fmt  = (n) => n != null ? `${n} bp` : "—";
  const fmtZ = (z) => (z >= 0 ? "+" : "") + z.toFixed(1);

  // Pick the most relevant comparitor (cluster preferred if available)
  const useCluster = clusterStats && clusterStats.count > 1;
  const cmpStats      = useCluster ? clusterStats : phamStats;
  const cmpLabel      = useCluster ? `cluster ${refPhageCluster}` : `pham ${result.refPham}`;
  const cmpExactCount = useCluster ? clusterExactCount : phamExactCount;

  const fmtExact = (n, total) => `${n} (${Math.round(100 * n / total)}%)`;

  let sentence = "";
  if (refGeneLength && cmpStats) {
    if (refGeneLength === cmpStats.mode) {
      // Mode match is the most meaningful result — lead with it
      sentence = `This gene (${fmt(refGeneLength)}) <strong>matches the mode</strong> for ${cmpLabel} — `
               + `${cmpStats.modeFreqPct}% of members share this exact length.`;
    } else if (cmpStats.stdDev === 0) {
      // All members share the same length but this gene differs
      const exactScope = useCluster ? `${refPhageCluster} cluster pham members` : `pham ${result.refPham} members`;
      sentence = `This gene (${fmt(refGeneLength)}) is <strong>notably atypical for ${cmpLabel}</strong> — `
               + `all ${cmpStats.count} ${exactScope} share a length of ${fmt(cmpStats.mode)}.`;
    } else {
      const z = (refGeneLength - cmpStats.mean) / cmpStats.stdDev;
      const verdict = Math.abs(z) < 0.5 ? "typical for"
                    : Math.abs(z) < 1.0 ? "slightly atypical for"
                    : "notably atypical for";
      const exactScope = useCluster ? `${refPhageCluster} cluster pham members` : `pham ${result.refPham} members`;
      const exactNote = cmpExactCount > 0
        ? ` ${cmpExactCount} of ${cmpStats.count} (${Math.round(100 * cmpExactCount / cmpStats.count)}%) ${exactScope} share this exact length.`
        : ` No other ${exactScope} share this exact length.`;
      sentence = `This gene (${fmt(refGeneLength)}) is <strong>${verdict} ${cmpLabel}</strong> `
               + `(mean ${fmt(cmpStats.mean)} ± ${fmt(cmpStats.stdDev)}, ${fmtZ(z)} SDs from mean).<br>${exactNote}`;
    }
  }

  const row = (label, ps, cs) => `
    <tr>
      <td style="padding:5px 10px;color:#475569">${label}</td>
      <td style="padding:5px 10px;text-align:right">${ps}</td>
      <td style="padding:5px 10px;text-align:right">${cs}</td>
    </tr>`;

  const cs = clusterStats;
  // Strip HTML for clipboard — replace <br> with space, remove remaining tags
  const plainSentence = sentence.replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '').trim();
  const escapedPlain  = plainSentence.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

  let out = `
  <div style="padding:12px 16px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:0.88em;line-height:1.6">
    <div style="font-weight:700;color:#1e293b;margin-bottom:2px">Gene length normalcy for pham</div>
    <div style="margin:0 0 8px 0;display:flex;align-items:flex-start;gap:8px">
      <span style="flex:1;line-height:1.6">${sentence}</span>
      ${sentence ? `<button onclick="navigator.clipboard.writeText(this.dataset.text).then(()=>{this.textContent='Copied!';setTimeout(()=>{this.textContent='Copy'},1500)})" data-text="${escapedPlain}" style="flex-shrink:0;padding:2px 10px;border-radius:5px;border:1px solid #cbd5e1;background:#f8fafc;cursor:pointer;font-size:0.82em;font-weight:600;color:#334155;margin-top:2px">Copy</button>` : ''}
    </div>
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
        ${row("This gene",       `<strong>${fmt(refGeneLength)}</strong>`, `<strong>${fmt(refGeneLength)}</strong>`)}
        ${row("Same length",     fmtExact(phamExactCount, phamStats.count), cs ? fmtExact(clusterExactCount, cs.count) : "—")}
      </tbody>
    </table>
  </div>`;
  return out;
  } catch (err) {
    console.error("Gene length table:", err);
    return `<div style="padding:8px 12px;background:#fee2e2;border-radius:6px;color:#b91c1c;font-size:0.8em;white-space:pre-wrap;font-family:monospace">⚠ Gene length table error:\n${err?.stack ?? String(err)}</div>`;
  }
})()}`
```

## ── CELL 15: syntenic function frequency table ─────────────────────────────

```js
html`${(() => {
  if (result.status !== "ok" || result.rows.length === 0) return "";

  const { rows, isOrpham, refPham } = result;
  const total = rows.length;

  // Tally function calls broken down by synteny type
  const tally = new Map();
  for (const r of rows) {
    const fn = r.genefunction?.trim() || "NKF";
    if (!tally.has(fn)) tally.set(fn, { total: 0, two: 0, up: 0, dn: 0 });
    const t = tally.get(fn);
    t.total++;
    if (r.twoSided)     t.two++;
    else if (r.upMatch) t.up++;
    else                t.dn++;
  }

  // Sort: two-sided count desc → total desc → alpha
  const sorted = [...tally.entries()].sort(([a, at], [b, bt]) =>
    bt.two - at.two || bt.total - at.total || a.localeCompare(b)
  );

  const pct = (n) => n > 0 ? `${n} <span style="color:#94a3b8">(${Math.round(100 * n / total)}%)</span>` : `<span style="color:#cbd5e1">—</span>`;

  const title = isOrpham
    ? `Functions at this genomic position <small style="font-weight:400;color:#64748b">(genes occupying the orpham's slot in syntenic phages)</small>`
    : `Functions called for pham ${refPham} in syntenic phages`;

  const uninformative = new Set(["nkf", "hypothetical protein", "no known function"]);
  const fnRows = sorted.map(([fn, t]) => {
    const pct_val = t.total / total;
    const informative = !uninformative.has(fn.toLowerCase());
    const bg = (informative && pct_val > 0.50) ? '#bbf7d0'   // deep green  > 50%
             : (informative && pct_val > 0.25) ? '#dcfce7'   // mid green   > 25%
             : (informative && pct_val > 0.10) ? '#f0fdf4'   // pale green  > 10%
             : '';
    const bold = informative && pct_val > 0.25;
    return `<tr style="${bg ? `background:${bg}` : ''}">
      <td style="padding:5px 10px;${bold ? 'font-weight:600' : ''}">${fn}</td>
      <td style="padding:5px 10px;text-align:right">${pct(t.two)}</td>
      <td style="padding:5px 10px;text-align:right">${pct(t.up)}</td>
      <td style="padding:5px 10px;text-align:right">${pct(t.dn)}</td>
      <td style="padding:5px 10px;text-align:right;font-weight:600">${pct(t.total)}</td>
    </tr>`;
  }).join("");

  return `
  <div style="padding:12px 16px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:0.88em;line-height:1.6;margin-top:10px">
    <div style="font-weight:700;color:#1e293b;margin-bottom:2px">${title}</div>
    <table style="border-collapse:collapse;width:100%">
      <thead>
        <tr style="border-bottom:2px solid #cbd5e1;color:#64748b;font-size:0.9em">
          <th style="padding:5px 10px;text-align:left;font-weight:600">Function</th>
          <th style="padding:5px 10px;text-align:right;font-weight:600">🔗 Two-sided</th>
          <th style="padding:5px 10px;text-align:right;font-weight:600">↑ Upstream only</th>
          <th style="padding:5px 10px;text-align:right;font-weight:600">↓ Downstream only</th>
          <th style="padding:5px 10px;text-align:right;font-weight:600">Total (n=${total})</th>
        </tr>
      </thead>
      <tbody style="color:#334155">${fnRows}</tbody>
    </table>
  </div>`;
})()}`
```

## ── CELL 16: synteny statement generator ────────────────────────────────────

```js
{
  if (result.status !== "ok") return html``;

  const { rows, refGeneFunc, refUpFunc, refDnFunc, refPhageCluster, isOrpham } = result;
  const fn = (f) => f || "NKF";

  // Pick best comparison phage: same-cluster non-Draft > same-cluster Draft > any non-Draft > any Draft
  const best = (candidates) => {
    if (!candidates.length) return null;
    const sameCluster = candidates.filter(r => r.cluster === refPhageCluster);
    const prefer = (list) => list.find(r => !r.isDraft) || list[0];
    return sameCluster.length > 0 ? prefer(sameCluster) : prefer(candidates);
  };

  const anyUp    = rows.filter(r => r.upMatch);
  const anyDn    = rows.filter(r => r.dnMatch);
  const twoSided = rows.filter(r => r.twoSided);

  let statement;
  if (rows.length === 0) {
    statement = "No synteny.";
  } else if (isOrpham) {
    if (twoSided.length > 0) {
      const p = best(twoSided);
      statement = `${fn(refGeneFunc)}. Upstream gene is ${fn(refUpFunc)}, downstream gene is ${fn(refDnFunc)}, synteny with phage ${p.phage}.`;
    } else {
      statement = "No synteny";
    }
  } else if (twoSided.length > 0) {
    // Both sides match in a single phage
    const p = best(twoSided);
    statement = `${fn(refGeneFunc)}. Upstream gene is ${fn(refUpFunc)}, downstream gene is ${fn(refDnFunc)}, synteny with phage ${p.phage}.`;
  } else if (anyUp.length > 0 && anyDn.length > 0) {
    // One-sided on each side but from different phages
    const pUp = best(anyUp);
    const pDn = best(anyDn);
    statement = `${fn(refGeneFunc)}. Upstream gene is ${fn(refUpFunc)}, synteny with phage ${pUp.phage}. Downstream gene is ${fn(refDnFunc)}, synteny with phage ${pDn.phage}.`;
  } else if (anyUp.length > 0) {
    const p = best(anyUp);
    statement = `${fn(refGeneFunc)}. Upstream gene is ${fn(refUpFunc)}, synteny with phage ${p.phage}.`;
  } else {
    const p = best(anyDn);
    statement = `${fn(refGeneFunc)}. Downstream gene is ${fn(refDnFunc)}, synteny with phage ${p.phage}.`;
  }

  // Warn if any function fields are empty so student knows what to fill in
  const missing = [
    !refGeneFunc                      && "gene of interest",
    anyUp.length > 0 && !refUpFunc    && "upstream neighbour",
    anyDn.length > 0 && !refDnFunc    && "downstream neighbour"
  ].filter(Boolean);

  const wrap = document.createElement('div');
  wrap.style.cssText = "padding:12px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;font-size:0.9em";

  const label = document.createElement('div');
  label.style.cssText = "font-weight:700;color:#166534;margin-bottom:6px";
  label.textContent = "Suggested synteny statement:";
  wrap.appendChild(label);

  if (isOrpham) {
    const orphamNote = document.createElement('div');
    orphamNote.style.cssText = "font-size:0.8em;color:#92400e;background:#fff7ed;border-radius:4px;padding:4px 10px;margin-bottom:8px";
    orphamNote.textContent = "⚠ Orpham gene — the statement reflects neighbour gene context only, and only two-sided synteny will be called by this tool.";
    wrap.appendChild(orphamNote);
  }

  const box = document.createElement('div');
  box.style.cssText = "background:#fff;border:1px solid #d1fae5;border-radius:6px;padding:10px 14px;font-style:italic;color:#1e293b;line-height:1.5;margin-bottom:8px";
  box.textContent = statement;
  wrap.appendChild(box);

  const btnRow = document.createElement('div');
  btnRow.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap";

  const copyBtn = document.createElement('button');
  copyBtn.textContent = "Copy";
  copyBtn.style.cssText = "padding:3px 14px;border-radius:6px;border:1px solid #6ee7b7;background:#ecfdf5;cursor:pointer;font-size:0.85em;font-weight:600;color:#065f46";
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(statement).then(() => {
      copyBtn.textContent = "Copied!";
      setTimeout(() => copyBtn.textContent = "Copy", 1500);
    });
  });
  btnRow.appendChild(copyBtn);

  if (missing.length > 0 && statement != "No synteny") {
    const warn = document.createElement('span');
    warn.style.cssText = "color:#92400e;font-size:0.82em";
    warn.textContent = `⚠ No function data for: ${missing.join(", ")} — replace NKF manually.`;
    btnRow.appendChild(warn);
  }

  wrap.appendChild(btnRow);
  return wrap;
}
```

## ── CELL 17: synteny table ──────────────────────────────────────────────────────

```js
{
  if (result.status !== "ok" || result.rows.length === 0) return html``;

  const { rows, refUpPham, refDnPham, isOrpham } = result;
  const phamUrl = (p) => `https://phagesdb.org/phams/${encodeURIComponent(p)}/`;

  const nTwo  = rows.filter(r => r.twoSided).length;
  const nUp   = rows.filter(r => !r.twoSided && r.upMatch).length;
  const nDown = rows.filter(r => !r.twoSided && r.dnMatch).length;
  const nFwd  = rows.filter(r => r.direction !== "reverse").length;
  const nRev  = rows.filter(r => r.direction === "reverse").length;

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

  const dirTag = dir => dir === "reverse"
    ? `<span style="color:#dc2626;font-weight:700" title="Reverse strand">←</span>`
    : `<span style="color:#2563eb;font-weight:700" title="Forward strand">→</span>`;

  const orphamBanner = isOrpham ? `
  <div style="padding:10px 14px;background:#fff7ed;border-radius:8px;border:1px solid #fed7aa;color:#92400e;font-size:0.88em;margin-bottom:10px">
    <strong>⚠ Orpham gene</strong> — this gene's pham has no other members.
    The results below show other phages that carry a gene in the same genomic neighbourhood (flanked by the same upstream and/or downstream phams), but <strong>that gene may be entirely unrelated</strong>.
  </div>` : "";

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
    .gene-fn { color:#64748b; font-size:0.8em; display:block; margin-top:1px; }
  </style>
  ${orphamBanner}
  <div style="margin-bottom:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
    <span style="font-size:0.82em;color:#64748b;margin-right:2px">Synteny:</span>
    <button class="sfbtn active" data-ftype="syn" data-filter="all" >All (${rows.length})</button>
    <button class="sfbtn"        data-ftype="syn" data-filter="two" >🔗 Two-sided (${nTwo})</button>
    <button class="sfbtn"        data-ftype="syn" data-filter="up"  >↑ Upstream only (${nUp})</button>
    <button class="sfbtn"        data-ftype="syn" data-filter="down">↓ Downstream only (${nDown})</button>
  </div>
  <div style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
    <span style="font-size:0.82em;color:#64748b;margin-right:2px">Direction:</span>
    <button class="sfbtn active" data-ftype="dir" data-filter="all" >All (${rows.length})</button>
    <button class="sfbtn"        data-ftype="dir" data-filter="fwd" >→ Forward (${nFwd})</button>
    <button class="sfbtn"        data-ftype="dir" data-filter="rev" >← Reverse (${nRev})</button>
  </div>
  <div style="overflow-x:auto;max-height:70vh;overflow-y:auto">
  <table class="syn-tbl">
    <thead><tr>
      <th>Phage</th><th>Gene #</th>${isOrpham ? '<th>Gene pham</th>' : ''}<th>Cluster</th><th style="text-align:center">Dir.</th>
      <th>Upstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refUpPham ?? "—"}</small></th>
      <th>Downstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refDnPham ?? "—"}</small></th>
      <th>Synteny</th>
    </tr></thead>
    <tbody>`;

  let gi = 0;
  for (const [groupKey, groupRows] of groups) {
    const gid = `g${gi++}`;
    html_out += `<tr class="grp-hdr" data-gid="${gid}">
      <td colspan="${isOrpham ? 8 : 7}"><span class="chev">▾</span> ${groupKey} (${groupRows.length} gene${groupRows.length>1?"s":""})</td></tr>`;
    for (const r of groupRows) {
      const syn = r.twoSided ? "two" : r.upMatch ? "up" : "down";
      const dir = r.direction === "reverse" ? "rev" : "fwd";
      const orphamPhamCell = isOrpham
        ? (r.candidatePham
            ? `<td style="text-align:center"><a href="${phamUrl(r.candidatePham)}" target="_blank" style="color:#2563eb">${r.candidatePham}</a></td>`
            : `<td style="text-align:center;color:#94a3b8;font-style:italic">orpham</td>`)
        : "";
      html_out += `
      <tr data-group="${gid}" data-syn="${syn}" data-dir="${dir}">
        <td>
          <a href="https://phagesdb.org/phages/${r.phage.replace(/_Draft$/i, "")}/" target="_blank">${r.phage}</a>${r.isDraft ? '&nbsp;<span title="Draft genome" style="font-size:0.9em">🚧</span>' : ""}
          ${r.genefunction ? `<span class="gene-fn">${r.genefunction}</span>` : ""}
        </td>
        <td style="text-align:center">${r.geneNumber}</td>
        ${orphamPhamCell}
        <td>${r.cluster || "—"}</td>
        <td style="text-align:center">${dirTag(r.direction)}</td>
        <td ${cellStyle(r.upMatch, refUpPham)}>${r.upPham ?? "—"}</td>
        <td ${cellStyle(r.dnMatch, refDnPham)}>${r.dnPham ?? "—"}</td>
        <td style="text-align:center">${synTag(r)}</td>
      </tr>`;
    }
  }
  html_out += `</tbody></table></div>`;

  // Create DOM node and wire up event listeners
  const wrap = document.createElement('div');
  wrap.innerHTML = html_out;
  const tbody = wrap.querySelector('tbody');

  // Two independent filters applied with AND logic
  let activeSyn = 'all', activeDir = 'all';
  const applyFilters = () => {
    tbody.querySelectorAll('tr[data-syn]').forEach(row => {
      const synOk = activeSyn === 'all' || row.dataset.syn === activeSyn;
      const dirOk = activeDir === 'all' || row.dataset.dir === activeDir;
      row.style.display = (synOk && dirOk) ? '' : 'none';
    });
    tbody.querySelectorAll('tr.grp-hdr').forEach(hdr => {
      const gid = hdr.dataset.gid;
      const any = [...tbody.querySelectorAll(`tr[data-group="${gid}"]`)].some(r => r.style.display !== 'none');
      hdr.style.display = any ? '' : 'none';
    });
  };

  wrap.querySelectorAll('.sfbtn').forEach(btn => {
    btn.addEventListener('click', function() {
      const ftype = this.dataset.ftype;
      wrap.querySelectorAll(`.sfbtn[data-ftype="${ftype}"]`).forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      if (ftype === 'syn') activeSyn = this.dataset.filter;
      else                 activeDir = this.dataset.filter;
      applyFilters();
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
