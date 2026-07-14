import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.graph.normalization import json_value

from .database import connect, initialize_database


OBJECT_COLUMNS = (
    "id", "database_key", "container_key", "owner", "name",
    "subobject_name", "object_type", "oracle_object_type", "status",
    "oracle_object_id", "created_at", "last_ddl_at", "is_external",
    "metadata_json",
)


class ScanWriter:
    """Owns the staging SQLite connection for one complete scan."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> "ScanWriter":
        self.path.unlink(missing_ok=True)
        initialize_database(self.path)
        self.connection = connect(self.path)
        return self

    def __exit__(self, *_: object) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("ScanWriter is not open")
        return self.connection

    def insert_objects(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [tuple(row[column] for column in OBJECT_COLUMNS) for row in rows]
        if not values:
            return 0
        before = self.db.total_changes
        self.db.executemany(
            f"INSERT OR IGNORE INTO objects ({','.join(OBJECT_COLUMNS)}) "
            f"VALUES ({','.join('?' for _ in OBJECT_COLUMNS)})",
            values,
        )
        self.db.commit()
        return self.db.total_changes - before

    def insert_relationship(
        self,
        row: dict[str, Any],
        *,
        source_view: str,
        evidence: dict[str, Any],
    ) -> bool:
        before = self.db.total_changes
        self.db.execute(
            """
            INSERT OR IGNORE INTO relationships (
                id, source_id, target_id, relationship_type, directed,
                confidence, origin, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"], row["source_id"], row["target_id"],
                row["relationship_type"], row["directed"], row["confidence"],
                row["origin"], row["metadata_json"],
            ),
        )
        inserted = self.db.total_changes > before
        duplicate = self.db.execute(
            """
            SELECT 1 FROM relationship_evidence
            WHERE relationship_id = ? AND source_view = ? AND evidence_json = ?
            """,
            (row["id"], source_view, json_value(evidence)),
        ).fetchone()
        if duplicate is None:
            self.db.execute(
                """
                INSERT INTO relationship_evidence (
                    relationship_id, source_view, evidence_json
                ) VALUES (?, ?, ?)
                """,
                (row["id"], source_view, json_value(evidence)),
            )
        return inserted

    def set_meta(self, key: str, value: Any) -> None:
        self.db.execute(
            """
            INSERT INTO app_meta (key, value_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, json_value(value), datetime.now(UTC).isoformat()),
        )

    def commit(self) -> None:
        self.db.commit()

    def counts(self) -> tuple[int, int, int]:
        objects = int(self.db.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
        relationships = int(self.db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0])
        external = int(
            self.db.execute("SELECT COUNT(*) FROM objects WHERE is_external = 1").fetchone()[0]
        )
        return objects, relationships, external

    def validate(self) -> None:
        foreign_key_errors = self.db.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"SQLite foreign key check failed: {foreign_key_errors[:3]}")
        missing_endpoints = self.db.execute(
            """
            SELECT COUNT(*)
            FROM relationships r
            LEFT JOIN objects s ON s.id = r.source_id
            LEFT JOIN objects t ON t.id = r.target_id
            WHERE s.id IS NULL OR t.id IS NULL
            """
        ).fetchone()[0]
        if missing_endpoints:
            raise RuntimeError(f"Relationships with missing endpoints: {missing_endpoints}")

