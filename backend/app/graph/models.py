import json
from dataclasses import dataclass, field
from typing import Any


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {"value": parsed}


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    database_key: str
    container_key: str
    owner: str
    name: str
    subobject_name: str | None
    object_type: str
    oracle_object_type: str
    status: str | None
    oracle_object_id: int | None
    created_at: str | None
    last_ddl_at: str | None
    is_external: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> "GraphNode":
        return cls(
            id=row["id"],
            database_key=row["database_key"],
            container_key=row["container_key"],
            owner=row["owner"],
            name=row["name"],
            subobject_name=row["subobject_name"],
            object_type=row["object_type"],
            oracle_object_type=row["oracle_object_type"],
            status=row["status"],
            oracle_object_id=row["oracle_object_id"],
            created_at=row["created_at"],
            last_ddl_at=row["last_ddl_at"],
            is_external=bool(row["is_external"]),
            metadata=_json_object(row["metadata_json"]),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "databaseKey": self.database_key,
            "containerKey": self.container_key,
            "owner": self.owner,
            "name": self.name,
            "subobjectName": self.subobject_name,
            "objectType": self.object_type,
            "oracleObjectType": self.oracle_object_type,
            "status": self.status,
            "oracleObjectId": self.oracle_object_id,
            "createdAt": self.created_at,
            "lastDdlAt": self.last_ddl_at,
            "isExternal": self.is_external,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    relationship_type: str
    directed: bool
    confidence: float
    origin: str
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_row(
        cls,
        row: Any,
        evidence: tuple[dict[str, Any], ...] = (),
    ) -> "GraphEdge":
        return cls(
            id=row["id"],
            source=row["source_id"],
            target=row["target_id"],
            relationship_type=row["relationship_type"],
            directed=bool(row["directed"]),
            confidence=float(row["confidence"]),
            origin=row["origin"],
            metadata=_json_object(row["metadata_json"]),
            evidence=evidence,
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relationshipType": self.relationship_type,
            "directed": self.directed,
            "confidence": self.confidence,
            "origin": self.origin,
            "metadata": self.metadata,
            "evidence": list(self.evidence),
        }
