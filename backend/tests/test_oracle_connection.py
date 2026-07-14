import socket

import pytest

from app.errors import AppError
from app.oracle.connection import OracleCredentials, connect_read_only


def test_dns_failure_becomes_structured_network_error(monkeypatch) -> None:
    def fail_to_connect(**_):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr("app.oracle.connection.oracledb.connect", fail_to_connect)
    credentials = OracleCredentials(
        user="reader",
        password="secret",
        dsn="unknown-host:1521/ORCL",
        mode="thin",
    )

    with pytest.raises(AppError) as captured:
        connect_read_only(credentials)

    assert captured.value.code == "ORACLE_NETWORK_ERROR"
    assert captured.value.status_code == 502
    assert "secret" not in str(captured.value.details)
    assert "host.docker.internal" in captured.value.details["hint"]
