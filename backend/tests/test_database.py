import sqlite3
from pathlib import Path

import pytest

from app.persistence.database import initialize_database, integrity_check, publish_database


def test_schema_initializes_all_core_tables(tmp_path: Path) -> None:
    path = tmp_path / "graph.db"
    initialize_database(path)

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {
        "app_meta", "scan_status", "objects", "relationships",
        "relationship_evidence", "analysis_runs", "analysis_membership",
        "community_metrics", "community_edges", "centrality_results", "annotations",
        "export_jobs", "analysis_hierarchy", "analysis_hierarchy_membership",
    } <= tables
    integrity_check(path)


def test_publish_database_atomically_replaces_current_file(tmp_path: Path) -> None:
    current = tmp_path / "oracle_graph.db"
    staging = tmp_path / "oracle_graph.next.db"
    initialize_database(current)
    initialize_database(staging)
    connection = sqlite3.connect(staging)
    try:
        connection.execute(
            "INSERT INTO app_meta VALUES ('marker', '\"new\"', '2026-07-14T00:00:00Z')"
        )
        connection.commit()
    finally:
        connection.close()

    publish_database(staging, current)

    assert not staging.exists()
    connection = sqlite3.connect(current)
    try:
        assert connection.execute("SELECT value_json FROM app_meta WHERE key='marker'").fetchone()[0] == '"new"'
    finally:
        connection.close()


def test_invalid_staging_database_does_not_replace_current(tmp_path: Path) -> None:
    current = tmp_path / "oracle_graph.db"
    staging = tmp_path / "oracle_graph.next.db"
    initialize_database(current)
    staging.write_bytes(b"not a sqlite database")

    with pytest.raises(sqlite3.DatabaseError):
        publish_database(staging, current)

    integrity_check(current)
