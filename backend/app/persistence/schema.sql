PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL,
    phase TEXT,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER,
    message TEXT,
    error_code TEXT,
    error_message TEXT,
    counters_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS objects (
    id TEXT PRIMARY KEY,
    database_key TEXT NOT NULL,
    container_key TEXT NOT NULL,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    subobject_name TEXT,
    object_type TEXT NOT NULL,
    oracle_object_type TEXT NOT NULL,
    status TEXT,
    oracle_object_id INTEGER,
    created_at TEXT,
    last_ddl_at TEXT,
    is_external INTEGER NOT NULL DEFAULT 0 CHECK (is_external IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES objects(id),
    target_id TEXT NOT NULL REFERENCES objects(id),
    relationship_type TEXT NOT NULL,
    directed INTEGER NOT NULL DEFAULT 1 CHECK (directed IN (0, 1)),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    origin TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS relationship_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_id TEXT NOT NULL REFERENCES relationships(id) ON DELETE CASCADE,
    source_view TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS object_details (
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    detail_type TEXT NOT NULL,
    details_json TEXT NOT NULL,
    PRIMARY KEY (object_id, detail_type)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    config_json TEXT NOT NULL,
    result_summary_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_membership (
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    community_id INTEGER NOT NULL,
    stability REAL,
    PRIMARY KEY (analysis_id, object_id)
);

CREATE TABLE IF NOT EXISTS community_metrics (
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    community_id INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, community_id)
);

CREATE TABLE IF NOT EXISTS community_edges (
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    source_community INTEGER NOT NULL,
    target_community INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    total_weight REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (analysis_id, source_community, target_community)
);

CREATE TABLE IF NOT EXISTS centrality_results (
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (analysis_id, object_id, metric)
);

CREATE TABLE IF NOT EXISTS annotations (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    community_id INTEGER NOT NULL,
    name TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_jobs (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    format TEXT NOT NULL,
    status TEXT NOT NULL,
    filename TEXT,
    content_type TEXT,
    file_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_objects_owner_type_name
    ON objects(owner, object_type, name);
CREATE INDEX IF NOT EXISTS idx_objects_name ON objects(name);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type);
CREATE INDEX IF NOT EXISTS idx_membership_community
    ON analysis_membership(analysis_id, community_id);
CREATE INDEX IF NOT EXISTS idx_membership_object
    ON analysis_membership(analysis_id, object_id);
CREATE INDEX IF NOT EXISTS idx_community_edges
    ON community_edges(analysis_id, source_community, target_community);
CREATE UNIQUE INDEX IF NOT EXISTS idx_annotations_community
    ON annotations(analysis_id, community_id);
CREATE INDEX IF NOT EXISTS idx_export_jobs_analysis
    ON export_jobs(analysis_id, created_at);
