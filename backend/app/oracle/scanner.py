import json
import threading
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import oracledb

from app.errors import AppError
from app.graph.normalization import (
    iso_value,
    json_value,
    normalize_object_type,
    stable_object_id,
)
from app.persistence.database import publish_database
from app.persistence.scan_writer import ScanWriter
from app.tasks.models import TaskState

from .connection import OracleCredentials, connect_read_only


RELATIONSHIP_NAMESPACE = uuid.UUID("f52431d7-a90a-4940-b505-7adecf0fc8ef")
CRITICAL_VIEWS = {"ALL_OBJECTS", "ALL_DEPENDENCIES", "ALL_CONSTRAINTS", "ALL_CONS_COLUMNS"}
SCANNER_VIEWS = CRITICAL_VIEWS | {"ALL_TRIGGERS", "ALL_INDEXES", "ALL_SYNONYMS"}


class ProgressReporter(Protocol):
    def __call__(
        self,
        state: TaskState,
        *,
        message: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
        counters: dict[str, int] | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ScanOptions:
    schemas: tuple[str, ...]
    object_types: tuple[str, ...] = ()
    include_source_code: bool = False
    resolve_external_references: bool = True
    include_scheduler_objects: bool = False
    synonym_max_depth: int = 8


class ScanCancelled(RuntimeError):
    pass


def resolve_synonym_chain(
    source: tuple[str, str],
    synonyms: dict[tuple[str, str], tuple[str, str, str | None]],
    max_depth: int,
) -> dict[str, Any]:
    current = source
    visited = {source}
    path = [source]
    for depth in range(1, max_depth + 1):
        target = synonyms.get(current)
        if target is None:
            return {
                "status": "RESOLVED", "depth": depth - 1,
                "finalOwner": current[0], "finalName": current[1], "path": path,
            }
        target_key = (target[0], target[1])
        path.append(target_key)
        if target[2]:
            return {
                "status": "REMOTE", "depth": depth,
                "finalOwner": target[0], "finalName": target[1], "path": path,
            }
        if target_key in visited:
            return {
                "status": "CYCLE", "depth": depth,
                "finalOwner": target[0], "finalName": target[1], "path": path,
            }
        if target_key not in synonyms:
            return {
                "status": "RESOLVED", "depth": depth,
                "finalOwner": target[0], "finalName": target[1], "path": path,
            }
        visited.add(target_key)
        current = target_key
    return {
        "status": "MAX_DEPTH", "depth": max_depth,
        "finalOwner": current[0], "finalName": current[1], "path": path,
    }


class ObjectResolver:
    def __init__(self) -> None:
        self.by_exact: dict[tuple[str, str, str], str] = {}
        self.by_name: dict[tuple[str, str], list[tuple[str, str]]] = {}

    def add(self, owner: str, name: str, oracle_type: str, object_id: str) -> None:
        key = (owner, name, oracle_type)
        self.by_exact.setdefault(key, object_id)
        candidates = self.by_name.setdefault((owner, name), [])
        candidate = (oracle_type, object_id)
        if candidate not in candidates:
            candidates.append(candidate)

    def resolve(self, owner: str, name: str, oracle_type: str | None = None) -> str | None:
        if oracle_type:
            exact = self.by_exact.get((owner, name, oracle_type))
            if exact:
                return exact
            logical_type = normalize_object_type(oracle_type)
            for candidate_type, object_id in self.by_name.get((owner, name), []):
                if normalize_object_type(candidate_type) == logical_type:
                    return object_id
        candidates = self.by_name.get((owner, name), [])
        if len(candidates) == 1:
            return candidates[0][1]
        # ALL_SYNONYMS does not expose the target type. Oracle namespaces can
        # still contain a table and an index with the same name, so prefer
        # semantic objects over technical ones for name-only resolution.
        priority = {
            "TABLE": 0, "VIEW": 1, "MATERIALIZED_VIEW": 2, "PACKAGE": 3,
            "PROCEDURE": 4, "FUNCTION": 5, "TYPE": 6, "SEQUENCE": 7,
            "SYNONYM": 8, "TRIGGER": 9, "INDEX": 10,
        }
        ranked = sorted(
            candidates,
            key=lambda candidate: priority.get(normalize_object_type(candidate[0]), 99),
        )
        return ranked[0][1] if ranked else None


def _bind_list(prefix: str, values: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    names = [f"{prefix}_{index}" for index in range(len(values))]
    return ", ".join(f":{name}" for name in names), dict(zip(names, values, strict=True))


def _column_name(description: Any) -> str:
    return str(getattr(description, "name", description[0])).lower()


def _rows(
    connection: oracledb.Connection,
    query: str,
    parameters: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.arraysize = 1000
        cursor.prefetchrows = 1000
        cursor.execute(query, parameters or {})
        columns = [_column_name(column) for column in cursor.description]
        while batch := cursor.fetchmany(1000):
            for row in batch:
                yield dict(zip(columns, row, strict=True))


def _relationship_id(
    source_id: str,
    target_id: str,
    relationship_type: str,
    metadata_json: str,
) -> str:
    canonical = "\x1f".join((source_id, target_id, relationship_type, metadata_json))
    return f"rel-{uuid.uuid5(RELATIONSHIP_NAMESPACE, canonical)}"


def _relationship(
    source_id: str,
    target_id: str,
    relationship_type: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    metadata_json = json_value(metadata)
    return {
        "id": _relationship_id(source_id, target_id, relationship_type, metadata_json),
        "source_id": source_id,
        "target_id": target_id,
        "relationship_type": relationship_type,
        "directed": 1,
        "confidence": 1.0,
        "origin": "ORACLE_CATALOG",
        "metadata_json": metadata_json,
    }


class OracleScanner:
    def __init__(
        self,
        credentials: OracleCredentials,
        next_path: Path,
        current_path: Path,
        *,
        connection_factory: Callable[[OracleCredentials], oracledb.Connection] = connect_read_only,
    ) -> None:
        self.credentials = credentials
        self.next_path = next_path
        self.current_path = current_path
        self.connection_factory = connection_factory
        self.database_key = ""
        self.container_key = ""
        self.resolver = ObjectResolver()
        self.warnings: list[str] = []
        self.counters: Counter[str] = Counter()

    def run(
        self,
        options: ScanOptions,
        report: ProgressReporter,
        cancelled: threading.Event,
        publication_lock: Any | None = None,
        published: threading.Event | None = None,
    ) -> dict[str, Any]:
        schemas = tuple(dict.fromkeys(options.schemas))
        if not schemas:
            raise AppError("SCAN_SCHEMAS_REQUIRED", "At least one schema must be selected.")

        connection: oracledb.Connection | None = None
        started_at = datetime.now(UTC)
        try:
            self._check_cancel(cancelled)
            report(TaskState.CONNECTING, message="Connecting to Oracle in read-only mode.")
            connection = self.connection_factory(self.credentials)

            report(TaskState.DISCOVERING_SCHEMAS, message="Checking schemas and catalog views.")
            identity = self._discover_identity(connection)
            self.database_key = identity["databaseName"] or "local-oracle"
            self.container_key = identity["containerName"] or self.database_key
            readable_views = self._readable_views(connection)
            missing_critical = sorted(CRITICAL_VIEWS - readable_views)
            if missing_critical:
                raise AppError(
                    "SCAN_CAPABILITY_MISSING",
                    "Required Oracle catalog views are not readable.",
                    status_code=422,
                    details={"missingViews": missing_critical},
                )
            self.warnings.extend(
                f"Optional catalog view is not readable: {view}"
                for view in sorted(SCANNER_VIEWS - readable_views)
            )
            self._validate_schemas(connection, schemas)
            self._check_cancel(cancelled)

            with ScanWriter(self.next_path) as writer:
                report(TaskState.EXTRACTING_OBJECTS, message="Extracting Oracle objects.")
                self._extract_objects(connection, writer, options, schemas, cancelled, report)

                report(
                    TaskState.EXTRACTING_RELATIONSHIPS,
                    message="Extracting dependencies and typed relationships.",
                    counters=dict(self.counters),
                )
                self._extract_dependencies(connection, writer, schemas, options, cancelled)
                self._extract_foreign_keys(connection, writer, schemas, options, cancelled)
                if "ALL_TRIGGERS" in readable_views:
                    self._extract_triggers(connection, writer, schemas, options, cancelled)
                if "ALL_INDEXES" in readable_views:
                    self._extract_indexes(connection, writer, schemas, options, cancelled)
                if "ALL_SYNONYMS" in readable_views:
                    self._extract_synonyms(connection, writer, schemas, options, cancelled)
                writer.commit()

                report(TaskState.NORMALIZING, message="Finalizing normalized graph metadata.")
                objects, relationships, external = writer.counts()
                self.counters["objects"] = objects
                self.counters["relationships"] = relationships
                self.counters["externalObjects"] = external
                summary = self._summary(writer, schemas, options, identity, started_at)
                writer.set_meta("schema_version", 1)
                writer.set_meta("scan_summary", summary)
                writer.set_meta("selected_schemas", list(schemas))
                writer.commit()

                self._check_cancel(cancelled)
                report(TaskState.VALIDATING, message="Validating graph and SQLite integrity.")
                writer.validate()

            self._check_cancel(cancelled)
            report(
                TaskState.PUBLISHING,
                message="Publishing the new graph atomically.",
                counters=dict(self.counters),
            )
            # Cancellation and the commit point share a lock. A cancellation
            # arriving before this block prevents publication; one arriving
            # after os.replace observes the published flag and keeps success.
            commit_lock = publication_lock or threading.Lock()
            with commit_lock:
                self._check_cancel(cancelled)
                publish_database(self.next_path, self.current_path)
                if published is not None:
                    published.set()
            return summary
        except BaseException:
            self.next_path.unlink(missing_ok=True)
            raise
        finally:
            if connection is not None:
                connection.close()

    def _check_cancel(self, cancelled: threading.Event) -> None:
        if cancelled.is_set():
            raise ScanCancelled("Scan was cancelled before publication.")

    def _discover_identity(self, connection: oracledb.Connection) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
                       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
                FROM dual
                """
            )
            database_name, container_name = cursor.fetchone()
        return {
            "databaseName": database_name,
            "containerName": container_name,
            "oracleVersion": connection.version,
        }

    def _readable_views(self, connection: oracledb.Connection) -> set[str]:
        readable: set[str] = set()
        with connection.cursor() as cursor:
            for view in sorted(SCANNER_VIEWS):
                try:
                    cursor.execute(f"SELECT 1 FROM {view} WHERE 1 = 0")
                    readable.add(view)
                except oracledb.Error:
                    continue
        return readable

    def _validate_schemas(
        self, connection: oracledb.Connection, schemas: tuple[str, ...]
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        rows = _rows(
            connection,
            f"SELECT DISTINCT owner FROM all_objects WHERE owner IN ({owner_sql})",
            parameters,
        )
        visible = {str(row["owner"]) for row in rows}
        missing = [schema for schema in schemas if schema not in visible]
        if missing:
            raise AppError(
                "SCAN_SCHEMA_NOT_VISIBLE",
                "One or more selected schemas are not visible to the Oracle account.",
                status_code=422,
                details={"schemas": missing},
            )

    def _extract_objects(
        self,
        connection: oracledb.Connection,
        writer: ScanWriter,
        options: ScanOptions,
        schemas: tuple[str, ...],
        cancelled: threading.Event,
        report: ProgressReporter,
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        filters = [f"owner IN ({owner_sql})"]
        if options.object_types:
            requested = tuple(value.replace("_", " ") for value in options.object_types)
            type_sql, type_parameters = _bind_list("object_type", requested)
            parameters.update(type_parameters)
            filters.append(f"object_type IN ({type_sql})")
        query = f"""
            SELECT owner, object_name, subobject_name, object_id,
                   object_type, status, created, last_ddl_time
            FROM all_objects
            WHERE {' AND '.join(filters)}
            ORDER BY owner, object_type, object_name, subobject_name
        """
        batch: list[dict[str, Any]] = []
        for index, row in enumerate(_rows(connection, query, parameters), start=1):
            if index % 1000 == 0:
                self._check_cancel(cancelled)
            oracle_type = str(row["object_type"])
            object_type = normalize_object_type(oracle_type)
            owner = str(row["owner"])
            name = str(row["object_name"])
            subobject = row["subobject_name"]
            object_id = stable_object_id(
                self.database_key, self.container_key, owner, object_type, name,
                str(subobject) if subobject is not None else None,
            )
            batch.append({
                "id": object_id,
                "database_key": self.database_key,
                "container_key": self.container_key,
                "owner": owner,
                "name": name,
                "subobject_name": subobject,
                "object_type": object_type,
                "oracle_object_type": oracle_type,
                "status": row["status"],
                "oracle_object_id": row["object_id"],
                "created_at": iso_value(row["created"]),
                "last_ddl_at": iso_value(row["last_ddl_time"]),
                "is_external": 0,
                "metadata_json": "{}",
            })
            self.resolver.add(owner, name, oracle_type, object_id)
            self.counters[f"owner:{owner}"] += 1
            self.counters[f"objectType:{object_type}"] += 1
            if len(batch) >= 1000:
                writer.insert_objects(batch)
                batch.clear()
                report(
                    TaskState.EXTRACTING_OBJECTS,
                    message=f"Extracted {index} Oracle objects.",
                    progress_current=index,
                    counters={"objectsExtracted": index},
                )
        writer.insert_objects(batch)
        self.counters["objectsExtracted"] = sum(
            value for key, value in self.counters.items() if key.startswith("owner:")
        )

    def _ensure_object(
        self,
        writer: ScanWriter,
        owner: str,
        name: str,
        oracle_type: str | None,
        *,
        external: bool,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        existing = self.resolver.resolve(owner, name, oracle_type)
        if existing:
            return existing
        logical_type = "EXTERNAL_OBJECT" if external else normalize_object_type(oracle_type)
        id_type = normalize_object_type(oracle_type)
        object_id = stable_object_id(
            self.database_key, self.container_key, owner, id_type, name
        )
        writer.insert_objects([{
            "id": object_id,
            "database_key": self.database_key,
            "container_key": self.container_key,
            "owner": owner,
            "name": name,
            "subobject_name": None,
            "object_type": logical_type,
            "oracle_object_type": oracle_type or "UNKNOWN",
            "status": None,
            "oracle_object_id": None,
            "created_at": None,
            "last_ddl_at": None,
            "is_external": int(external),
            "metadata_json": json_value(metadata or {}),
        }])
        self.resolver.add(owner, name, oracle_type or "UNKNOWN", object_id)
        if external:
            self.counters["externalObjectsCreated"] += 1
        return object_id

    def _target(
        self,
        writer: ScanWriter,
        owner: str,
        name: str,
        oracle_type: str | None,
        options: ScanOptions,
        *,
        force_external: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not force_external:
            resolved = self.resolver.resolve(owner, name, oracle_type)
            if resolved:
                return resolved
        if not options.resolve_external_references:
            self.counters["externalReferencesSkipped"] += 1
            return None
        if force_external:
            # A database-link target is a different namespace even when a local
            # object happens to have the same owner and name.
            remote_name = f"{name}@{(metadata or {}).get('databaseLink') or 'DB_LINK'}"
            return self._ensure_object(
                writer, owner, remote_name, oracle_type, external=True,
                metadata={"placeholderReason": "REMOTE_REFERENCE", **(metadata or {})},
            )
        return self._ensure_object(
            writer, owner, name, oracle_type, external=True,
            metadata={"placeholderReason": "UNRESOLVED_REFERENCE", **(metadata or {})},
        )

    def _save_relationship(
        self,
        writer: ScanWriter,
        source_id: str | None,
        target_id: str | None,
        relationship_type: str,
        metadata: dict[str, Any],
        source_view: str,
        evidence: dict[str, Any],
    ) -> None:
        if not source_id or not target_id:
            self.counters["relationshipsSkipped"] += 1
            return
        if writer.insert_relationship(
            _relationship(source_id, target_id, relationship_type, metadata),
            source_view=source_view,
            evidence=evidence,
        ):
            self.counters[f"relationshipType:{relationship_type}"] += 1

    def _extract_dependencies(
        self,
        connection: oracledb.Connection,
        writer: ScanWriter,
        schemas: tuple[str, ...],
        options: ScanOptions,
        cancelled: threading.Event,
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        query = f"""
            SELECT owner, name, type, referenced_owner, referenced_name,
                   referenced_type, dependency_type, referenced_link_name
            FROM all_dependencies
            WHERE owner IN ({owner_sql}) AND referenced_owner IS NOT NULL
            ORDER BY owner, name, type, referenced_owner, referenced_name
        """
        for index, row in enumerate(_rows(connection, query, parameters), start=1):
            if index % 1000 == 0:
                self._check_cancel(cancelled)
            source = self.resolver.resolve(str(row["owner"]), str(row["name"]), str(row["type"]))
            target = self._target(
                writer, str(row["referenced_owner"]), str(row["referenced_name"]),
                str(row["referenced_type"]) if row["referenced_type"] else None, options,
                force_external=bool(row["referenced_link_name"]),
                metadata={"databaseLink": row["referenced_link_name"]},
            )
            metadata = {
                "dependencyType": row["dependency_type"],
                "referencedLinkName": row["referenced_link_name"],
            }
            evidence = {key: row[key] for key in row}
            self._save_relationship(
                writer, source, target, "DEPENDS_ON", metadata,
                "ALL_DEPENDENCIES", evidence,
            )

    def _extract_foreign_keys(
        self,
        connection: oracledb.Connection,
        writer: ScanWriter,
        schemas: tuple[str, ...],
        options: ScanOptions,
        cancelled: threading.Event,
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        query = f"""
            SELECT c.owner, c.table_name, c.constraint_name, c.delete_rule, c.status,
                   cc.column_name AS source_column, cc.position,
                   r.owner AS target_owner, r.table_name AS target_table,
                   rcc.column_name AS target_column
            FROM all_constraints c
            JOIN all_cons_columns cc
              ON cc.owner = c.owner AND cc.constraint_name = c.constraint_name
            JOIN all_constraints r
              ON r.owner = c.r_owner AND r.constraint_name = c.r_constraint_name
            JOIN all_cons_columns rcc
              ON rcc.owner = r.owner AND rcc.constraint_name = r.constraint_name
             AND rcc.position = cc.position
            WHERE c.constraint_type = 'R' AND c.owner IN ({owner_sql})
            ORDER BY c.owner, c.constraint_name, cc.position
        """
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for index, row in enumerate(_rows(connection, query, parameters), start=1):
            if index % 1000 == 0:
                self._check_cancel(cancelled)
            key = (str(row["owner"]), str(row["constraint_name"]))
            item = grouped.setdefault(key, {
                "row": row,
                "sourceColumns": [],
                "targetColumns": [],
                "positions": [],
            })
            item["sourceColumns"].append(row["source_column"])
            item["targetColumns"].append(row["target_column"])
            item["positions"].append(int(row["position"]))

        for item in grouped.values():
            row = item["row"]
            positions = item["positions"]
            if positions != list(range(1, len(positions) + 1)):
                raise RuntimeError(
                    f"Non-contiguous FK column positions: {row['owner']}.{row['constraint_name']}"
                )
            source = self.resolver.resolve(str(row["owner"]), str(row["table_name"]), "TABLE")
            target = self._target(
                writer, str(row["target_owner"]), str(row["target_table"]),
                "TABLE", options,
            )
            metadata = {
                "constraintName": row["constraint_name"],
                "sourceColumns": item["sourceColumns"],
                "targetColumns": item["targetColumns"],
                "deleteRule": row["delete_rule"],
                "status": row["status"],
            }
            self._save_relationship(
                writer, source, target, "FOREIGN_KEY", metadata,
                "ALL_CONSTRAINTS+ALL_CONS_COLUMNS",
                {**metadata, "owner": row["owner"], "targetOwner": row["target_owner"]},
            )

    def _extract_triggers(
        self,
        connection: oracledb.Connection,
        writer: ScanWriter,
        schemas: tuple[str, ...],
        options: ScanOptions,
        cancelled: threading.Event,
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        query = f"""
            SELECT owner, trigger_name, table_owner, table_name, base_object_type,
                   status, trigger_type, triggering_event
            FROM all_triggers
            WHERE owner IN ({owner_sql})
            ORDER BY owner, trigger_name
        """
        for index, row in enumerate(_rows(connection, query, parameters), start=1):
            if index % 1000 == 0:
                self._check_cancel(cancelled)
            source = self.resolver.resolve(str(row["owner"]), str(row["trigger_name"]), "TRIGGER")
            if row["table_owner"] is None or row["table_name"] is None:
                self.counters["schemaOrDatabaseTriggersSkipped"] += 1
                continue
            target_type = str(row["base_object_type"] or "TABLE")
            target = self._target(
                writer, str(row["table_owner"]), str(row["table_name"]), target_type, options
            )
            metadata = {
                "status": row["status"], "triggerType": row["trigger_type"],
                "triggeringEvent": row["triggering_event"],
            }
            self._save_relationship(
                writer, source, target, "TRIGGER_ON", metadata,
                "ALL_TRIGGERS", {key: row[key] for key in row},
            )

    def _extract_indexes(
        self,
        connection: oracledb.Connection,
        writer: ScanWriter,
        schemas: tuple[str, ...],
        options: ScanOptions,
        cancelled: threading.Event,
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        query = f"""
            SELECT owner, index_name, table_owner, table_name, index_type,
                   uniqueness, status
            FROM all_indexes
            WHERE owner IN ({owner_sql})
            ORDER BY owner, index_name
        """
        for index, row in enumerate(_rows(connection, query, parameters), start=1):
            if index % 1000 == 0:
                self._check_cancel(cancelled)
            source = self.resolver.resolve(str(row["owner"]), str(row["index_name"]), "INDEX")
            target = self._target(
                writer, str(row["table_owner"]), str(row["table_name"]), "TABLE", options
            )
            metadata = {
                "indexType": row["index_type"], "uniqueness": row["uniqueness"],
                "status": row["status"],
            }
            self._save_relationship(
                writer, source, target, "INDEX_ON", metadata,
                "ALL_INDEXES", {key: row[key] for key in row},
            )

    def _extract_synonyms(
        self,
        connection: oracledb.Connection,
        writer: ScanWriter,
        schemas: tuple[str, ...],
        options: ScanOptions,
        cancelled: threading.Event,
    ) -> None:
        owner_sql, parameters = _bind_list("owner", schemas)
        query = f"""
            SELECT owner, synonym_name, table_owner, table_name, db_link
            FROM all_synonyms
            WHERE owner IN ({owner_sql})
               OR (owner = 'PUBLIC' AND table_owner IN ({owner_sql}))
            ORDER BY owner, synonym_name
        """
        rows = list(_rows(connection, query, parameters))
        synonym_targets = {
            (str(row["owner"]), str(row["synonym_name"])): (
                str(row["table_owner"]), str(row["table_name"]),
                str(row["db_link"]) if row["db_link"] else None,
            )
            for row in rows
        }
        for row in rows:
            owner = str(row["owner"])
            name = str(row["synonym_name"])
            self._ensure_object(
                writer, owner, name, "SYNONYM", external=False,
                metadata={"public": owner == "PUBLIC"},
            )
        reported_cycles: set[tuple[tuple[str, str], ...]] = set()
        for index, row in enumerate(rows, start=1):
            if index % 1000 == 0:
                self._check_cancel(cancelled)
            owner = str(row["owner"])
            name = str(row["synonym_name"])
            source = self.resolver.resolve(owner, name, "SYNONYM")
            target_owner = str(row["table_owner"])
            target_name = str(row["table_name"])
            resolution = resolve_synonym_chain(
                (owner, name), synonym_targets, options.synonym_max_depth
            )
            resolution_path = [f"{item_owner}.{item_name}" for item_owner, item_name in resolution["path"]]
            if resolution["status"] == "CYCLE":
                cycle_key = tuple(sorted(set(resolution["path"][:-1])))
                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    self.counters["synonymCycles"] += 1
                    self.warnings.append(
                        "Synonym cycle detected: " + " -> ".join(resolution_path)
                    )
                self.counters["unresolvedSynonyms"] += 1
            elif resolution["status"] == "MAX_DEPTH":
                self.counters["synonymDepthExceeded"] += 1
                self.counters["unresolvedSynonyms"] += 1
                self.warnings.append(
                    f"Synonym resolution reached depth {options.synonym_max_depth}: "
                    + " -> ".join(resolution_path)
                )
            target = self.resolver.resolve(target_owner, target_name)
            if target is None:
                target = self._target(
                    writer, target_owner, target_name, None, options,
                    force_external=bool(row["db_link"]),
                    metadata={"databaseLink": row["db_link"]},
                )
                if resolution["status"] not in {"CYCLE", "MAX_DEPTH"}:
                    self.counters["unresolvedSynonyms"] += 1
            metadata = {
                "databaseLink": row["db_link"],
                "public": owner == "PUBLIC",
                "resolutionStatus": resolution["status"],
                "resolutionDepth": resolution["depth"],
                "resolvedOwner": resolution["finalOwner"],
                "resolvedName": resolution["finalName"],
                "resolutionPath": resolution_path,
            }
            self._save_relationship(
                writer, source, target, "POINTS_TO", metadata,
                "ALL_SYNONYMS", {key: row[key] for key in row},
            )

    def _summary(
        self,
        writer: ScanWriter,
        schemas: tuple[str, ...],
        options: ScanOptions,
        identity: dict[str, Any],
        started_at: datetime,
    ) -> dict[str, Any]:
        owner_counts = {
            row[0]: row[1]
            for row in writer.db.execute(
                "SELECT owner, COUNT(*) FROM objects GROUP BY owner ORDER BY owner"
            )
        }
        object_type_counts = {
            row[0]: row[1]
            for row in writer.db.execute(
                "SELECT object_type, COUNT(*) FROM objects GROUP BY object_type ORDER BY object_type"
            )
        }
        relationship_type_counts = {
            row[0]: row[1]
            for row in writer.db.execute(
                """
                SELECT relationship_type, COUNT(*) FROM relationships
                GROUP BY relationship_type ORDER BY relationship_type
                """
            )
        }
        return {
            "databaseName": identity["databaseName"],
            "containerName": identity["containerName"],
            "oracleVersion": identity["oracleVersion"],
            "selectedSchemas": list(schemas),
            "objectTypeFilter": list(options.object_types),
            "startedAt": started_at.isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "ownerCounts": owner_counts,
            "objectTypeCounts": object_type_counts,
            "relationshipTypeCounts": relationship_type_counts,
            "externalObjectCount": self.counters["externalObjects"],
            "unresolvedSynonymCount": self.counters["unresolvedSynonyms"],
            "synonymCycleCount": self.counters["synonymCycles"],
            "synonymDepthExceededCount": self.counters["synonymDepthExceeded"],
            "warnings": self.warnings,
        }


def load_scan_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT value_json FROM app_meta WHERE key = 'scan_summary'"
        ).fetchone()
    finally:
        connection.close()
    return json.loads(row[0]) if row else None
