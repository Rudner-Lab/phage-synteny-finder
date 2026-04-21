# Orpham Synteny Scanner
Observable notebook source — paste each cell into a new cell in observablehq.com

## ── CELL 1: title ──────────────────────────────────────────────────────────

```md
# 🧬 Orpham Synteny Scanner
Enter a phage name. This tool scans every orpham in the phage and, for each one, finds all other phages that carry a gene in the same genomic neighbourhood (flanked by the same upstream and/or downstream phams).

**What you get:**
- **Per-orpham summary** — upstream/downstream pham context and hit counts.
- **Function tally** — which functions appear in the central candidate gene at the target genomic slot (between matched flanking phams).
- **Synteny table** — all syntenic genes grouped by cluster (collapsible per orpham).

## Step 1: Connect to Phamerator
```


## ── CELL 3: Abortable Phamerator API func ──────────────────────────────────
```js
getPhameratorData = (dataset, endpoint, apiKey, signal) => {
  return d3.json(`https://phamerator.org/api/${dataset}${endpoint}`, {
    headers: new Headers({
      Authorization: `Bearer ${apiKey}`
    }),
    signal
  });
}
```

## ── CELL 4: Phamerator terms ───────────────────────────────────────────────

```md
**Terms of use:** To use this notebook, first ensure that you have a [phamerator.org](https://phamerator.org) API key. You can create one by [signing up](https://phamerator.org/sign-up) for a [phamerator.org](https://phamerator.org) account and then clicking ***generate new API key*** in your [account settings](https://phamerator.org/account). Enter your key in the box [here](https://observablehq.com/@cresawn-labs/phamerator-api-utilities). You should only need to do this once. Protect your API key like you would a password. If you accidentally expose your key, [revoke it and generate a new key](https://phamerator.org/account).  Use of phamerator.org, the phamerator.org API, or data stored in the phamerator.org database, whether the use occurs here on https://observablehq.com or elsewhere, constitutes your agreement to the terms and policies of both [phamerator.org](https://phamerator.org/terms) and the SEA-PHAGES program's [phagesdb.org](https://phagesdb.org/terms/). In addition, when creating your own [observablehq.com](https://observablehq.com) notebooks that feature Phamerator.org data, you agree to prominently display these terms of use near the top of your notebook(s).
```

## ── CELL 5: Phamerator login ───────────────────────────────────────────────
```js
viewof formData = {
  const card = html`<div style="
    border:1px solid #e2e8f0; border-radius:8px;
    padding:16px 20px; max-width:460px;
    background:#f8fafc; font-family:system-ui,sans-serif;
  ">
    <p style="margin:0 0 12px;font-weight:600;font-size:0.95em;color:#1e293b">
      🔑 Phamerator API Key
    </p>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <input name="apiKey" type="password"
        placeholder="Paste your API key here"
        style="flex:1;padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;
               font-size:0.9em;font-family:monospace;color:#1e293b">
      <button type="button" id="connect-btn" style="
        padding:6px 16px; background:#1e40af; color:#fff;
        border:none; border-radius:6px; font-size:0.9em;
        cursor:pointer; white-space:nowrap;
      ">Connect</button>
    </div>
    <p style="margin:0 0 8px;font-size:0.8em;color:#64748b;line-height:1.5">
      To get your key: log in at <a href="https://phamerator.org" target="_blank" style="color:#1e40af">phamerator.org</a>,
      click your name in the top-right corner, then find <strong>API Access</strong> and click <strong>Generate new API key</strong>.
      <strong>Save it to a password manager immediately</strong> — Phamerator cannot show it again,
      and you will need to generate a new one if you lose it.
    </p>
    <div id="login-status" style="font-size:0.82em;color:#64748b;min-height:1.1em"></div>
  </div>`;

  card.value = null;

  const btn    = card.querySelector("#connect-btn");
  const input  = card.querySelector("[name=apiKey]");
  const status = card.querySelector("#login-status");

  btn.addEventListener("click", async () => {
    const apiKey = input.value.trim();
    if (!apiKey) { status.textContent = "Please enter an API key."; return; }
    status.textContent = "Connecting…";
    btn.disabled = true;
    try {
      const profile = await d3.json("https://phamerator.org/api/profile", {
        headers: new Headers({ Authorization: `Bearer ${apiKey}` })
      });
      card.value = { apiKey, datasets: profile.datasets ?? [] };
      card.dispatchEvent(new CustomEvent("input"));
      card.innerHTML = `<p style="margin:0;font-size:0.85em;color:#475569;font-family:system-ui,sans-serif">
        <span style="color:#16a34a">✓</span> Connected as <strong>${profile.username ?? profile.email ?? "unknown"}</strong>
      </p>`;
    } catch {
      status.textContent = "Connection failed — check your API key and try again.";
      btn.disabled = false;
    }
  });

  return card;
}
```

## ── CELL 6: dataset selector label ────────────────────────────────────────
```md
Select the dataset you're annotating:
```

## ── CELL 7: dataset selector ────────────────────────────────────────────────
```js
viewof dataset = Inputs.select((formData?.datasets ?? []).sort(), {
  label: "Dataset",
  value: "Actino_Draft"
})
```

## ── CELL 8: phage selection heading ─────────────────────────────────────────

```md
## Step 2: Enter your phage name
```

## ── CELL 9: phage name input ───────────────────────────────────────────────

```js
viewof phageName = Inputs.text({
  label: "Phage name",
  placeholder: "e.g. Beanstalk",
  value: "",
  submit: "Load"
})
```

## ── CELL 10: fetch reference phage ─────────────────────────────────────────

```js
refPhageResult = {
  const controller = new AbortController();
  invalidation.then(() => controller.abort());
  const signal = controller.signal;

  const fetchGenome = async (name) => {
    const data = await getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}/`, formData.apiKey, signal);
    if (data) return { data, isDraft: false };
    const draftData = await getPhameratorData(dataset, `/genome/${encodeURIComponent(name)}_Draft/`, formData.apiKey, signal);
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
  try {
    const r = await fetchGenome(pn);
    return r?.data
      ? mkEl({ data: r.data, isDraft: r.isDraft }, `✓ ${pn} loaded`, "#16a34a")
      : mkEl({ data: null, isDraft: false }, `✗ ${pn} not found on Phamerator`, "#dc2626");
  } catch (err) {
    if (err.name === "AbortError") throw err;
    return mkEl({ data: null, isDraft: false }, `✗ Error loading ${pn}: ${err.message}`, "#dc2626");
  }
}
```

## ── CELL 11: orpham scan (generator) ───────────────────────────────────────

```js
scanResult = {
  const pn = phageName?.trim().replace(/_Draft$/i, "");
  const samePhage = (id) => id?.replace(/_Draft$/i, "").toLowerCase() === pn?.toLowerCase();

  const controller = new AbortController();
  invalidation.then(() => controller.abort());
  const signal = controller.signal;

  // Polite mode: slower requests and smaller batches to reduce API load.
  const REQUEST_DELAY_MS = 50;
  const FETCH_BATCH_SIZE = 4;
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  const runBatched = async (items, fn, batchSize = FETCH_BATCH_SIZE) => {
    for (let i = 0; i < items.length; i += batchSize)
      await Promise.all(items.slice(i, i + batchSize).map(fn));
  };

  const politeGet = async (endpoint) => {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    const response = await getPhameratorData(dataset, endpoint, formData.apiKey, signal);
    await sleep(REQUEST_DELAY_MS);
    return response;
  };

  if (!pn || !refPhageResult?.data) {
    yield { status: "idle", orphams: [] };
    return;
  }

  yield { status: "loading", phase: "Preparing…", done: 0, total: 0, orphams: [] };

  const refPhage = refPhageResult.data;
  const genes = [...refPhage.genes].sort((a, b) => (a.stop || 0) - (b.stop || 0));
  const refPhageCluster = refPhage.clusterSubcluster || refPhage.cluster || null;

  const fetchGenome = async (name) => {
    const data = await politeGet(`/genome/${encodeURIComponent(name)}/`);
    if (data) return { data, isDraft: false };
    const draftData = await politeGet(`/genome/${encodeURIComponent(name)}_Draft/`);
    return { data: draftData, isDraft: !!draftData };
  };

  const fetchPhamPolite = async (phamName) => {
    const result = await politeGet(`/phamily/${phamName}`);
    if (!result || result.length === 0)
      throw new Error(`Phamerator returned no data for pham ${phamName}.`);
    return result;
  };

  try {
    // ── Phase 1: fetch all unique phams in the phage ──────────────────────
    const phamCache = new Map(); // phamName → genes[]
    const uniquePhams = [...new Set(genes.map(g => g.phamName).filter(Boolean))];

    yield { status: "loading", phase: `Fetching ${uniquePhams.length} phams…`, done: 0, total: uniquePhams.length, orphams: [] };

    const warnings = [];
    await runBatched(uniquePhams, async (phamName) => {
      try { phamCache.set(phamName, await fetchPhamPolite(phamName)); }
      catch (err) { phamCache.set(phamName, []); warnings.push(`Pham ${phamName}: ${err.message}`); }
    });

    // ── Identify orphams; collect any neighbor phams not already in cache ─
    const orphamGenes = [];
    const extraPhamNames = new Set();

    for (let geneIdx = 0; geneIdx < genes.length; geneIdx++) {
      const gene = genes[geneIdx];
      const members = (phamCache.get(gene.phamName) || []).filter(g => !samePhage(g.phageID));
      if (members.length > 0) continue; // has other pham members → not an orpham

      const refDir = gene.direction || "forward";
      const upIdx  = refDir === "reverse" ? geneIdx + 1 : geneIdx - 1;
      const dnIdx  = refDir === "reverse" ? geneIdx - 1 : geneIdx + 1;
      const refUpPham = (upIdx >= 0 && upIdx < genes.length) ? genes[upIdx].phamName : null;
      const refDnPham = (dnIdx >= 0 && dnIdx < genes.length) ? genes[dnIdx].phamName : null;
      const refUpFunc = (upIdx >= 0 && upIdx < genes.length) ? (genes[upIdx].genefunction || "") : "";
      const refDnFunc = (dnIdx >= 0 && dnIdx < genes.length) ? (genes[dnIdx].genefunction || "") : "";

      orphamGenes.push({ gene, refUpPham, refDnPham, refUpFunc, refDnFunc });
      if (refUpPham && !phamCache.has(refUpPham)) extraPhamNames.add(refUpPham);
      if (refDnPham && !phamCache.has(refDnPham)) extraPhamNames.add(refDnPham);
    }

    // ── Phase 2: fetch any neighbor phams not already cached ─────────────
    const extraPhams = [...extraPhamNames];
    if (extraPhams.length > 0) {
      yield { status: "loading", phase: `Fetching ${extraPhams.length} neighbor phams…`, done: 0, total: extraPhams.length, orphams: [] };
      await runBatched(extraPhams, async (phamName) => {
        try { phamCache.set(phamName, await fetchPhamPolite(phamName)); }
        catch (err) { phamCache.set(phamName, []); warnings.push(`Pham ${phamName}: ${err.message}`); }
      });
    }

    // ── Collect all candidate phage IDs across all orphams (deduped) ──────
    const candidatePhageIds = new Set();
    for (const { refUpPham, refDnPham } of orphamGenes) {
      for (const p of [refUpPham, refDnPham]) {
        if (!p) continue;
        for (const g of (phamCache.get(p) || []))
          if (!samePhage(g.phageID)) candidatePhageIds.add(g.phageID);
      }
    }

    // ── Phase 3: fetch all candidate phage genomes (shared across orphams) ─
    const phageCache = new Map(); // phageId → { cluster, parentCluster, genes, isDraft }
    const candidateList = [...candidatePhageIds];

    let genomeDone = 0;
    yield { status: "loading", phase: `Fetching ${candidateList.length} candidate phage genomes…`, done: 0, total: candidateList.length, orphams: [] };

    await runBatched(candidateList, async (phageId) => {
      try {
        const { data, isDraft } = await fetchGenome(phageId);
        if (data && (!data.genes || data.genes.length === 0))
          warnings.push(`Phage ${phageId}: genome returned no gene data.`);
        phageCache.set(phageId, data
          ? { cluster: data.clusterSubcluster || data.cluster || "—", parentCluster: data.cluster || null, genes: data.genes || [], isDraft }
          : { cluster: "—", parentCluster: null, genes: [], isDraft: false });
        if (!data) warnings.push(`Phage ${phageId}: not found (tried _Draft fallback).`);
      } catch (err) {
        phageCache.set(phageId, { cluster: "—", parentCluster: null, genes: [], isDraft: false });
        warnings.push(`Phage ${phageId}: ${err.message}`);
      }
      genomeDone++;
    });

    // ── Phase 4: compute synteny for each orpham (pure computation) ───────
    const completedOrphams = [];
    yield { status: "loading", phase: `Computing synteny for ${orphamGenes.length} orphams…`, done: 0, total: orphamGenes.length, orphams: [] };

    for (const { gene, refUpPham, refDnPham, refUpFunc, refDnFunc } of orphamGenes) {
      const rows = [];

      if (refUpPham || refDnPham) {
        // Candidate phage IDs relevant to this particular orpham
        const myPhageIds = new Set();
        for (const p of [refUpPham, refDnPham]) {
          if (!p) continue;
          for (const g of (phamCache.get(p) || []))
            if (!samePhage(g.phageID)) myPhageIds.add(g.phageID);
        }

        for (const phageId of myPhageIds) {
          const meta   = phageCache.get(phageId);
          if (!meta?.genes?.length) continue;
          const cGenes = meta.genes;
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
        rows.sort((a, b) => a.sortKey.localeCompare(b.sortKey) || a.phage.localeCompare(b.phage));
      }

      completedOrphams.push({
        geneNumber:   gene.name,
        phamName:     gene.phamName,
        direction:    gene.direction || "forward",
        genefunction: gene.genefunction || "",
        geneLength:   Math.abs(gene.stop - gene.start) + 1,
        start: gene.start, stop: gene.stop,
        refUpPham, refDnPham, refUpFunc, refDnFunc,
        rows
      });

      yield {
        status:  "loading",
        phase:   `Computing synteny (${completedOrphams.length}/${orphamGenes.length})…`,
        done:    completedOrphams.length,
        total:   orphamGenes.length,
        orphams: [...completedOrphams]
      };
    }

    yield {
      status: "ok",
      phageName: pn,
      refPhageCluster,
      totalGenes: genes.length,
      warnings,
      orphams: completedOrphams
    };

  } catch (err) {
    if (err.name === "AbortError") return;
    yield { status: "error", message: err.message, orphams: [] };
  }
}
```

## ── CELL 12: results heading ─────────────────────────────────────────────────

```md
## Results
```

## ── CELL 13: summary bar ─────────────────────────────────────────────────────

```js
html`${(() => {
  const { status, phase, done, total, orphams, phageName, totalGenes } = scanResult;

  if (status === "idle")
    return `<p style="color:#888">Enter a phage name above to begin.</p>`;

  if (status === "error")
    return `<div style="padding:10px;background:#fee2e2;border-radius:6px;color:#b91c1c">⚠️ ${scanResult.message}</div>`;

  const withTwo = orphams.filter(o => o.rows.some(r => r.twoSided)).length;
  const withAny = orphams.filter(o => o.rows.length > 0).length;

  if (status === "loading") {
    const pct = total > 0 ? Math.round(100 * done / total) : 0;
    return `
    <div style="padding:10px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:0.88em">
      <div style="color:#475569;margin-bottom:6px">${phase}</div>
      <div style="background:#e2e8f0;border-radius:9999px;height:6px;overflow:hidden">
        <div style="background:#2563eb;height:100%;width:${pct}%;transition:width 0.3s"></div>
      </div>
      ${orphams.length > 0 ? `<div style="margin-top:6px;color:#64748b">${orphams.length} orpham${orphams.length !== 1 ? "s" : ""} processed — ${withTwo} with two-flank support</div>` : ""}
    </div>`;
  }

  // status === "ok"
  const { warnings } = scanResult;
  const phageUrl = `https://phagesdb.org/phages/${encodeURIComponent(phageName.replace(/_Draft$/i, ""))}/`;
  const warningBanner = warnings?.length > 0 ? `
    <div style="margin-top:10px;padding:8px 12px;background:#fef9c3;border-radius:6px;border:1px solid #fde047;font-size:0.82em;color:#854d0e">
      ⚠ ${warnings.length} API fetch issue${warnings.length !== 1 ? "s" : ""} — some results may be incomplete.
      <details style="margin-top:4px"><summary style="cursor:pointer">Show details</summary>
        <ul style="margin:4px 0 0 16px;padding:0">${warnings.map(w => `<li>${w}</li>`).join("")}</ul>
      </details>
    </div>` : "";
  return `
  <div style="margin-bottom:6px;font-size:0.88em;color:#475569">
    Phage: <a href="${phageUrl}" target="_blank" style="color:#2563eb;font-weight:600">${phageName}</a>
    &nbsp;·&nbsp; ${totalGenes} total genes
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap">
    <div style="padding:8px 16px;background:#fff7ed;border-radius:8px;border:1px solid #fed7aa">
      🔬 <b>${orphams.length}</b> orpham${orphams.length !== 1 ? "s" : ""}
    </div>
    <div style="padding:8px 16px;background:#faf5ff;border-radius:8px;border:1px solid #e9d5ff">
      🔗 <b>${withTwo}</b> with two-flank support
    </div>
    <div style="padding:8px 16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0">
      🔀 <b>${withAny - withTwo}</b> one-flank only
    </div>
    <div style="padding:8px 16px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0">
      ⬜ <b>${orphams.length - withAny}</b> no hits
    </div>
  </div>
  ${warningBanner}`;
})()}`
```

## ── CELL 14: per-orpham results ─────────────────────────────────────────────

```js
{
  const { status, orphams } = scanResult;
  if (status === "idle" || (status === "loading" && orphams.length === 0)) return html``;

  const phamUrl  = (p) => `https://phagesdb.org/phams/${encodeURIComponent(p)}/`;
  const phageUrl = (p) => `https://phagesdb.org/phages/${encodeURIComponent(p.replace(/_Draft$/i, ""))}/`;

  // One scoped style block for all tables in this cell
  const uid = `orp-${Date.now().toString(36)}`;
  const styleEl = document.createElement('style');
  styleEl.textContent = `
    #${uid} .syn-tbl { border-collapse:collapse; width:100%; font-size:0.85em; }
    #${uid} .syn-tbl th { padding:6px 10px; background:#1e293b; color:#f8fafc;
                     text-align:left; position:sticky; top:0; z-index:1; }
    #${uid} .syn-tbl td { padding:5px 10px; border-bottom:1px solid #e2e8f0; }
    #${uid} .syn-tbl tr:hover td { background:#f1f5f9 !important; }
    #${uid} .syn-tbl .grp-hdr td { background:#f1f5f9; font-weight:700; cursor:pointer;
                               color:#334155; padding:3px 10px; border-top:2px solid #cbd5e1;
                               font-size:0.82em; user-select:none; }
    #${uid} .syn-tbl .grp-hdr:hover td { background:#e2e8f0 !important; }
    #${uid} .syn-tbl td a { color:#2563eb; text-decoration:none; }
    #${uid} .syn-tbl td a:hover { text-decoration:underline; }
    #${uid} .gene-fn { color:#64748b; font-size:0.78em; display:block; margin-top:1px; }
    #${uid} .orpham-card { margin-bottom:14px; border:1px solid #e2e8f0; border-radius:8px; overflow:hidden; font-size:0.88em; }
    #${uid} .card-header { padding:10px 14px; background:#f8fafc; display:flex;
                      justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:6px; }
    #${uid} .card-body   { padding:12px 14px; border-top:1px solid #e2e8f0; }
    #${uid} .card-nohits { padding:8px 14px; color:#94a3b8; font-style:italic;
                      border-top:1px solid #e2e8f0; font-size:0.85em; }
    #${uid} .tbtn { padding:3px 10px; border-radius:6px; border:1px solid #cbd5e1;
               background:#f8fafc; cursor:pointer; font-size:0.8em; font-weight:600; color:#334155; }
  `;
  document.head.appendChild(styleEl);
  invalidation.then(() => styleEl.remove());

  const dirTag = dir => dir === "reverse"
    ? `<span style="color:#dc2626;font-weight:700" title="Reverse strand">←</span>`
    : `<span style="color:#2563eb;font-weight:700" title="Forward strand">→</span>`;

  const wrap = document.createElement('div');
  wrap.id = uid;

  orphams.forEach((o, oi) => {
    const { geneNumber, phamName, direction, genefunction,
            start, stop, refUpPham, refDnPham, refUpFunc, refDnFunc, rows } = o;
    const nTwo = rows.filter(r => r.twoSided).length;
    const nOne = rows.length - nTwo;

    const card = document.createElement('div');
    card.className = 'orpham-card';

    // ── Card header ──────────────────────────────────────────────────────
    const hdr = document.createElement('div');
    hdr.className = 'card-header';
    hdr.innerHTML = `
      <div>
        <span style="font-weight:700;color:#1e293b">Gene ${geneNumber}</span>
        <span style="color:#64748b;margin-left:8px">${Number(start).toLocaleString()}–${Number(stop).toLocaleString()} bp</span>
        <span style="margin-left:6px">${dirTag(direction)}</span>
        ${genefunction ? `<span style="color:#475569;margin-left:8px">${genefunction}</span>` : ''}
        ${phamName ? `<span style="margin-left:8px;font-size:0.82em;color:#94a3b8">pham <a href="${phamUrl(phamName)}" target="_blank" style="color:#64748b">${phamName}</a></span>` : ''}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <span style="padding:3px 9px;background:#f0fdf4;border-radius:6px;border:1px solid #bbf7d0;color:#15803d;font-size:0.82em">
          ↑ ${refUpPham ? `<a href="${phamUrl(refUpPham)}" target="_blank" style="color:#15803d">${refUpPham}</a>` : "—"}
        </span>
        <span style="padding:3px 9px;background:#f0fdf4;border-radius:6px;border:1px solid #bbf7d0;color:#15803d;font-size:0.82em">
          ↓ ${refDnPham ? `<a href="${phamUrl(refDnPham)}" target="_blank" style="color:#15803d">${refDnPham}</a>` : "—"}
        </span>
        ${nTwo > 0 ? `<span style="padding:3px 9px;background:#ede9fe;border-radius:6px;color:#5b21b6;font-size:0.82em">🔗 ${nTwo} two-flank</span>` : ""}
        ${nOne > 0 ? `<span style="padding:3px 9px;background:#f0fdf4;border-radius:6px;color:#166534;font-size:0.82em">🔀 ${nOne} one-flank</span>` : ""}
      </div>`;
    card.appendChild(hdr);

    if (rows.length === 0) {
      const nohits = document.createElement('div');
      nohits.className = 'card-nohits';
      nohits.textContent = !refUpPham && !refDnPham
        ? "No known pham neighbors — cannot search for synteny."
        : "No syntenic hits found.";
      card.appendChild(nohits);
      wrap.appendChild(card);
      return;
    }

    const body = document.createElement('div');
    body.className = 'card-body';

    // ── Function tally for the central candidate gene (two-flank supported) ─
    // A function qualifies if it appears in >=1 upstream-supported hit AND
    // >=1 downstream-supported hit (two-sided hits count for both).
    const upFns = new Set(rows.filter(r => r.upMatch).map(r => r.genefunction?.trim() || "Hypothetical protein"));
    const dnFns = new Set(rows.filter(r => r.dnMatch).map(r => r.genefunction?.trim() || "Hypothetical protein"));
    const bothFns = new Set([...upFns].filter(fn => dnFns.has(fn)));

    const tally = new Map();
    for (const r of rows) {
      const fn = r.genefunction?.trim() || "Hypothetical protein";
      if (!bothFns.has(fn)) continue;
      tally.set(fn, (tally.get(fn) || 0) + 1);
    }
    const tallyTotal = [...tally.values()].reduce((a, b) => a + b, 0);
    const sortedTally = [...tally.entries()].sort(([, a], [, b]) => b - a);
    const uninformative = new Set(["nkf", "hypothetical protein", "no known function"]);

    if (sortedTally.length > 0) {
      const fnRows = sortedTally.map(([fn, n]) => {
        const v = n / tallyTotal;
        const informative = !uninformative.has(fn.toLowerCase());
        const bg = (informative && v > 0.50) ? '#bbf7d0' : (informative && v > 0.25) ? '#dcfce7' : (informative && v > 0.10) ? '#f0fdf4' : '';
        const bold = informative && v > 0.25;
        return `<tr style="${bg ? `background:${bg}` : ''}">
          <td style="padding:4px 10px;${bold ? 'font-weight:600' : ''}">${fn}</td>
          <td style="padding:4px 10px;text-align:right;font-weight:600">${n} <span style="color:#94a3b8">(${Math.round(100*v)}%)</span></td>
        </tr>`;
      }).join("");
      const tallyDiv = document.createElement('div');
      tallyDiv.style.cssText = "margin-bottom:10px";
      tallyDiv.innerHTML = `
        <div style="font-size:0.82em;color:#64748b;margin-bottom:4px">Central-gene functions with support from both flanks (n=${tallyTotal} hits)</div>
        <table class="syn-tbl">
          <thead>
            <tr style="border-bottom:2px solid #cbd5e1;color:#64748b">
              <th>Function</th>
              <th style="text-align:right">Hits</th>
            </tr>
          </thead>
          <tbody style="color:#334155">${fnRows}</tbody>
        </table>`;
      body.appendChild(tallyDiv);
    }

    // ── One-flank-supported central-gene functions (three-column view) ─────
    const upOnly = rows.filter(r => r.upMatch && !r.twoSided);
    const dnOnly = rows.filter(r => r.dnMatch && !r.twoSided);
    if (upOnly.length > 0 || dnOnly.length > 0) {
      const upN = upOnly.length, dnN = dnOnly.length;
      // Collect central-gene functions by support type, with per-side counts
      const oneFns = new Map(); // fn → { up: n, dn: n }
      for (const r of upOnly) {
        const fn = r.genefunction?.trim() || "Hypothetical protein";
        if (!oneFns.has(fn)) oneFns.set(fn, { up: 0, dn: 0 });
        oneFns.get(fn).up++;
      }
      for (const r of dnOnly) {
        const fn = r.genefunction?.trim() || "Hypothetical protein";
        if (!oneFns.has(fn)) oneFns.set(fn, { up: 0, dn: 0 });
        oneFns.get(fn).dn++;
      }
      // Sort: functions seen in both one-flank subsets first, then by total
      const sortedOne = [...oneFns.entries()].sort(([, a], [, b]) => {
        const aShared = a.up > 0 && a.dn > 0 ? 1 : 0;
        const bShared = b.up > 0 && b.dn > 0 ? 1 : 0;
        return bShared - aShared || (b.up + b.dn) - (a.up + a.dn);
      });
      const pctCell = (n, total) => n > 0
        ? `${n} <span style="color:#94a3b8">(${Math.round(100*n/total)}%)</span>`
        : `<span style="color:#cbd5e1">—</span>`;
      const fnRows = sortedOne.map(([fn, t]) => {
        const shared = t.up > 0 && t.dn > 0;
        const informative = !uninformative.has(fn.toLowerCase());
        const bg = (shared && informative) ? '#f0fdf4' : '';
        return `<tr style="${bg ? `background:${bg}` : ''}">
          <td style="padding:4px 10px;${shared && informative ? 'font-weight:600' : ''}">${shared ? '✓ ' : ''}${fn}</td>
          <td style="padding:4px 10px;text-align:right">${upN > 0 ? pctCell(t.up, upN) : '<span style="color:#cbd5e1">n/a</span>'}</td>
          <td style="padding:4px 10px;text-align:right">${dnN > 0 ? pctCell(t.dn, dnN) : '<span style="color:#cbd5e1">n/a</span>'}</td>
        </tr>`;
      }).join("");
      const oneSidedToggle = document.createElement('button');
      oneSidedToggle.className = 'tbtn';
      oneSidedToggle.style.cssText += ";margin-bottom:8px";
      oneSidedToggle.textContent = `▸ Show one-flank-supported functions (${upN + dnN} hit${upN + dnN !== 1 ? "s" : ""})`;

      const oneSidedWrap = document.createElement('div');
      oneSidedWrap.style.cssText = "display:none;margin-bottom:10px";
      oneSidedWrap.innerHTML = `
        <div style="font-size:0.82em;color:#64748b;margin-bottom:4px">Central-gene functions from one-flank hits <span style="color:#94a3b8">(✓ = seen in both one-flank subsets: upstream-supported and downstream-supported)</span></div>
        <table class="syn-tbl">
          <thead>
            <tr style="border-bottom:2px solid #cbd5e1;color:#64748b">
              <th>Function</th>
              <th style="text-align:right">↑ Upstream flank matched only (n=${upN})</th>
              <th style="text-align:right">↓ Downstream flank matched only (n=${dnN})</th>
            </tr>
          </thead>
          <tbody style="color:#334155">${fnRows}</tbody>
        </table>`;

      oneSidedToggle.addEventListener('click', () => {
        const open = oneSidedWrap.style.display === 'none';
        oneSidedWrap.style.display = open ? '' : 'none';
        oneSidedToggle.textContent = open
          ? `▾ Hide one-flank-supported functions (${upN + dnN} hit${upN + dnN !== 1 ? "s" : ""})`
          : `▸ Show one-flank-supported functions (${upN + dnN} hit${upN + dnN !== 1 ? "s" : ""})`;
      });

      // one-sided section appended after two-sided table (below)
      body._oneSidedToggle = oneSidedToggle;
      body._oneSidedWrap   = oneSidedWrap;
    }

    // ── Two-sided synteny table (expanded by default) ─────────────────────
    const twoRows = rows.filter(r => r.twoSided);
    if (twoRows.length === 0) {
      // No two-sided hits — still append one-sided section if present
      if (body._oneSidedToggle) { body.appendChild(body._oneSidedToggle); body.appendChild(body._oneSidedWrap); }
      card.appendChild(body); wrap.appendChild(card); return;
    }

    const groups = new Map();
    for (const r of twoRows) {
      const key = r.cluster || "Unknown";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(r);
    }

    let tblHtml = `
      <table class="syn-tbl">
        <thead><tr>
          <th>Phage</th><th>Gene #</th><th>Gene pham</th><th>Cluster</th>
          <th style="text-align:center">Dir.</th>
          <th>Upstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refUpPham ?? "—"}</small></th>
          <th>Downstream pham<br><small style="font-weight:400;opacity:.7">ref: ${refDnPham ?? "—"}</small></th>
        </tr></thead><tbody>`;
    let gi = 0;
    for (const [groupKey, groupRows] of groups) {
      const gid = `o${oi}g${gi++}`;
      tblHtml += `<tr class="grp-hdr" data-gid="${gid}">
        <td colspan="7"><span class="chev">▾</span> ${groupKey} (${groupRows.length} gene${groupRows.length > 1 ? "s" : ""})</td></tr>`;
      for (const r of groupRows) {
        const phamCell = r.candidatePham
          ? `<td style="text-align:center"><a href="${phamUrl(r.candidatePham)}" target="_blank">${r.candidatePham}</a></td>`
          : `<td style="text-align:center;color:#94a3b8;font-style:italic">orpham</td>`;
        tblHtml += `
        <tr data-group="${gid}">
          <td>
            <a href="${phageUrl(r.phage)}" target="_blank">${r.phage}</a>${r.isDraft ? ' <span title="Draft genome">🚧</span>' : ""}
            ${r.genefunction ? `<span class="gene-fn">${r.genefunction}</span>` : ""}
          </td>
          <td style="text-align:center">${r.geneNumber}</td>
          ${phamCell}
          <td>${r.cluster || "—"}</td>
          <td style="text-align:center">${dirTag(r.direction)}</td>
          <td style="background:#dcfce7;color:#166534;font-weight:600;text-align:center">${r.upPham ?? "—"}</td>
          <td style="background:#dcfce7;color:#166534;font-weight:600;text-align:center">${r.dnPham ?? "—"}</td>
        </tr>`;
      }
    }
    tblHtml += `</tbody></table>`;

    const tblWrap = document.createElement('div');
    tblWrap.style.cssText = "overflow-x:auto;max-height:50vh;overflow-y:auto;margin-bottom:10px";
    tblWrap.innerHTML = tblHtml;

    tblWrap.querySelectorAll('tr.grp-hdr').forEach(hdr => {
      hdr.addEventListener('click', function() {
        const gid = this.dataset.gid;
        const rs = [...tblWrap.querySelectorAll(`tr[data-group="${gid}"]`)];
        const collapsed = rs[0]?.style.display === 'none';
        rs.forEach(r => r.style.display = collapsed ? '' : 'none');
        this.querySelector('.chev').textContent = collapsed ? '▾' : '▸';
      });
    });

    body.appendChild(tblWrap);

    // Append one-sided section after two-sided table
    if (body._oneSidedToggle) { body.appendChild(body._oneSidedToggle); body.appendChild(body._oneSidedWrap); }

    card.appendChild(body);
    wrap.appendChild(card);
  });

  return wrap;
}
```
