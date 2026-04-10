-- phamerator.sqlite schema

CREATE TABLE phages (
    phage_id            TEXT    NOT NULL,
    dataset             TEXT    NOT NULL,
    phagename           TEXT,
    cluster             TEXT,
    subcluster          TEXT,
    cluster_subcluster  TEXT,           -- e.g. "F1"; derived from cluster + subcluster
    genome_length       INTEGER,
    scraped_at          TEXT,
    is_draft            INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (phage_id, dataset)
);

CREATE TABLE genes (
    gene_id         TEXT    NOT NULL,
    phage_id        TEXT    NOT NULL,
    dataset         TEXT    NOT NULL,
    name            TEXT,
    accession       TEXT,
    start           INTEGER,
    stop            INTEGER,
    midpoint        REAL,
    gap             INTEGER,
    direction       TEXT,
    pham_color      TEXT,
    pham_name       TEXT,
    translation     TEXT,
    gene_function   TEXT,
    locus_tag       TEXT,
    domain_count    INTEGER,
    tm_domain_count INTEGER,
    is_draft        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (gene_id, dataset)
);

CREATE INDEX idx_genes_phage ON genes (phage_id, dataset);
CREATE INDEX idx_genes_pham  ON genes (pham_name);

CREATE TABLE scrape_log (
    phage_id     TEXT    NOT NULL,
    dataset      TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending',  -- 'pending' | 'done' | 'error'
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT,
    error_msg    TEXT,
    is_draft     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (phage_id, dataset)
);
