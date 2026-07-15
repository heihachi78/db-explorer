import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from app.graph.models import GraphEdge, GraphNode

from .database import database


Direction = Literal["INCOMING", "OUTGOING", "BOTH"]


def _placeholders(values: Iterable[object]) -> str:
    return ",".join("?" for _ in values)


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if "*" in escaped:
        return escaped.replace("*", "%")
    return f"%{escaped}%"


class GraphRepository:
    """Read-only access to the published source graph."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _object_filters(
        *,
        query: str | None = None,
        owner: str | None = None,
        object_type: str | None = None,
        status: str | None = None,
        is_external: bool | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if query:
            clauses.append("(name LIKE ? ESCAPE '\\' COLLATE NOCASE OR id LIKE ? ESCAPE '\\' COLLATE NOCASE)")
            pattern = _like_pattern(query)
            parameters.extend((pattern, pattern))
        if owner:
            clauses.append("owner = ? COLLATE NOCASE")
            parameters.append(owner)
        if object_type:
            clauses.append("object_type = ? COLLATE NOCASE")
            parameters.append(object_type)
        if status:
            clauses.append("status = ? COLLATE NOCASE")
            parameters.append(status)
        if is_external is not None:
            clauses.append("is_external = ?")
            parameters.append(int(is_external))
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), parameters

    def search_objects(
        self,
        *,
        query: str | None = None,
        owner: str | None = None,
        object_type: str | None = None,
        status: str | None = None,
        is_external: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        where, parameters = self._object_filters(
            query=query,
            owner=owner,
            object_type=object_type,
            status=status,
            is_external=is_external,
        )
        with database(self.path, read_only=True) as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM objects{where}", parameters
            ).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT * FROM objects{where}
                ORDER BY owner COLLATE NOCASE, name COLLATE NOCASE, object_type, id
                LIMIT ? OFFSET ?
                """,
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
            facets: dict[str, dict[str, int]] = {}
            for name, column in (
                ("owners", "owner"),
                ("objectTypes", "object_type"),
                ("statuses", "status"),
            ):
                facet_where = (
                    f"{where} AND {column} IS NOT NULL"
                    if where else f" WHERE {column} IS NOT NULL"
                )
                facet_rows = connection.execute(
                    f"""
                    SELECT {column} AS value, COUNT(*) AS count
                    FROM objects{facet_where}
                    GROUP BY {column} ORDER BY count DESC, value
                    """,
                    parameters,
                ).fetchall()
                facets[name] = {row["value"]: int(row["count"]) for row in facet_rows}
        return {
            "items": [GraphNode.from_row(row).to_api() for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "facets": facets,
        }

    def get_object(self, object_id: str) -> GraphNode | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM objects WHERE id = ?", (object_id,)
            ).fetchone()
        return GraphNode.from_row(row) if row else None

    def load_source_graph(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Load the normalized raw graph once for CPU-heavy analysis."""
        with database(self.path, read_only=True) as connection:
            node_rows = connection.execute("SELECT * FROM objects ORDER BY id").fetchall()
            edge_rows = connection.execute("SELECT * FROM relationships ORDER BY id").fetchall()
        return (
            [GraphNode.from_row(row) for row in node_rows],
            [GraphEdge.from_row(row) for row in edge_rows],
        )

    def get_objects(self, object_ids: Iterable[str]) -> list[GraphNode]:
        ids = tuple(dict.fromkeys(object_ids))
        if not ids:
            return []
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                f"SELECT * FROM objects WHERE id IN ({_placeholders(ids)})",
                ids,
            ).fetchall()
        by_id = {row["id"]: GraphNode.from_row(row) for row in rows}
        return [by_id[object_id] for object_id in ids if object_id in by_id]

    def get_object_details(self, object_id: str) -> dict[str, Any]:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT detail_type, details_json
                FROM object_details WHERE object_id = ? ORDER BY detail_type
                """,
                (object_id,),
            ).fetchall()
        return {row["detail_type"]: json.loads(row["details_json"]) for row in rows}

    def relationship_counts(self, object_id: str) -> dict[str, int]:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN source_id = ? THEN 1 ELSE 0 END) AS outgoing,
                    SUM(CASE WHEN target_id = ? THEN 1 ELSE 0 END) AS incoming
                FROM relationships
                WHERE source_id = ? OR target_id = ?
                """,
                (object_id, object_id, object_id, object_id),
            ).fetchone()
        return {
            "outgoing": int(row["outgoing"] or 0),
            "incoming": int(row["incoming"] or 0),
        }

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM relationships WHERE id = ?", (edge_id,)
            ).fetchone()
            if not row:
                return None
            evidence = self._load_evidence(connection, (edge_id,)).get(edge_id, ())
        return GraphEdge.from_row(row, evidence)

    @staticmethod
    def _load_evidence(connection: Any, edge_ids: tuple[str, ...]) -> dict[str, tuple[dict[str, Any], ...]]:
        if not edge_ids:
            return {}
        rows = connection.execute(
            f"""
            SELECT relationship_id, source_view, evidence_json
            FROM relationship_evidence
            WHERE relationship_id IN ({_placeholders(edge_ids)})
            ORDER BY relationship_id, id
            """,
            edge_ids,
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["relationship_id"], []).append({
                "sourceView": row["source_view"],
                "details": json.loads(row["evidence_json"]),
            })
        return {edge_id: tuple(items) for edge_id, items in grouped.items()}

    def adjacent_edges(
        self,
        object_ids: Iterable[str],
        *,
        direction: Direction,
        relationship_types: tuple[str, ...] = (),
        minimum_confidence: float = 0.0,
        include_evidence: bool = True,
    ) -> list[GraphEdge]:
        ids = tuple(dict.fromkeys(object_ids))
        if not ids:
            return []
        id_sql = _placeholders(ids)
        parameters: list[Any]
        if direction == "OUTGOING":
            endpoint_clause = f"source_id IN ({id_sql})"
            parameters = list(ids)
        elif direction == "INCOMING":
            endpoint_clause = f"target_id IN ({id_sql})"
            parameters = list(ids)
        else:
            endpoint_clause = f"(source_id IN ({id_sql}) OR target_id IN ({id_sql}))"
            parameters = [*ids, *ids]
        clauses = [endpoint_clause, "confidence >= ?"]
        parameters.append(minimum_confidence)
        if relationship_types:
            clauses.append(f"relationship_type IN ({_placeholders(relationship_types)})")
            parameters.extend(relationship_types)
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                "SELECT * FROM relationships WHERE " + " AND ".join(clauses)
                + " ORDER BY id",
                parameters,
            ).fetchall()
            edge_ids = tuple(row["id"] for row in rows)
            evidence = self._load_evidence(connection, edge_ids) if include_evidence else {}
        return [GraphEdge.from_row(row, evidence.get(row["id"], ())) for row in rows]
