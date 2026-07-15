from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.graph.models import GraphEdge, GraphNode

from .database import database


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ExportRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def create(self, export_id: str, analysis_id: str, export_format: str) -> None:
        with database(self.path) as connection:
            connection.execute(
                """
                INSERT INTO export_jobs (
                    id, analysis_id, format, status, created_at
                ) VALUES (?, ?, ?, 'QUEUED', ?)
                """,
                (export_id, analysis_id, export_format, _now()),
            )
            connection.commit()

    def mark_running(self, export_id: str) -> bool:
        with database(self.path) as connection:
            cursor = connection.execute(
                "UPDATE export_jobs SET status = 'RUNNING' WHERE id = ? AND status = 'QUEUED'",
                (export_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def mark_success(
        self,
        export_id: str,
        *,
        filename: str,
        content_type: str,
        file_path: Path,
    ) -> bool:
        with database(self.path) as connection:
            cursor = connection.execute(
                """
                UPDATE export_jobs
                SET status = 'SUCCEEDED', filename = ?, content_type = ?,
                    file_path = ?, finished_at = ?
                WHERE id = ? AND status = 'RUNNING'
                """,
                (filename, content_type, str(file_path), _now(), export_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    def mark_terminal(self, export_id: str, status: str, error_message: str | None = None) -> None:
        with database(self.path) as connection:
            connection.execute(
                """
                UPDATE export_jobs SET status = ?, error_message = ?, finished_at = ?
                WHERE id = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (status, error_message, _now(), export_id),
            )
            connection.commit()

    def recover_interrupted(self) -> int:
        with database(self.path) as connection:
            cursor = connection.execute(
                """
                UPDATE export_jobs SET status = 'FAILED',
                    error_message = 'Application stopped before the export completed.',
                    finished_at = ?
                WHERE status IN ('QUEUED', 'RUNNING')
                """,
                (_now(),),
            )
            connection.commit()
        return cursor.rowcount

    def cleanup_files(self, export_dir: Path) -> int:
        export_dir.mkdir(parents=True, exist_ok=True)
        with database(self.path, read_only=True) as connection:
            referenced = {
                Path(row["file_path"]).resolve()
                for row in connection.execute(
                    """
                    SELECT file_path FROM export_jobs
                    WHERE status = 'SUCCEEDED' AND file_path IS NOT NULL
                    """
                ).fetchall()
            }
        removed = 0
        for path in export_dir.iterdir():
            if path.is_file() and path.resolve() not in referenced:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def files_for_analysis(self, analysis_id: str) -> list[Path]:
        with database(self.path, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT file_path FROM export_jobs
                WHERE analysis_id = ? AND file_path IS NOT NULL
                """,
                (analysis_id,),
            ).fetchall()
        return [Path(row["file_path"]) for row in rows]

    @staticmethod
    def _to_api(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "analysisId": row["analysis_id"],
            "format": row["format"],
            "status": row["status"],
            "filename": row["filename"],
            "contentType": row["content_type"],
            "errorMessage": row["error_message"],
            "createdAt": row["created_at"],
            "finishedAt": row["finished_at"],
            "downloadUrl": f"/api/export/{row['id']}/file" if row["status"] == "SUCCEEDED" else None,
        }

    def get(self, export_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM export_jobs WHERE id = ?", (export_id,)
            ).fetchone()
        return self._to_api(row) if row else None

    def file_details(self, export_id: str) -> tuple[Path, str, str] | None:
        with database(self.path, read_only=True) as connection:
            row = connection.execute(
                """
                SELECT file_path, content_type, filename FROM export_jobs
                WHERE id = ? AND status = 'SUCCEEDED'
                """,
                (export_id,),
            ).fetchone()
        if row is None or not row["file_path"]:
            return None
        return Path(row["file_path"]), row["content_type"], row["filename"]

    def snapshot(self, analysis_id: str) -> dict[str, Any] | None:
        with database(self.path, read_only=True) as connection:
            run = connection.execute(
                "SELECT * FROM analysis_runs WHERE id = ? AND status = 'SUCCEEDED'",
                (analysis_id,),
            ).fetchone()
            if run is None:
                return None
            membership_rows = connection.execute(
                """
                SELECT am.object_id, am.community_id, am.stability, o.*
                FROM analysis_membership am JOIN objects o ON o.id = am.object_id
                WHERE am.analysis_id = ? ORDER BY am.object_id
                """,
                (analysis_id,),
            ).fetchall()
            relationship_rows = connection.execute(
                """
                SELECT r.* FROM relationships r
                JOIN analysis_membership source_membership
                  ON source_membership.analysis_id = ?
                 AND source_membership.object_id = r.source_id
                JOIN analysis_membership target_membership
                  ON target_membership.analysis_id = ?
                 AND target_membership.object_id = r.target_id
                ORDER BY r.id
                """,
                (analysis_id, analysis_id),
            ).fetchall()
            metric_rows = connection.execute(
                """
                SELECT community_id, metrics_json FROM community_metrics
                WHERE analysis_id = ? ORDER BY community_id
                """,
                (analysis_id,),
            ).fetchall()
            centrality_rows = connection.execute(
                """
                SELECT object_id, metric, value, metadata_json
                FROM centrality_results WHERE analysis_id = ?
                ORDER BY object_id, metric
                """,
                (analysis_id,),
            ).fetchall()
            community_edge_rows = connection.execute(
                """
                SELECT * FROM community_edges WHERE analysis_id = ?
                ORDER BY source_community, target_community
                """,
                (analysis_id,),
            ).fetchall()
            annotation_rows = connection.execute(
                """
                SELECT id, community_id, name, note, created_at, updated_at
                FROM annotations WHERE analysis_id = ? ORDER BY community_id
                """,
                (analysis_id,),
            ).fetchall()
            hierarchy_rows = connection.execute(
                """
                SELECT * FROM analysis_hierarchy
                WHERE analysis_id = ? ORDER BY level, hierarchy_id
                """,
                (analysis_id,),
            ).fetchall()
            hierarchy_membership_rows = connection.execute(
                """
                SELECT hierarchy_id, object_id
                FROM analysis_hierarchy_membership
                WHERE analysis_id = ? ORDER BY hierarchy_id, object_id
                """,
                (analysis_id,),
            ).fetchall()
        return {
            "analysis": {
                "id": run["id"], "name": run["name"], "algorithm": run["algorithm"],
                "config": json.loads(run["config_json"]),
                "summary": json.loads(run["result_summary_json"]),
                "createdAt": run["created_at"], "finishedAt": run["finished_at"],
            },
            "nodes": [GraphNode.from_row(row).to_api() for row in membership_rows],
            "relationships": [GraphEdge.from_row(row).to_api() for row in relationship_rows],
            "memberships": [
                {
                    "objectId": row["object_id"],
                    "communityId": row["community_id"],
                    "stability": row["stability"],
                }
                for row in membership_rows
            ],
            "communityMetrics": [json.loads(row["metrics_json"]) for row in metric_rows],
            "communityEdges": [
                {
                    "sourceCommunity": row["source_community"],
                    "targetCommunity": row["target_community"],
                    "edgeCount": row["edge_count"],
                    "totalWeight": row["total_weight"],
                    **json.loads(row["metadata_json"]),
                }
                for row in community_edge_rows
            ],
            "centrality": [
                {
                    "objectId": row["object_id"], "metric": row["metric"],
                    "value": row["value"], "metadata": json.loads(row["metadata_json"]),
                }
                for row in centrality_rows
            ],
            "annotations": [
                {
                    "id": row["id"], "communityId": row["community_id"],
                    "name": row["name"], "note": row["note"],
                    "createdAt": row["created_at"], "updatedAt": row["updated_at"],
                }
                for row in annotation_rows
            ],
            "hierarchyNodes": [
                {
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
                for row in hierarchy_rows
            ],
            "hierarchyMemberships": [
                {"hierarchyId": row["hierarchy_id"], "objectId": row["object_id"]}
                for row in hierarchy_membership_rows
            ],
        }
