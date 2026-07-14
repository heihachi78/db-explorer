import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if not read_only:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def database(path: Path, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    connection = connect(path, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()


def initialize_database(path: Path) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with database(path) as connection:
        connection.executescript(schema)
        connection.commit()


def integrity_check(path: Path) -> None:
    with database(path, read_only=True) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result[0] if result else 'no result'}")


def _checkpoint_for_publish(path: Path) -> None:
    """Move every WAL page into the database before renaming the file."""
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        connection.commit()
    finally:
        connection.close()

    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    finally:
        connection.close()


def publish_database(next_path: Path, current_path: Path) -> None:
    """Validate and atomically promote a fully closed staging database."""
    _checkpoint_for_publish(next_path)
    integrity_check(next_path)
    current_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(next_path, current_path)
