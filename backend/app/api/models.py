from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.analysis.models import DEFAULT_EDGE_WEIGHTS, DEFAULT_OBJECT_TYPES


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


class AnalysisRequest(BaseModel):
    name: str = Field(default="Leiden elemzés", min_length=1, max_length=200)
    algorithm: Literal["LEIDEN"] = "LEIDEN"
    objective: Literal["CPM", "MODULARITY"] = "CPM"
    resolution: float = Field(default=1.0, gt=0, le=100)
    seed: int = 42
    iterations: int = Field(default=-1, ge=-1, le=100)
    objectTypes: list[str] = Field(default_factory=lambda: list(DEFAULT_OBJECT_TYPES))
    owners: list[str] = Field(default_factory=list)
    minimumConfidence: float = Field(default=0.8, ge=0, le=1)
    minimumCommunitySize: int = Field(default=3, ge=1, le=10_000)
    edgeWeights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_EDGE_WEIGHTS))
    parallelEdgeAggregation: Literal["TYPE_MAX_THEN_CAPPED_SUM"] = "TYPE_MAX_THEN_CAPPED_SUM"
    parallelEdgeWeightCap: float = Field(default=10.0, gt=0, le=1_000)
    hubPolicy: Literal["NONE", "DEGREE_NORMALIZATION", "EXCLUDE_TOP_HUBS"] = "DEGREE_NORMALIZATION"
    directionPolicy: Literal["SYMMETRIZE_SUM"] = "SYMMETRIZE_SUM"
    includeTechnicalObjects: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Az elemzés neve nem lehet üres.")
        return cleaned

    @field_validator("objectTypes", "owners")
    @classmethod
    def unique_analysis_filters(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("iterations")
    @classmethod
    def valid_iterations(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Az iterációszám -1 vagy pozitív egész lehet.")
        return value

    @field_validator("edgeWeights")
    @classmethod
    def valid_analysis_weights(cls, values: dict[str, float]) -> dict[str, float]:
        if any(value <= 0 for value in values.values()):
            raise ValueError("Minden élsúlynak pozitívnak kell lennie.")
        return values


class AnalysisCompareRequest(BaseModel):
    analysisIds: list[str] = Field(min_length=2, max_length=10)

    @field_validator("analysisIds")
    @classmethod
    def unique_analysis_ids(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if len(cleaned) < 2:
            raise ValueError("Legalább két különböző elemzés szükséges.")
        return cleaned


class ResolutionProfileRequest(AnalysisRequest):
    resolutions: list[float] = Field(
        default_factory=lambda: [0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
        min_length=2,
        max_length=12,
    )

    @field_validator("resolutions")
    @classmethod
    def valid_resolutions(cls, values: list[float]) -> list[float]:
        if any(value <= 0 or value > 100 for value in values):
            raise ValueError("A resolution értékeknek 0 és 100 között kell lenniük.")
        cleaned = list(dict.fromkeys(values))
        if len(cleaned) < 2:
            raise ValueError("Legalább két különböző resolution érték szükséges.")
        return cleaned
