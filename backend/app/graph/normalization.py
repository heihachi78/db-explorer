import json
from datetime import date, datetime
from typing import Any


OBJECT_TYPE_MAP = {
    "TABLE": "TABLE",
    "VIEW": "VIEW",
    "MATERIALIZED VIEW": "MATERIALIZED_VIEW",
    "PACKAGE": "PACKAGE",
    "PACKAGE BODY": "PACKAGE_BODY",
    "PROCEDURE": "PROCEDURE",
    "FUNCTION": "FUNCTION",
    "TRIGGER": "TRIGGER",
    "TYPE": "TYPE",
    "TYPE BODY": "TYPE_BODY",
    "INDEX": "INDEX",
    "SYNONYM": "SYNONYM",
    "SEQUENCE": "SEQUENCE",
    "DATABASE LINK": "DB_LINK",
}


def normalize_object_type(oracle_object_type: str | None) -> str:
    """Map Oracle's type labels without discarding unknown catalog objects."""
    if not oracle_object_type:
        return "EXTERNAL_OBJECT"
    return OBJECT_TYPE_MAP.get(oracle_object_type, "OTHER")


def _id_component(value: str) -> str:
    # Keep ordinary identifiers readable while preventing quoted identifiers
    # containing the contract separator from creating collisions.
    return value.replace("%", "%25").replace("::", "%3A%3A")


def stable_object_id(
    database_key: str,
    container_key: str,
    owner: str,
    object_type: str,
    name: str,
    subobject_name: str | None = None,
) -> str:
    parts = (database_key, container_key, owner, object_type, name)
    identifier = "::".join(_id_component(part) for part in parts)
    if subobject_name:
        identifier += f"::{_id_component(subobject_name)}"
    return identifier


def iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

