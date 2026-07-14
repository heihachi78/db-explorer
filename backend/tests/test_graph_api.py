import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.persistence.database import initialize_database


def _seed_graph(path: Path) -> None:
    initialize_database(path)
    objects = [
        ("A", "PACKAGE", "ORDER_API", 0),
        ("B", "TABLE", "ORDERS", 0),
        ("C", "VIEW", "ORDER_VIEW", 0),
        ("X", "EXTERNAL_OBJECT", "CUSTOMERS", 1),
    ]
    relationships = [
        ("ab", "A", "B", "DEPENDS_ON", 1.0),
        ("ca", "C", "A", "DEPENDS_ON", 1.0),
        ("bc", "B", "C", "DEPENDS_ON", 1.0),
        ("cb", "C", "B", "POINTS_TO", 0.5),
        ("bx", "B", "X", "FOREIGN_KEY", 1.0),
    ]
    with sqlite3.connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO objects (
                id, database_key, container_key, owner, name, object_type,
                oracle_object_type, status, is_external, metadata_json
            ) VALUES (?, 'db', 'pdb', ?, ?, ?, ?, 'VALID', ?, '{}')
            """,
            [
                (object_id, "CRM" if external else "SALES", name, object_type,
                 object_type, external)
                for object_id, object_type, name, external in objects
            ],
        )
        connection.executemany(
            """
            INSERT INTO relationships (
                id, source_id, target_id, relationship_type, directed,
                confidence, origin, metadata_json
            ) VALUES (?, ?, ?, ?, 1, ?, 'ORACLE_CATALOG', '{}')
            """,
            relationships,
        )
        connection.execute(
            """
            INSERT INTO relationship_evidence (relationship_id, source_view, evidence_json)
            VALUES ('ab', 'ALL_DEPENDENCIES', ?)
            """,
            (json.dumps({"dependencyType": "HARD"}),),
        )
        connection.execute(
            """
            INSERT INTO object_details (object_id, detail_type, details_json)
            VALUES ('B', 'COLUMNS', ?)
            """,
            (json.dumps([{"name": "ID"}]),),
        )
        connection.commit()


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(app_data_dir=tmp_path)
    _seed_graph(settings.database_path)
    return TestClient(create_app(settings))


def test_object_search_facets_details_and_evidence(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        search = client.get("/api/objects", params={"q": "ORD*", "objectType": "TABLE"})
        details = client.get("/api/objects/B")
        relationship = client.get("/api/relationships/ab")

    assert search.status_code == 200
    assert [item["id"] for item in search.json()["items"]] == ["B"]
    assert search.json()["facets"]["owners"] == {"SALES": 1}
    assert details.json()["details"] == {"COLUMNS": [{"name": "ID"}]}
    assert details.json()["relationshipCounts"] == {"outgoing": 2, "incoming": 2}
    assert relationship.json()["evidence"] == [{
        "sourceView": "ALL_DEPENDENCIES",
        "details": {"dependencyType": "HARD"},
    }]


def test_subgraph_is_directional_filtered_and_truncated(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/subgraph", json={
            "rootObjectIds": ["B"],
            "depth": 2,
            "direction": "INCOMING",
            "relationshipTypes": ["DEPENDS_ON"],
            "maxNodes": 2,
        })

    assert response.status_code == 200
    payload = response.json()
    assert [node["id"] for node in payload["nodes"]] == ["B", "A"]
    assert [edge["id"] for edge in payload["edges"]] == ["ab"]
    assert payload["truncated"] is True
    assert payload["suggestion"]


def test_impact_is_cycle_safe_and_tracks_minimum_depth(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/impact", json={
            "objectId": "B",
            "mode": "DEPENDENTS",
            "maxDepth": 5,
            "relationshipTypes": ["DEPENDS_ON"],
        })

    assert response.status_code == 200
    payload = response.json()
    assert {node["id"]: node["depth"] for node in payload["nodes"]} == {
        "B": 0, "A": 1, "C": 2,
    }
    assert len(payload["edges"]) == 3
    assert payload["estimatedImpact"] is True


def test_hop_and_weighted_path_can_choose_different_routes(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        hops = client.post("/api/paths", json={
            "sourceId": "C", "targetId": "B", "mode": "HOPS",
        })
        weighted = client.post("/api/paths", json={
            "sourceId": "C", "targetId": "B", "mode": "WEIGHTED",
        })

    assert [node["id"] for node in hops.json()["paths"][0]["nodes"]] == ["C", "B"]
    assert [node["id"] for node in weighted.json()["paths"][0]["nodes"]] == ["C", "A", "B"]
    assert weighted.json()["paths"][0]["totalCost"] < 1


def test_graph_api_uses_uniform_not_found_and_validation_errors(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        missing = client.get("/api/objects/missing")
        invalid = client.post("/api/subgraph", json={"rootObjectIds": ["B"], "depth": 4})

    assert missing.status_code == 404
    assert missing.json()["code"] == "OBJECT_NOT_FOUND"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"
