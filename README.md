# Phage Synteny Tools

A collection of tools for synteny-based phage genome annotation, built around the [Phamerator](https://phamerator.org) database.

## Tools

### Orpham synteny report (Python)

A command-line tool that identifies **orpham genes** in a set of phage genomes and generates a self-contained HTML report summarising their syntenic context.

An **orpham** is a gene whose protein family (pham) exists in only one phage — it has no homologs in the rest of the dataset. This tool asks: *even if the gene itself is unique, does the genomic neighbourhood around it point to a known function?* It does this by scanning other phages in the dataset for the same flanking pham context and tallying the functions of whatever gene sits in the corresponding position.

### Observable notebooks (`observable_notebooks/`)

Two interactive notebooks for use on [ObservableHQ](https://observablehq.com). Each notebook is stored as a Markdown file with cell-by-cell source; paste the cells into a new notebook to use them.

- **`phage_synteny_notebook.md`** — *Phage Genome Annotation – Synteny Helper*: enter a phage name and select a gene to see a synteny table, gene-length statistics, and an auto-generated annotation statement based on neighbour functions.
- **`orpham_synteny_notebook.md`** — *Orpham Synteny Scanner*: enter a phage name to scan all its orphams and view per-orpham hit counts, function tallies, and synteny tables grouped by cluster.

Both notebooks query the Phamerator API directly and require a Phamerator login.

## Orpham report — setup and usage

### Requirements

- Python 3.10+
- A `phamerator.sqlite` database (scraped from [PhagesDB](https://phagesdb.org) via `scrape_phamerator.py`)

Install dependencies into a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Usage

Run the entry-point script, specifying either a cluster/subcluster pattern or a single phage:

```bash
# All phages in subcluster F1
.venv/bin/python report_orpham_synteny.py --cluster F1

# All phages in cluster F (any subcluster or none)
.venv/bin/python report_orpham_synteny.py --cluster "F*"

# Only unsubclustered phages in cluster F
.venv/bin/python report_orpham_synteny.py --cluster F

# Multiple patterns
.venv/bin/python report_orpham_synteny.py --cluster F1 F2 K1

# Entire dataset
.venv/bin/python report_orpham_synteny.py --cluster all

# Single phage
.venv/bin/python report_orpham_synteny.py --phage LordVader
```

Output is a self-contained HTML file. By default the filename is derived from the pattern (e.g. `F1_orpham_report.html`). Use `--out` to override:

```bash
.venv/bin/python report_orpham_synteny.py --cluster F1 --out report.html
```

Other options:

| Flag | Default | Description |
|---|---|---|
| `--dataset` | `Actino_Draft` | Dataset name in the database |
| `--db` | `phamerator.sqlite` | Path to the SQLite database |
| `--out` | `<pattern>_orpham_report.html` | Output HTML file |

### Cluster pattern syntax

| Pattern | Matches |
|---|---|
| `F1` | Phages in subcluster F1 only |
| `F` | Phages in cluster F with no subcluster assigned |
| `F*` | All phages in cluster F (any subcluster or none) |
| `all` | Every phage in the dataset |

Multiple patterns are OR'd together and deduplicated.

### How it works

For each phage in the requested set, the pipeline:

1. Loads the phage's genes sorted by position.
2. Identifies orpham genes — phams present in only one phage.
3. Records the upstream and downstream flanking pham for each orpham.
4. Finds all other phages in the dataset that carry either flanking pham (candidate phages).
5. Scans each candidate for a gene sitting between those same two flanking phams.
6. Tallies the functions annotated on those candidate genes, split by whether both flanks matched (two-sided hit) or only one (one-sided hit).
7. Filters to orphams that have at least one **informative** function — not "hypothetical protein" or NKF — appearing on both flanks.

Results are rendered into a single HTML file with collapsible sections per phage and gene, a summary table, a TOC, and links to PhagesDB.

## Project layout

```
orpham_report/
  cli.py        command-line interface (argparse, entry-point logic)
  db.py         database helpers (open_db, resolve_*, normalize_phage_id)
  analysis.py   full pipeline (compute_phage_results, compute_cluster_results)
  render.py     HTML report generation (pure Python, no template engine)

tests/
  conftest.py   shared fixtures (in-memory SQLite with synthetic test data)
  test_analysis.py
  test_db.py
  test_render.py
  test_smoke.py  integration tests against the real phamerator.sqlite (skipped if absent)

observable_notebooks/
  phage_synteny_notebook.md   Phage Genome Annotation – Synteny Helper
  orpham_synteny_notebook.md  Orpham Synteny Scanner

scrape_phamerator.py   scrapes PhagesDB and populates phamerator.sqlite
report_orpham_synteny.py   entry-point shim
schema.sql             database schema for reference
```

### Running the tests

```bash
.venv/bin/python -m pytest tests/ -q
```

A pre-commit hook runs the tests automatically. To skip it for a WIP commit:

```bash
SKIP_TESTS=true git commit -m "..."
```

The smoke tests (`test_smoke.py`) require `phamerator.sqlite` to be present and are automatically skipped otherwise.

## Database

The database is populated by `scrape_phamerator.py`, which fetches phage and gene data from PhagesDB. See `schema.sql` for the full table definitions. The two main tables are:

- **`phages`** — one row per phage per dataset; includes cluster, subcluster, genome length, and draft status.
- **`genes`** — one row per gene; includes position, strand, pham assignment, and function annotation.
