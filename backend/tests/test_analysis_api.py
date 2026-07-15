import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.analysis.models import AnalysisConfig, AnalysisResult
from app.persistence.analysis_repository import AnalysisRepository
from app.persistence.database import initialize_database
from app.analysis.service import AnalysisCancelled


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
