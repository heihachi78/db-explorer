import json
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.persistence.database import initialize_database


def _seed(path: Path) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO objects (
                id, database_key, container_key, owner, name, object_type,
                oracle_object_type, status, is_external, metadata_json
            ) VALUES (?, 'db', 'pdb', ?, ?, 'TABLE', 'TABLE', 'VALID', 0, '{}')
            """,
            [(name, "SALES" if name < "D" else "BILLING", name) for name in "ABCDEF"],
        )
        connection.executemany(
            """
            INSERT INTO relationships (
                id, source_id, target_id, relationship_type, directed,
                confidence, origin, metadata_json
            ) VALUES (?, ?, ?, 'DEPENDS_ON', 1, 1, 'TEST', '{}')
            """,
            [
                ("ab", "A", "B"), ("ac", "A", "C"), ("bc", "B", "C"),
                ("de", "D", "E"), ("df", "D", "F"), ("ef", "E", "F"),
            ],
        )
        connection.execute(
            "INSERT INTO app_meta (key, value_json, updated_at) VALUES ('dataset_id', ?, 'now')",
            (json.dumps("dataset-1"),),
        )
        connection.execute(
            "INSERT INTO app_meta (key, value_json, updated_at) VALUES ('scan_summary', ?, 'now')",
            (json.dumps({"datasetId": "dataset-1", "selectedSchemas": ["SALES", "BILLING"]}),),
        )
        connection.commit()


def _wait(client: TestClient, analysis_id: str) -> dict:
    for _ in range(200):
        run = client.get(f"/api/analyses/{analysis_id}").json()
        if run["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        time.sleep(0.01)
    raise AssertionError("Analysis did not finish in time")


def test_named_subgraph_scopes_analysis_and_supports_recursive_community_workflow(
    tmp_path: Path,
) -> None:
    settings = Settings(app_data_dir=tmp_path)
    _seed(settings.database_path)

    with TestClient(create_app(settings)) as client:
        created = client.post("/api/subgraphs", json={
            "name": "Sales domain", "objectIds": ["A", "B", "C"],
        })
        assert created.status_code == 200
        scope = created.json()
        graph = client.get(f"/api/subgraphs/{scope['id']}/graph")
        estimate = client.post("/api/analyses/estimate", json={
            "subgraphId": scope["id"], "minimumConfidence": 0, "hubPolicy": "NONE",
        })
        started = client.post("/api/analyses", json={
            "name": "Sales communities", "subgraphId": scope["id"],
            "minimumConfidence": 0, "hubPolicy": "NONE", "seed": 42,
        })
        run = _wait(client, started.json()["analysisId"])
        communities = client.get(f"/api/analyses/{run['id']}/communities").json()["items"]
        community_id = communities[0]["communityId"]
        objects = client.get(
            f"/api/analyses/{run['id']}/communities/{community_id}/objects",
            params={"q": "A", "owner": "SALES"},
        )
        community_graph = client.get(
            f"/api/analyses/{run['id']}/communities/{community_id}/subgraph"
        )
        child = client.post("/api/subgraphs/from-community", json={
            "name": "Sales core", "analysisId": run["id"],
            "communityId": community_id, "parentId": scope["id"],
        })

    assert scope["nodeCount"] == 3
    assert scope["edgeCount"] == 3
    assert {node["id"] for node in graph.json()["nodes"]} == {"A", "B", "C"}
    assert estimate.json()["estimatedNodeCount"] == 3
    assert estimate.json()["sourceNodeCount"] == 3
    assert run["status"] == "SUCCEEDED", run["errorMessage"]
    assert run["config"]["subgraphId"] == scope["id"]
    assert objects.status_code == 200
    assert all(item["owner"] == "SALES" for item in objects.json()["items"])
    assert community_graph.status_code == 200
    assert child.status_code == 200
    assert child.json()["parentId"] == scope["id"]
    assert child.json()["sourceKind"] == "COMMUNITY"


def test_workspace_reset_atomically_clears_scan_graph_analysis_and_exports(
    tmp_path: Path,
) -> None:
    settings = Settings(
        app_data_dir=tmp_path,
        oracle_user="reader", oracle_password="secret", oracle_dsn="example.invalid/db",
    )
    _seed(settings.database_path)
    settings.export_dir.mkdir(parents=True)
    (settings.export_dir / "old-export.json").write_text("{}", encoding="utf-8")

    with TestClient(create_app(settings)) as client:
        client.post("/api/subgraphs", json={"name": "Old", "objectIds": ["A", "B"]})
        blocked = client.post("/api/scan", json={"schemas": ["SALES"]})
        reset = client.post("/api/workspace/reset")
        summary = client.get("/api/scan/summary")
        subgraphs = client.get("/api/subgraphs")
        analyses = client.get("/api/analyses")
        config = client.get("/api/config")

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "WORKSPACE_RESET_REQUIRED"
    assert reset.status_code == 200
    assert summary.json() == {"available": False, "summary": None}
    assert subgraphs.json()["items"] == []
    assert analyses.json()["items"] == []
    assert config.json()["datasetId"] is None
    assert config.json()["resetRequired"] is False
    assert not (settings.export_dir / "old-export.json").exists()
