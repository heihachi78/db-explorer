import sqlite3
import threading
import time
import json
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.analysis.models import AnalysisConfig, AnalysisResult
from app.persistence.analysis_repository import AnalysisRepository
from app.persistence.database import initialize_database
from app.analysis.service import AnalysisCancelled, AnalysisService
from app.errors import AppError
from app.persistence.graph_repository import GraphRepository


def _seed_two_communities(path: Path) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO objects (
                id, database_key, container_key, owner, name, object_type,
                oracle_object_type, status, is_external, metadata_json
            ) VALUES (?, 'db', 'pdb', ?, ?, 'TABLE', 'TABLE', 'VALID', 0, '{}')
            """,
            [
                (name, "SALES" if name < "D" else "BILLING", name)
                for name in "ABCDEF"
            ],
        )
        connection.executemany(
            """
            INSERT INTO relationships (
                id, source_id, target_id, relationship_type, directed,
                confidence, origin, metadata_json
            ) VALUES (?, ?, ?, ?, 1, ?, 'TEST', '{}')
            """,
            [
                ("ab", "A", "B", "DEPENDS_ON", 1.0),
                ("ac", "A", "C", "DEPENDS_ON", 1.0),
                ("bc", "B", "C", "DEPENDS_ON", 1.0),
                ("de", "D", "E", "DEPENDS_ON", 1.0),
                ("df", "D", "F", "DEPENDS_ON", 1.0),
                ("ef", "E", "F", "DEPENDS_ON", 1.0),
                ("cd", "C", "D", "POINTS_TO", 0.1),
            ],
        )
        connection.commit()


def _wait_for_analysis(client: TestClient, analysis_id: str) -> dict:
    for _ in range(200):
        run = client.get(f"/api/analyses/{analysis_id}").json()
        if run["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        time.sleep(0.01)
    raise AssertionError("Analysis did not finish in time")


def _wait_for_export(client: TestClient, export_id: str) -> dict:
    for _ in range(200):
        job = client.get(f"/api/export/{export_id}/status").json()
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Export did not finish in time")


def test_analysis_api_runs_persists_and_exposes_communities(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        started = client.post("/api/analyses", json={
            "name": "Two domains",
            "minimumConfidence": 0,
            "hubPolicy": "NONE",
            "seed": 42,
        })
        assert started.status_code == 202
        analysis_id = started.json()["analysisId"]
        run = _wait_for_analysis(client, analysis_id)
        communities = client.get(f"/api/analyses/{analysis_id}/communities")
        community_graph = client.get(f"/api/analyses/{analysis_id}/community-graph")
        detail = client.get(
            f"/api/analyses/{analysis_id}/communities/"
            f"{communities.json()['items'][0]['communityId']}"
        )

    assert run["status"] == "SUCCEEDED", run["errorMessage"]
    assert run["config"]["igraphVersion"]
    assert run["summary"]["communityCount"] == 2
    assert communities.status_code == 200
    assert sorted(item["nodeCount"] for item in communities.json()["items"]) == [3, 3]
    assert len(community_graph.json()["edges"]) == 1
    assert len(detail.json()["nodes"]) == 3
    assert "PAGERANK" in detail.json()["nodes"][0]["centrality"]


def test_analysis_estimate_and_preflight_limit_rejection(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path, analysis_max_nodes=5, analysis_max_edges=100)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        estimate = client.post("/api/analyses/estimate", json={
            "minimumConfidence": 0, "hubPolicy": "NONE",
        })
        rejected = client.post("/api/analyses", json={
            "minimumConfidence": 0, "hubPolicy": "NONE",
        })
        runs = client.get("/api/analyses").json()["items"]

    assert estimate.status_code == 200
    assert estimate.json()["estimatedNodeCount"] == 6
    assert estimate.json()["estimatedRelationshipCount"] == 7
    assert estimate.json()["sizeCategory"] == "SMALL"
    assert estimate.json()["estimatedMemoryBytes"] > 0
    assert estimate.json()["withinLimits"] is False
    assert rejected.status_code == 413
    assert rejected.json()["code"] == "ANALYSIS_TOO_LARGE"
    assert runs == []


def test_experimental_hierarchy_is_persisted_and_queryable(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        started = client.post("/api/analyses/hierarchy", json={
            "name": "Domain hierarchy", "resolution": 0.01,
            "minimumConfidence": 0, "hubPolicy": "NONE",
            "hierarchyChildResolution": 4,
            "hierarchyMinimumSize": 2, "hierarchyMaxDepth": 1,
            "hierarchyResolutionOverrides": {"0": 4.5, "99": 2},
        })
        assert started.status_code == 202
        analysis_id = started.json()["analysisId"]
        run = _wait_for_analysis(client, analysis_id)
        hierarchy = client.get(f"/api/analyses/{analysis_id}/hierarchy")
        root_id = hierarchy.json()["roots"][0]["hierarchyId"]
        detail = client.get(f"/api/analyses/{analysis_id}/hierarchy/{root_id}")
        json_export = client.post("/api/export", json={
            "analysisId": analysis_id, "format": "JSON",
        })
        json_job = _wait_for_export(client, json_export.json()["exportId"])
        json_payload = client.get(json_job["downloadUrl"]).json()
        csv_export = client.post("/api/export", json={
            "analysisId": analysis_id, "format": "CSV",
        })
        csv_job = _wait_for_export(client, csv_export.json()["exportId"])
        csv_payload = client.get(csv_job["downloadUrl"]).content
        invalid = client.post("/api/analyses/hierarchy", json={
            "hierarchyResolutionOverrides": {"invalid-path": 2},
        })

    assert run["status"] == "SUCCEEDED", run["errorMessage"]
    assert run["config"]["hierarchyEnabled"] is True
    assert run["summary"]["hierarchy"]["experimental"] is True
    assert hierarchy.status_code == 200
    assert hierarchy.json()["summary"]["maximumDepthReached"] == 1
    assert hierarchy.json()["summary"]["unusedResolutionOverrideIds"] == ["99"]
    assert hierarchy.json()["roots"][0]["childrenCount"] > 0
    assert detail.status_code == 200
    assert detail.json()["nodeCount"] == len(detail.json()["objects"])
    assert json_payload["hierarchyNodes"]
    assert len(json_payload["hierarchyMemberships"]) == 6
    with zipfile.ZipFile(BytesIO(csv_payload)) as archive:
        assert "hierarchy.csv" in archive.namelist()
        assert "hierarchy_memberships.csv" in archive.namelist()
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_hierarchy_exposes_an_empty_tree_for_an_isolated_graph(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    initialize_database(settings.database_path)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO objects (
                id, database_key, container_key, owner, name, object_type,
                oracle_object_type, status, is_external, metadata_json
            ) VALUES ('isolated', 'db', 'pdb', 'APP', 'ISOLATED',
                      'TABLE', 'TABLE', 'VALID', 0, '{}')
            """
        )
        connection.commit()

    with TestClient(create_app(settings)) as client:
        started = client.post("/api/analyses/hierarchy", json={
            "minimumConfidence": 0, "hubPolicy": "NONE",
        })
        analysis_id = started.json()["analysisId"]
        run = _wait_for_analysis(client, analysis_id)
        hierarchy = client.get(f"/api/analyses/{analysis_id}/hierarchy")
        csv_export = client.post("/api/export", json={
            "analysisId": analysis_id, "format": "CSV",
        })
        csv_job = _wait_for_export(client, csv_export.json()["exportId"])
        csv_payload = client.get(csv_job["downloadUrl"]).content

    assert run["status"] == "SUCCEEDED", run["errorMessage"]
    assert hierarchy.status_code == 200
    assert hierarchy.json()["roots"] == []
    assert hierarchy.json()["summary"]["hierarchyNodeCount"] == 0
    with zipfile.ZipFile(BytesIO(csv_payload)) as archive:
        assert "hierarchy.csv" in archive.namelist()
        assert "hierarchy_memberships.csv" in archive.namelist()


