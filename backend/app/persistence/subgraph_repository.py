from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.graph.models import GraphEdge, GraphNode

from .database import database


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _chunks(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


class SubgraphRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def create(
        self,
        name: str,
        object_ids: list[str],
        *,
        parent_id: str | None = None,
        source_kind: str = "COMPONENT_SELECTION",
        source_analysis_id: str | None = None,
        source_community_id: int | None = None,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(object_ids))
        if not unique_ids:
            raise ValueError("A részgráf nem lehet üres.")
        subgraph_id = str(uuid.uuid4())
        with database(self.path) as connection:
            found = sum(int(connection.execute(
                f"SELECT COUNT(*) FROM objects WHERE id IN ({_placeholders(chunk)})",
                chunk,
            ).fetchone()[0]) for chunk in _chunks(unique_ids))
            if found != len(unique_ids):
                raise ValueError("A részgráf egy vagy több objektuma nem található az aktuális felmérésben.")
            if parent_id is not None and connection.execute(
                "SELECT 1 FROM named_subgraphs WHERE id = ?", (parent_id,)
            ).fetchone() is None:
                raise ValueError("A szülő részgráf nem található.")
            connection.execute(
                """
                INSERT INTO named_subgraphs (
                    id, name, parent_id, source_kind, source_analysis_id,
                    source_community_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subgraph_id, name, parent_id, source_kind,
                    source_analysis_id, source_community_id, _now(),
                ),
            )
            connection.executemany(
                "INSERT INTO named_subgraph_membership (subgraph_id, object_id) VALUES (?, ?)",
                [(subgraph_id, object_id) for object_id in unique_ids],
            )
            connection.commit()
        return self.get(subgraph_id) or {}

    def create_from_community(
        self,
        name: str,
        analysis_id: str,
        community_id: int,
        *,
        parent_id: str | None,
    ) -> dict[str, Any]:
        with database(self.path, read_only=True) as connection:
            analysis_row = connection.execute(
                "SELECT config_json FROM analysis_runs WHERE id = ? AND status = 'SUCCEEDED'",
                (analysis_id,),
            ).fetchone()
            if analysis_row is None:
                raise ValueError("A sikeres forráselemzés nem található.")
            source_subgraph_id = json.loads(analysis_row["config_json"]).get("subgraphId")
            if parent_id is None:
                parent_id = source_subgraph_id
            elif source_subgraph_id is not None and parent_id != source_subgraph_id:
                raise ValueError("A szülő részgráf nem egyezik a közösséget létrehozó elemzés részgráfjával.")
            object_ids = [
                row["object_id"]
                for row in connection.execute(
                    """
                    SELECT object_id FROM analysis_membership
                    WHERE analysis_id = ? AND community_id = ?
                    ORDER BY object_id
                    """,
                    (analysis_id, community_id),
                ).fetchall()
            ]
        if not object_ids:
            raise ValueError("A közösség nem található vagy nem tartalmaz objektumot.")
        return self.create(
            name,
            object_ids,
            parent_id=parent_id,
            source_kind="COMMUNITY",
            source_analysis_id=analysis_id,
            source_community_id=community_id,
        )

    @staticmethod
    def _to_api(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "parentId": row["parent_id"],
            "sourceKind": row["source_kind"],
            "sourceAnalysisId": row["source_analysis_id"],
            "sourceCommunityId": row["source_community_id"],
            "createdAt": row["created_at"],
            "nodeCount": int(row["node_count"]),
            "edgeCount": int(row["edge_count"]),
        }

    def get(self, subgraph_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                """
                SELECT ns.*,
                       COUNT(DISTINCT nsm.object_id) AS node_count,
                       (SELECT COUNT(*) FROM relationships r
                        WHERE EXISTS (
                            SELECT 1 FROM named_subgraph_membership s
                            WHERE s.subgraph_id = ns.id AND s.object_id = r.source_id
                        ) AND EXISTS (
                            SELECT 1 FROM named_subgraph_membership t
                            WHERE t.subgraph_id = ns.id AND t.object_id = r.target_id
                        )) AS edge_count
                FROM named_subgraphs ns
                LEFT JOIN named_subgraph_membership nsm ON nsm.subgraph_id = ns.id
                WHERE ns.id = ? GROUP BY ns.id
                """,
                (subgraph_id,),
            ).fetchone()
        return self._to_api(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT ns.*,
                       COUNT(DISTINCT nsm.object_id) AS node_count,
                       (SELECT COUNT(*) FROM relationships r
                        WHERE EXISTS (
                            SELECT 1 FROM named_subgraph_membership s
                            WHERE s.subgraph_id = ns.id AND s.object_id = r.source_id
                        ) AND EXISTS (
                            SELECT 1 FROM named_subgraph_membership t
                            WHERE t.subgraph_id = ns.id AND t.object_id = r.target_id
                        )) AS edge_count
                FROM named_subgraphs ns
                LEFT JOIN named_subgraph_membership nsm ON nsm.subgraph_id = ns.id
                GROUP BY ns.id ORDER BY ns.created_at, ns.id
                """
            ).fetchall()
        return [self._to_api(row) for row in rows]

    def node_ids(self, subgraph_id: str) -> list[str] | None:
        with database(self.path, read_only=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM named_subgraphs WHERE id = ?", (subgraph_id,)
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """
                SELECT object_id FROM named_subgraph_membership
                WHERE subgraph_id = ? ORDER BY object_id
                """,
                (subgraph_id,),
            ).fetchall()
        return [row["object_id"] for row in rows]

    def graph(self, subgraph_id: str, *, max_nodes: int, max_edges: int) -> dict[str, Any] | None:
        node_ids = self.node_ids(subgraph_id)
        if node_ids is None:
            return None
        selected_ids = node_ids[:max_nodes]
        truncated = len(node_ids) > len(selected_ids)
        if not selected_ids:
            return {"nodes": [], "edges": [], "truncated": False, "suggestion": None}
        with database(self.path, read_only=True) as connection:
            nodes = connection.execute(
                f"SELECT * FROM objects WHERE id IN ({_placeholders(selected_ids)}) ORDER BY owner, name, object_type, id",
                selected_ids,
            ).fetchall()
            edges = connection.execute(
                f"""
                SELECT * FROM relationships
                WHERE source_id IN ({_placeholders(selected_ids)})
                  AND target_id IN ({_placeholders(selected_ids)})
                ORDER BY id LIMIT ?
                """,
                (*selected_ids, *selected_ids, max_edges + 1),
            ).fetchall()
            edge_rows = edges[:max_edges]
            truncated = truncated or len(edges) > max_edges
            evidence_rows = []
            edge_ids = [row["id"] for row in edge_rows]
            if edge_ids:
                evidence_rows = connection.execute(
                    f"""
                    SELECT relationship_id, source_view, evidence_json
                    FROM relationship_evidence
                    WHERE relationship_id IN ({_placeholders(edge_ids)}) ORDER BY id
                    """,
                    edge_ids,
                ).fetchall()
        evidence: dict[str, list[dict[str, Any]]] = {}
        for row in evidence_rows:
            evidence.setdefault(row["relationship_id"], []).append({
                "sourceView": row["source_view"],
                "details": json.loads(row["evidence_json"]),
            })
        return {
            "nodes": [GraphNode.from_row(row).to_api() for row in nodes],
            "edges": [
                GraphEdge.from_row(row, tuple(evidence.get(row["id"], []))).to_api()
                for row in edge_rows
            ],
            "truncated": truncated,
            "suggestion": "A részgráf nagyobb a megjelenítési limitnél; szűkítsd vagy bontsd kisebb részgráfokra." if truncated else None,
        }

    def delete(self, subgraph_id: str) -> bool:
        with database(self.path) as connection:
            cursor = connection.execute("DELETE FROM named_subgraphs WHERE id = ?", (subgraph_id,))
            connection.commit()
        return cursor.rowcount > 0
