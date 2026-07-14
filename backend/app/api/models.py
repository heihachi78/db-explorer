from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PublicConfig(BaseModel):
    oracleConfigured: bool
    oracleMode: str
    dataFilePresent: bool
    activeOperation: bool
    limits: dict[str, int]


class ConnectionTestResponse(BaseModel):
    success: bool = True
    capabilities: dict[str, Any]


class ScanRequest(BaseModel):
    schemas: list[str] = Field(min_length=1)
    objectTypes: list[str] = Field(default_factory=list)
    includeSourceCode: bool = False
    resolveExternalReferences: bool = True
    includeSchedulerObjects: bool = False

    @field_validator("schemas", "objectTypes")
    @classmethod
    def clean_unique_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) != len(set(cleaned)):
            cleaned = list(dict.fromkeys(cleaned))
        return cleaned


GraphDirection = Literal["INCOMING", "OUTGOING", "BOTH"]


class SubgraphRequest(BaseModel):
    rootObjectIds: list[str] = Field(min_length=1, max_length=50)
    depth: int = Field(default=1, ge=0, le=3)
    direction: GraphDirection = "BOTH"
    relationshipTypes: list[str] = Field(default_factory=list)
    minimumConfidence: float = Field(default=0.0, ge=0.0, le=1.0)
    includeExternal: bool = True
    maxNodes: int = Field(default=500, ge=1, le=2_000)
    maxEdges: int = Field(default=2_000, ge=0, le=10_000)

    @field_validator("rootObjectIds", "relationshipTypes")
    @classmethod
    def unique_non_empty_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ImpactRequest(BaseModel):
    objectId: str = Field(min_length=1)
    mode: Literal["DEPENDENTS", "DEPENDENCIES"] = "DEPENDENTS"
    maxDepth: int = Field(default=5, ge=1, le=20)
    relationshipTypes: list[str] = Field(default_factory=list)
    minimumConfidence: float = Field(default=0.0, ge=0.0, le=1.0)
    includeExternal: bool = True
    maxNodes: int = Field(default=500, ge=1, le=2_000)
    maxEdges: int = Field(default=2_000, ge=0, le=10_000)

    @field_validator("relationshipTypes")
    @classmethod
    def unique_relationship_types(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class PathsRequest(BaseModel):
    sourceId: str = Field(min_length=1)
    targetId: str = Field(min_length=1)
    mode: Literal["HOPS", "WEIGHTED"] = "HOPS"
    directed: bool = True
    maxPaths: int = Field(default=1, ge=1, le=3)
    maxDepth: int = Field(default=12, ge=1, le=30)
    relationshipTypes: list[str] = Field(default_factory=list)
    minimumConfidence: float = Field(default=0.0, ge=0.0, le=1.0)
    edgeWeights: dict[str, float] = Field(default_factory=dict)
    maxExpandedNodes: int = Field(default=2_000, ge=1, le=10_000)

    @field_validator("relationshipTypes")
    @classmethod
    def unique_path_relationship_types(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("edgeWeights")
    @classmethod
    def positive_edge_weights(cls, values: dict[str, float]) -> dict[str, float]:
        if any(value <= 0 for value in values.values()):
            raise ValueError("Minden élsúlynak pozitívnak kell lennie.")
        return values
