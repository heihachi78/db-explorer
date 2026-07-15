from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.analysis.models import AnalysisConfig, AnalysisResult
from app.graph.models import GraphNode

from .database import database


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class AnalysisRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def create(self, analysis_id: str, config: AnalysisConfig) -> None:
        with database(self.path) as connection:
            connection.execute(
                """
                INSERT INTO analysis_runs (
                    id, name, status, algorithm, config_json, created_at
                ) VALUES (?, ?, 'QUEUED', ?, ?, ?)
                """,
                (analysis_id, config.name, config.algorithm, _json(config.to_api()), _now()),
            )
            connection.commit()

    def mark_running(self, analysis_id: str) -> bool:
        with database(self.path) as connection:
            cursor = connection.execute(
                """
                UPDATE analysis_runs SET status = 'RUNNING', started_at = ?
                WHERE id = ? AND status = 'QUEUED'
                """,
                (_now(), analysis_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    def recover_interrupted(self) -> int:
        with database(self.path) as connection:
            cursor = connection.execute(
                """
                UPDATE analysis_runs
                SET status = 'CANCELLED',
                    error_message = 'Application stopped before the analysis completed.',
                    finished_at = ?
                WHERE status IN ('QUEUED', 'RUNNING')
                """,
                (_now(),),
            )
            connection.commit()
        return cursor.rowcount

    def save_success(self, analysis_id: str, result: AnalysisResult) -> bool:
        with database(self.path) as connection:
            try:
                connection.execute("BEGIN")
                connection.executemany(
                    """
                    INSERT INTO analysis_membership (
                        analysis_id, object_id, community_id, stability
                    ) VALUES (?, ?, ?, NULL)
                    """,
                    [
                        (analysis_id, object_id, community_id)
                        for object_id, community_id in sorted(result.membership.items())
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO community_metrics (analysis_id, community_id, metrics_json)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (analysis_id, community_id, _json(metrics))
                        for community_id, metrics in sorted(result.community_metrics.items())
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO community_edges (
                        analysis_id, source_community, target_community,
                        edge_count, total_weight, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            analysis_id, edge["sourceCommunity"], edge["targetCommunity"],
                            edge["edgeCount"], edge["totalWeight"],
                            _json({
                                "relationshipTypeDistribution": edge["relationshipTypeDistribution"],
                                "bridgePairs": edge["bridgePairs"],
                                "forwardWeight": edge["forwardWeight"],
                                "reverseWeight": edge["reverseWeight"],
                            }),
                        )
                        for edge in result.community_edges
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO centrality_results (
                        analysis_id, object_id, metric, value, metadata_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            analysis_id, row["objectId"], row["metric"], row["value"],
                            _json(row["metadata"]),
                        )
                        for row in result.centrality_results
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO analysis_hierarchy (
                        analysis_id, hierarchy_id, parent_id, level, resolution,
                        split_resolution, split_quality, node_count, stop_reason,
                        metrics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            analysis_id, node["hierarchyId"], node["parentId"],
                            node["level"], node["resolution"], node["splitResolution"],
                            node["splitQuality"], node["nodeCount"], node["stopReason"],
                            _json(node["metrics"]),
                        )
                        for node in result.hierarchy_nodes
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO analysis_hierarchy_membership (
                        analysis_id, hierarchy_id, object_id
                    ) VALUES (?, ?, ?)
                    """,
                    [
                        (analysis_id, hierarchy_id, object_id)
                        for hierarchy_id, object_id in result.hierarchy_memberships
                    ],
                )
                cursor = connection.execute(
                    """
                    UPDATE analysis_runs
                    SET status = 'SUCCEEDED', result_summary_json = ?, finished_at = ?
                    WHERE id = ? AND status = 'RUNNING'
                    """,
                    (_json(result.summary), _now(), analysis_id),
                )
                if cursor.rowcount == 0:
                    connection.rollback()
                    return False
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return True

    def mark_terminal(self, analysis_id: str, status: str, error_message: str | None = None) -> None:
        with database(self.path) as connection:
            connection.execute(
                """
                UPDATE analysis_runs
                SET status = ?, error_message = ?, finished_at = ?
                WHERE id = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (status, error_message, _now(), analysis_id),
            )
            connection.commit()

    @staticmethod
    def _run_to_api(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "algorithm": row["algorithm"],
            "config": json.loads(row["config_json"]),
            "summary": json.loads(row["result_summary_json"]) if row["result_summary_json"] else None,
            "errorMessage": row["error_message"],
            "createdAt": row["created_at"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
        }

    def list(self) -> list[dict[str, Any]]:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_runs ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._run_to_api(row) for row in rows]

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM analysis_runs WHERE id = ?", (analysis_id,)
            ).fetchone()
        return self._run_to_api(row) if row else None

    def delete(self, analysis_id: str) -> bool:
        with database(self.path) as connection:
            cursor = connection.execute(
                "DELETE FROM analysis_runs WHERE id = ? AND status NOT IN ('QUEUED', 'RUNNING')",
                (analysis_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def discard_queued(self, analysis_id: str) -> None:
        with database(self.path) as connection:
            connection.execute(
                "DELETE FROM analysis_runs WHERE id = ? AND status = 'QUEUED'",
                (analysis_id,),
            )
            connection.commit()

    def communities(self, analysis_id: str) -> list[dict[str, Any]]:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT cm.community_id, cm.metrics_json, a.name AS annotation_name,
                       a.note AS annotation_note
                FROM community_metrics cm
                LEFT JOIN annotations a
                  ON a.analysis_id = cm.analysis_id AND a.community_id = cm.community_id
                WHERE cm.analysis_id = ?
                ORDER BY json_extract(cm.metrics_json, '$.nodeCount') DESC, cm.community_id
                """,
                (analysis_id,),
            ).fetchall()
        return [
            json.loads(row["metrics_json"]) | {
                "annotation": {
                    "name": row["annotation_name"], "note": row["annotation_note"],
                } if row["annotation_name"] is not None or row["annotation_note"] is not None else None
            }
            for row in rows
        ]

    def membership(self, analysis_id: str) -> dict[str, int]:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT object_id, community_id FROM analysis_membership
                WHERE analysis_id = ? ORDER BY object_id
                """,
                (analysis_id,),
            ).fetchall()
        return {row["object_id"]: row["community_id"] for row in rows}

    def update_stability(self, analysis_id: str, comparison: dict[str, Any]) -> None:
        labels = {
            item["communityId"]: item for item in comparison["communityStability"]
        }
        with database(self.path) as connection:
            try:
                connection.execute("BEGIN")
                connection.executemany(
                    """
                    UPDATE analysis_membership SET stability = ?
                    WHERE analysis_id = ? AND object_id = ?
                    """,
                    [
                        (score, analysis_id, object_id)
                        for object_id, score in comparison["nodeStability"].items()
                    ],
                )
                rows = connection.execute(
                    """
                    SELECT community_id, metrics_json FROM community_metrics
                    WHERE analysis_id = ?
                    """,
                    (analysis_id,),
                ).fetchall()
                for row in rows:
                    metrics = json.loads(row["metrics_json"])
                    stability = labels.get(row["community_id"])
                    if stability:
                        metrics["stability"] = stability["label"]
                        metrics["stabilityScore"] = stability["score"]
                    connection.execute(
                        """
                        UPDATE community_metrics SET metrics_json = ?
                        WHERE analysis_id = ? AND community_id = ?
                        """,
                        (_json(metrics), analysis_id, row["community_id"]),
                    )
                run_row = connection.execute(
                    "SELECT result_summary_json FROM analysis_runs WHERE id = ?",
                    (analysis_id,),
                ).fetchone()
                if run_row and run_row["result_summary_json"]:
                    summary = json.loads(run_row["result_summary_json"])
                    summary["stability"] = {
                        "sharedNodeCount": comparison["sharedNodeCount"],
                        "pairwise": comparison["pairwise"],
                        "thresholds": comparison["thresholds"],
                    }
                    connection.execute(
                        "UPDATE analysis_runs SET result_summary_json = ? WHERE id = ?",
                        (_json(summary), analysis_id),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def upsert_annotation(
        self,
        analysis_id: str,
        community_id: int,
        name: str | None,
        note: str | None,
    ) -> dict[str, Any] | None:
        timestamp = _now()
        with database(self.path) as connection:
            community = connection.execute(
                """
                SELECT 1 FROM community_metrics
                WHERE analysis_id = ? AND community_id = ?
                """,
                (analysis_id, community_id),
            ).fetchone()
            if community is None:
                return None
            existing = connection.execute(
                """
                SELECT id, created_at FROM annotations
                WHERE analysis_id = ? AND community_id = ?
                """,
                (analysis_id, community_id),
            ).fetchone()
            annotation_id = existing["id"] if existing else str(uuid.uuid4())
            created_at = existing["created_at"] if existing else timestamp
            connection.execute(
                """
                INSERT INTO annotations (
                    id, analysis_id, community_id, name, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id, community_id) DO UPDATE SET
                    name = excluded.name, note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    annotation_id, analysis_id, community_id, name, note,
                    created_at, timestamp,
                ),
            )
            connection.commit()
        return {
            "id": annotation_id,
            "analysisId": analysis_id,
            "communityId": community_id,
            "name": name,
            "note": note,
            "createdAt": created_at,
            "updatedAt": timestamp,
        }

    def annotation(self, annotation_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM annotations WHERE id = ?", (annotation_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"], "analysisId": row["analysis_id"],
            "communityId": row["community_id"], "name": row["name"],
            "note": row["note"], "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def community(self, analysis_id: str, community_id: int) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            metrics_row = connection.execute(
                """
                SELECT metrics_json FROM community_metrics
                WHERE analysis_id = ? AND community_id = ?
                """,
                (analysis_id, community_id),
            ).fetchone()
            if metrics_row is None:
                return None
            node_rows = connection.execute(
                """
                SELECT o.*
                FROM analysis_membership am
                JOIN objects o ON o.id = am.object_id
                WHERE am.analysis_id = ? AND am.community_id = ?
                ORDER BY o.owner, o.name, o.object_type, o.id
                """,
                (analysis_id, community_id),
            ).fetchall()
            centrality_rows = connection.execute(
                """
                SELECT object_id, metric, value
                FROM centrality_results
                WHERE analysis_id = ? AND object_id IN (
                    SELECT object_id FROM analysis_membership
                    WHERE analysis_id = ? AND community_id = ?
                )
                ORDER BY object_id, metric
                """,
                (analysis_id, analysis_id, community_id),
            ).fetchall()
            annotation_row = connection.execute(
                """
                SELECT * FROM annotations
                WHERE analysis_id = ? AND community_id = ?
                """,
                (analysis_id, community_id),
            ).fetchone()
        centrality: dict[str, dict[str, float]] = {}
        for row in centrality_rows:
            centrality.setdefault(row["object_id"], {})[row["metric"]] = row["value"]
        return {
            "metrics": json.loads(metrics_row["metrics_json"]),
            "nodes": [
                GraphNode.from_row(row).to_api() | {"centrality": centrality.get(row["id"], {})}
                for row in node_rows
            ],
            "annotation": self.annotation(annotation_row["id"]) if annotation_row else None,
        }

    def community_graph(self, analysis_id: str) -> dict[str, Any]:
        communities = self.communities(analysis_id)
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT * FROM community_edges
                WHERE analysis_id = ? ORDER BY source_community, target_community
                """,
                (analysis_id,),
            ).fetchall()
        return {
            "nodes": communities,
            "edges": [
                {
                    "sourceCommunity": row["source_community"],
                    "targetCommunity": row["target_community"],
                    "edgeCount": row["edge_count"],
                    "totalWeight": row["total_weight"],
                    **json.loads(row["metadata_json"]),
                }
                for row in rows
            ],
        }

    @staticmethod
    def _hierarchy_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "hierarchyId": row["hierarchy_id"],
            "parentId": row["parent_id"],
            "level": row["level"],
            "resolution": row["resolution"],
            "splitResolution": row["split_resolution"],
            "splitQuality": row["split_quality"],
            "nodeCount": row["node_count"],
            "stopReason": row["stop_reason"],
            "metrics": json.loads(row["metrics_json"]),
        }

    def hierarchy(self, analysis_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT * FROM analysis_hierarchy
                WHERE analysis_id = ? ORDER BY level, hierarchy_id
                """,
                (analysis_id,),
            ).fetchall()
            run = connection.execute(
                "SELECT result_summary_json FROM analysis_runs WHERE id = ?",
                (analysis_id,),
            ).fetchone()
        summary = json.loads(run["result_summary_json"]) if run and run["result_summary_json"] else {}
        hierarchy_summary = summary.get("hierarchy")
        if not rows and hierarchy_summary is None:
            return None
        items = {
            row["hierarchy_id"]: self._hierarchy_row(row) | {"children": []}
            for row in rows
        }
        roots = []
        for item in items.values():
            parent_id = item["parentId"]
            if parent_id is None:
                roots.append(item)
            else:
                items[parent_id]["children"].append(item)
        for item in items.values():
            item["children"].sort(key=lambda child: child["hierarchyId"])
            item["childrenCount"] = len(item["children"])
        return {
            "analysisId": analysis_id,
            "experimental": True,
            "summary": hierarchy_summary,
            "roots": sorted(roots, key=lambda item: item["hierarchyId"]),
        }

    def hierarchy_node(self, analysis_id: str, hierarchy_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM analysis_hierarchy
                WHERE analysis_id = ? AND hierarchy_id = ?
                """,
                (analysis_id, hierarchy_id),
            ).fetchone()
            if row is None:
                return None
            object_rows = connection.execute(
                """
                SELECT objects.*
                FROM analysis_hierarchy_membership membership
                JOIN objects ON objects.id = membership.object_id
                WHERE membership.analysis_id = ?
                  AND (
                    membership.hierarchy_id = ?
                    OR membership.hierarchy_id LIKE ?
                  )
                ORDER BY objects.owner, objects.name, objects.object_type, objects.id
                """,
                (analysis_id, hierarchy_id, f"{hierarchy_id}.%"),
            ).fetchall()
        return self._hierarchy_row(row) | {
            "objects": [GraphNode.from_row(object_row).to_api() for object_row in object_rows]
        }