def test_analysis_service_translates_memory_exhaustion(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)
    repository = AnalysisRepository(settings.database_path)
    repository.create("memory", AnalysisConfig(name="Memory"))
    service = AnalysisService(GraphRepository(settings.database_path), repository)

    with patch("app.analysis.service.build_analysis_graph", side_effect=MemoryError):
        with pytest.raises(AppError) as raised:
            service.run("memory", AnalysisConfig(name="Memory"), lambda *_args, **_kwargs: None, threading.Event())

    assert raised.value.code == "ANALYSIS_MEMORY_EXHAUSTED"
    assert raised.value.status_code == 507


def test_analysis_comparison_validation_and_delete(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        ids = []
        for resolution in (0.5, 2.0):
            response = client.post("/api/analyses", json={
                "name": f"Resolution {resolution}",
                "resolution": resolution,
                "minimumConfidence": 0,
                "hubPolicy": "NONE",
            })
            analysis_id = response.json()["analysisId"]
            assert _wait_for_analysis(client, analysis_id)["status"] == "SUCCEEDED"
            ids.append(analysis_id)

        comparison = client.post("/api/analyses/compare", json={"analysisIds": ids})
        deleted = client.delete(f"/api/analyses/{ids[0]}")
        missing = client.get(f"/api/analyses/{ids[0]}")
        invalid = client.post("/api/analyses", json={"iterations": 0})

    assert comparison.status_code == 200
    assert [item["config"]["resolution"] for item in comparison.json()["items"]] == [0.5, 2.0]
    assert deleted.json() == {"deleted": True}
    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_resolution_profile_runs_as_one_serial_long_operation(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        response = client.post("/api/analyses/resolution-profile", json={
            "name": "Resolution sweep",
            "resolutions": [0.5, 1.0, 2.0],
            "minimumConfidence": 0,
            "hubPolicy": "NONE",
        })
        assert response.status_code == 202
        analysis_ids = response.json()["analysisIds"]
        runs = [_wait_for_analysis(client, analysis_id) for analysis_id in analysis_ids]

    assert len(runs) == 3
    assert all(run["status"] == "SUCCEEDED" for run in runs)
    assert [run["config"]["resolution"] for run in runs] == [0.5, 1.0, 2.0]
    assert [run["name"] for run in runs] == [
        "Resolution sweep · r=0.5",
        "Resolution sweep · r=1",
        "Resolution sweep · r=2",
    ]


def test_startup_recovers_interrupted_analysis_runs(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)
    repository = AnalysisRepository(settings.database_path)
    repository.create("stale", AnalysisConfig(name="Interrupted"))
    repository.mark_running("stale")

    with TestClient(create_app(settings)) as client:
        run = client.get("/api/analyses/stale").json()

    assert run["status"] == "CANCELLED"
    assert "stopped" in run["errorMessage"]


def test_cancelled_run_cannot_commit_results(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)
    repository = AnalysisRepository(settings.database_path)
    repository.create("cancelled", AnalysisConfig(name="Cancelled"))
    assert repository.mark_running("cancelled")
    repository.mark_terminal("cancelled", "CANCELLED")

    saved = repository.save_success(
        "cancelled",
        AnalysisResult({}, {}, [], [], {"communityCount": 0}),
    )

    assert not saved
    assert repository.get("cancelled")["status"] == "CANCELLED"


def test_cancelling_one_profile_run_cancels_the_whole_serial_operation(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    def slow_run(self, analysis_id, _config, _report, cancelled) -> None:
        if not self.analysis_repository.mark_running(analysis_id):
            raise AnalysisCancelled()
        while not cancelled.wait(0.005):
            pass
        raise AnalysisCancelled()

    with patch("app.analysis.service.AnalysisService.run", slow_run):
        with TestClient(create_app(settings)) as client:
            started = client.post("/api/analyses/resolution-profile", json={
                "resolutions": [0.5, 1.0],
            })
            analysis_ids = started.json()["analysisIds"]
            cancelled = client.post(f"/api/analyses/{analysis_ids[0]}/cancel")
            runs = [client.get(f"/api/analyses/{analysis_id}").json() for analysis_id in analysis_ids]

    assert cancelled.status_code == 202
    assert all(run["status"] == "CANCELLED" for run in runs)


def test_seed_profile_persists_stability_and_comparison_scores(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        started = client.post("/api/analyses/seed-profile", json={
            "name": "Stable domains", "seeds": [42, 43],
            "minimumConfidence": 0, "hubPolicy": "NONE",
        })
        assert started.status_code == 202
        analysis_ids = started.json()["analysisIds"]
        runs = [_wait_for_analysis(client, analysis_id) for analysis_id in analysis_ids]
        baseline_id = started.json()["baselineAnalysisId"]
        for _ in range(200):
            baseline = client.get(f"/api/analyses/{baseline_id}").json()
            if baseline["summary"].get("stability"):
                break
            time.sleep(0.01)
        comparison = client.post("/api/analyses/compare", json={"analysisIds": analysis_ids})
        communities = client.get(f"/api/analyses/{baseline_id}/communities").json()["items"]

    assert all(run["status"] == "SUCCEEDED" for run in runs)
    assert baseline["summary"]["stability"]["sharedNodeCount"] == 6
    assert comparison.status_code == 200
    assert comparison.json()["agreement"]["pairwise"][0]["adjustedRandIndex"] == 1.0
    assert all(item["stability"] in {"STABLE", "MIXED", "UNSTABLE"} for item in communities)


def test_annotations_are_upserted_and_exposed_in_community_views(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        started = client.post("/api/analyses", json={
            "minimumConfidence": 0, "hubPolicy": "NONE",
        })
        analysis_id = started.json()["analysisId"]
        assert _wait_for_analysis(client, analysis_id)["status"] == "SUCCEEDED"
        community_id = client.get(f"/api/analyses/{analysis_id}/communities").json()["items"][0]["communityId"]
        created = client.post("/api/annotations", json={
            "analysisId": analysis_id, "communityId": community_id,
            "name": "Order domain", "note": "Verified by the analyst.",
        })
        updated = client.patch(f"/api/annotations/{created.json()['id']}", json={
            "name": "Sales order domain",
        })
        communities = client.get(f"/api/analyses/{analysis_id}/communities").json()["items"]
        detail = client.get(f"/api/analyses/{analysis_id}/communities/{community_id}").json()

    assert created.status_code == 200
    assert updated.json()["name"] == "Sales order domain"
    assert updated.json()["note"] == "Verified by the analyst."
    assert communities[0]["annotation"]["name"] == "Sales order domain"
    assert detail["annotation"]["note"] == "Verified by the analyst."


def test_deterministic_json_csv_svg_and_png_exports(tmp_path: Path) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed_two_communities(settings.database_path)

    with TestClient(create_app(settings)) as client:
        analysis_id = client.post("/api/analyses", json={
            "name": "Exportálható – közösség", "minimumConfidence": 0, "hubPolicy": "NONE",
        }).json()["analysisId"]
        assert _wait_for_analysis(client, analysis_id)["status"] == "SUCCEEDED"
        downloads = {}
        for export_format in ("JSON", "CSV", "SVG", "PNG", "JSON"):
            started = client.post("/api/export", json={
                "analysisId": analysis_id, "format": export_format,
            })
            assert started.status_code == 202
            job = _wait_for_export(client, started.json()["exportId"])
            assert job["status"] == "SUCCEEDED", job["errorMessage"]
            response = client.get(job["downloadUrl"])
            assert response.status_code == 200
            downloads.setdefault(export_format, []).append(response.content)

    payload = json.loads(downloads["JSON"][0])
    assert payload["analysis"]["config"]["minimumConfidence"] == 0
    assert len(payload["nodes"]) == 6
    assert downloads["JSON"][0] == downloads["JSON"][1]
    with zipfile.ZipFile(BytesIO(downloads["CSV"][0])) as archive:
        assert archive.namelist() == [
            "objects.csv", "relationships.csv", "memberships.csv",
            "community_metrics.csv", "centrality.csv", "analysis.json",
        ]
    assert downloads["SVG"][0].startswith(b"<svg")
    assert downloads["PNG"][0].startswith(b"\x89PNG\r\n\x1a\n")
