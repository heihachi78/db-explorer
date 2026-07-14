import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest

from app.oracle.connection import OracleCredentials
from app.oracle.scanner import OracleScanner, ScanCancelled, ScanOptions
from app.persistence.database import initialize_database


class FakeCursor:
    def __init__(self) -> None:
        self.arraysize = 1
        self.prefetchrows = 1
        self.description = []
        self._rows: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query: str, _parameters=None) -> None:
        normalized = " ".join(query.lower().split())
        rows: list[dict] = []
        if "sys_context('userenv', 'db_name')" in normalized:
            rows = [{"database_name": "TESTDB", "container_name": "TESTPDB"}]
        elif normalized.startswith("select 1 from"):
            rows = []
        elif "select distinct owner from all_objects" in normalized:
            rows = [{"owner": "SALES"}]
        elif "from all_objects" in normalized:
            created = datetime(2026, 1, 1)
            rows = [
                {"owner": "SALES", "object_name": "ORDERS", "subobject_name": None,
                 "object_id": 1, "object_type": "TABLE", "status": "VALID",
                 "created": created, "last_ddl_time": created},
                {"owner": "SALES", "object_name": "ORDER_API", "subobject_name": None,
                 "object_id": 2, "object_type": "PACKAGE", "status": "VALID",
                 "created": created, "last_ddl_time": created},
                {"owner": "SALES", "object_name": "TRG_ORDERS", "subobject_name": None,
                 "object_id": 3, "object_type": "TRIGGER", "status": "VALID",
                 "created": created, "last_ddl_time": created},
                {"owner": "SALES", "object_name": "IX_ORDERS", "subobject_name": None,
                 "object_id": 4, "object_type": "INDEX", "status": "VALID",
                 "created": created, "last_ddl_time": created},
                {"owner": "SALES", "object_name": "ORDERS_ALIAS", "subobject_name": None,
                 "object_id": 5, "object_type": "SYNONYM", "status": "VALID",
                 "created": created, "last_ddl_time": created},
            ]
        elif "from all_dependencies" in normalized:
            rows = [{
                "owner": "SALES", "name": "ORDER_API", "type": "PACKAGE",
                "referenced_owner": "SALES", "referenced_name": "ORDERS",
                "referenced_type": "TABLE", "dependency_type": "HARD",
                "referenced_link_name": None,
            }]
        elif "from all_constraints c" in normalized:
            rows = [{
                "owner": "SALES", "table_name": "ORDERS", "constraint_name": "FK_CUSTOMER",
                "delete_rule": "NO ACTION", "status": "ENABLED", "source_column": "CUSTOMER_ID",
                "position": 1, "target_owner": "CRM", "target_table": "CUSTOMERS",
                "target_column": "ID",
            }]
        elif "from all_triggers" in normalized:
            rows = [{
                "owner": "SALES", "trigger_name": "TRG_ORDERS", "table_owner": "SALES",
                "table_name": "ORDERS", "base_object_type": "TABLE", "status": "ENABLED",
                "trigger_type": "BEFORE EACH ROW", "triggering_event": "INSERT",
            }]
        elif "from all_indexes" in normalized:
            rows = [{
                "owner": "SALES", "index_name": "IX_ORDERS", "table_owner": "SALES",
                "table_name": "ORDERS", "index_type": "NORMAL", "uniqueness": "NONUNIQUE",
                "status": "VALID",
            }]
        elif "from all_synonyms" in normalized:
            rows = [
                {"owner": "SALES", "synonym_name": "ORDERS_ALIAS", "table_owner": "SALES",
                 "table_name": "ORDERS", "db_link": None},
                {"owner": "PUBLIC", "synonym_name": "PUBLIC_ORDERS", "table_owner": "SALES",
                 "table_name": "ORDERS", "db_link": None},
            ]
        else:
            raise AssertionError(f"Unexpected query: {normalized}")

        columns = list(rows[0]) if rows else []
        self.description = [(column,) for column in columns]
        self._rows = [tuple(row[column] for column in columns) for row in rows]

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchmany(self, size: int):
        batch, self._rows = self._rows[:size], self._rows[size:]
        return batch


class FakeConnection:
    version = "23.1.0"

    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def close(self) -> None:
        pass


def test_scanner_builds_and_publishes_source_graph(tmp_path: Path) -> None:
    current = tmp_path / "oracle_graph.db"
    staging = tmp_path / "oracle_graph.next.db"
    scanner = OracleScanner(
        OracleCredentials("reader", "secret", "test", "thin"),
        staging,
        current,
        connection_factory=lambda _credentials: FakeConnection(),
    )
    states = []

    scanner.run(
        ScanOptions(("SALES",)),
        lambda state, **_kwargs: states.append(state),
        threading.Event(),
    )

    assert current.is_file()
    assert not staging.exists()
    with sqlite3.connect(current) as connection:
        assert connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 7
        assert connection.execute(
            "SELECT COUNT(*) FROM objects WHERE is_external = 1"
        ).fetchone()[0] == 1
        assert dict(connection.execute(
            "SELECT relationship_type, COUNT(*) FROM relationships GROUP BY relationship_type"
        )) == {
            "DEPENDS_ON": 1,
            "FOREIGN_KEY": 1,
            "INDEX_ON": 1,
            "POINTS_TO": 2,
            "TRIGGER_ON": 1,
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM relationship_evidence"
        ).fetchone()[0] == 6


def test_cancelled_scanner_preserves_current_database(tmp_path: Path) -> None:
    current = tmp_path / "oracle_graph.db"
    staging = tmp_path / "oracle_graph.next.db"
    initialize_database(current)
    with sqlite3.connect(current) as connection:
        connection.execute(
            "INSERT INTO app_meta VALUES ('marker', '\"current\"', '2026-07-14T00:00:00Z')"
        )
        connection.commit()

    scanner = OracleScanner(
        OracleCredentials("reader", "secret", "test", "thin"),
        staging,
        current,
        connection_factory=lambda _credentials: FakeConnection(),
    )
    cancelled = threading.Event()

    def cancel_before_relationships(state, **_kwargs) -> None:
        if state == "EXTRACTING_RELATIONSHIPS":
            cancelled.set()

    with pytest.raises(ScanCancelled):
        scanner.run(ScanOptions(("SALES",)), cancel_before_relationships, cancelled)

    assert not staging.exists()
    with sqlite3.connect(current) as connection:
        assert connection.execute(
            "SELECT value_json FROM app_meta WHERE key = 'marker'"
        ).fetchone()[0] == '"current"'
