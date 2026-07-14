from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_and_public_config_do_not_expose_secrets(tmp_path: Path) -> None:
    settings = Settings(
        oracle_user="reader",
        oracle_password="very-secret",
        oracle_dsn="db.internal:1521/PROD",
        app_data_dir=tmp_path,
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["oracleConfigured"] is True
    assert "very-secret" not in response.text
    assert "db.internal" not in response.text


def test_connection_test_reports_missing_configuration(tmp_path: Path) -> None:
    settings = Settings(
        oracle_user=None, oracle_password=None, oracle_dsn=None,
        app_data_dir=tmp_path,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/connection/test")

    assert response.status_code == 503
    assert response.json()["code"] == "ORACLE_NOT_CONFIGURED"


def test_scan_requires_oracle_configuration(tmp_path: Path) -> None:
    settings = Settings(
        oracle_user=None, oracle_password=None, oracle_dsn=None,
        app_data_dir=tmp_path,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/scan", json={"schemas": ["SALES"]})

    assert response.status_code == 503
    assert response.json()["code"] == "ORACLE_NOT_CONFIGURED"


def test_scan_endpoint_starts_background_operation(tmp_path: Path) -> None:
    settings = Settings(
        oracle_user="reader", oracle_password="secret", oracle_dsn="test-db",
        app_data_dir=tmp_path,
    )

    def completed_scan(*_args, **_kwargs) -> dict:
        return {}

    with patch("app.oracle.scanner.OracleScanner.run", completed_scan):
        with TestClient(create_app(settings)) as client:
            response = client.post("/api/scan", json={"schemas": ["SALES"]})

            assert response.status_code == 202
            assert response.json() == {"accepted": True}
