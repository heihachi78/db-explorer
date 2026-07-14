import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.tasks.models import TaskSnapshot

from .database import database


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ScanStatusRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, snapshot: TaskSnapshot) -> None:
        values = asdict(snapshot)
        with database(self.path) as connection:
            connection.execute(
                """
                INSERT INTO scan_status (
                    id, state, phase, progress_current, progress_total, message,
                    error_code, error_message, counters_json, started_at,
                    finished_at, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state=excluded.state, phase=excluded.phase,
                    progress_current=excluded.progress_current,
                    progress_total=excluded.progress_total, message=excluded.message,
                    error_code=excluded.error_code, error_message=excluded.error_message,
                    counters_json=excluded.counters_json,
                    started_at=excluded.started_at, finished_at=excluded.finished_at,
                    updated_at=excluded.updated_at
                """,
                (
                    values["state"], values["phase"], values["progress_current"],
                    values["progress_total"], values["message"], values["error_code"],
                    values["error_message"], json.dumps(values["counters"]),
                    values["started_at"], values["finished_at"], utc_now(),
                ),
            )
            connection.commit()


class ObjectRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def count(self) -> int:
        with database(self.path, read_only=True) as connection:
            row = connection.execute("SELECT COUNT(*) FROM objects").fetchone()
        return int(row[0])

    def insert_many(self, rows: list[dict[str, Any]]) -> None:
        columns = (
            "id", "database_key", "container_key", "owner", "name",
            "subobject_name", "object_type", "oracle_object_type", "status",
            "oracle_object_id", "created_at", "last_ddl_at", "is_external",
            "metadata_json",
        )
        values = [tuple(row[column] for column in columns) for row in rows]
        with database(self.path) as connection:
            connection.executemany(
                f"INSERT INTO objects ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            connection.commit()
