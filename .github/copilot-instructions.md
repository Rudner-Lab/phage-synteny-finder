# Copilot / AI agent instructions — Phage Synteny Notebook

This repository is a single Observable notebook used as an interactive phage
synteny helper. Agents should treat edits conservatively: the notebook is the
primary artifact and is intended to be run on observablehq.com.

Quick facts
- Primary file: `phage_synteny_notebook.ojs` (Observable notebook source).
- No build/test toolchain present; verification is manual by running the
  notebook in Observable (copy cells or import as appropriate).

Big picture / data flow
- Inputs: `inputs` form (phageName, geneNumber) → button `runBtn` triggers
  `result` evaluation.
- `phagesdbGet(path)` is the single HTTP helper (CORS proxy via `PROXY`).
- Flow: fetch reference phage → fetch genes for that phage → find ref pham →
  fetch pham members → fetch per-phage gene lists (cached) → evaluate
  synteny → render summary + grouped table.

Critical patterns & conventions
- Preserve Observable cell boundaries and the cell header comments like
  `// ── CELL X:`. Splitting/merging cells can change execution order/UI.
- Use the existing `phagesdbGet` helper for all PhagesDB calls (it centralizes
  the `PROXY` handling and `format=json` suffix).
- The code avoids per-gene requests by grouping members per-phage and caching
  gene lists in `phageCache` (Map). When optimizing, maintain the same
  batching/caching approach to avoid thousands of requests.
- Default page sizes are explicit (`page_size=1000` or `2000`) — don't reduce
  without confirming effect on API responses.

Integration points / external dependencies
- PhagesDB HTTP API (phages and genes endpoints). All requests go through
  `phagesdbGet`. Note CORS is circumvented with `PROXY` currently set to
  `https://cors-anywhere.herokuapp.com/` — changing this has runtime impact.
- Observable platform: rendering HTML via `html` and `md` cells; behaviors are
  Observable-specific (e.g., `viewof`, reactive cell execution).

Editing & testing workflow (how to verify changes)
1. Edit `phage_synteny_notebook.ojs` in the repo. Keep cell markers intact.
2. Open observablehq.com, create a new notebook, and paste each cell in order
   (or import if you have an import flow). Run the notebook in-browser.
3. Test with known phage names (e.g., `L5`) and gene numbers to exercise
   caching and table rendering. Observe network requests in DevTools.

Examples of local edits
- To change caching behavior, update `getPhageGenes(name)` and keep the
  `phageCache` Map semantics so existing logic that assumes cached responses
  continues to work.
- To alter the proxy behavior, update `PROXY` only after confirming CORS on
  phagesdb.org; prefer feature-flagging or a single place change (`PROXY` var).

Commit & PR guidance
- Small, focused PRs are preferred. Describe the observable changes and how
  to test them (example phage/gene inputs). Include note if the change alters
  external request patterns (e.g., increased request count or proxy changes).

If something is unclear or you need broader refactors (e.g., extract logic to
a module or add automated tests), ask for permission — the notebook is the
primary UX and changes should preserve the live-demo behaviour.

---
If you'd like, I can (a) merge this into the repo now, (b) expand testing
instructions for running locally with node tooling, or (c) extract the logic
into a small JS module and add a README showing how to run quick checks.
