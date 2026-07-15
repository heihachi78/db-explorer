from dataclasses import dataclass, field
from typing import Literal

from app.graph.models import GraphNode


DEFAULT_OBJECT_TYPES = (
    "TABLE", "VIEW", "MATERIALIZED_VIEW", "PACKAGE",
    "PROCEDURE", "FUNCTION", "TRIGGER", "TYPE",
)

TECHNICAL_OBJECT_TYPES = {
    "INDEX", "SYNONYM", "SEQUENCE", "DB_LINK", "OTHER",
}

DEFAULT_EDGE_WEIGHTS = {
    "FOREIGN_KEY": 5.0,
    "TRIGGER_ON": 4.0,
    "DEPENDS_ON": 3.0,
    "POINTS_TO": 1.0,
    "INDEX_ON": 0.5,
}


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    name: str
    algorithm: Literal["LEIDEN"] = "LEIDEN"
    objective: Literal["CPM", "MODULARITY"] = "CPM"
    resolution: float = 1.0
    seed: int = 42
    iterations: int = -1
    object_types: tuple[str, ...] = DEFAULT_OBJECT_TYPES
    owners: tuple[str, ...] = ()
    minimum_confidence: float = 0.8
    minimum_community_size: int = 3
    edge_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_EDGE_WEIGHTS))
    parallel_edge_weight_cap: float = 10.0
    hub_policy: Literal["NONE", "DEGREE_NORMALIZATION", "EXCLUDE_TOP_HUBS"] = "DEGREE_NORMALIZATION"
    direction_policy: Literal["SYMMETRIZE_SUM"] = "SYMMETRIZE_SUM"
    include_technical_objects: bool = False
    hierarchy_enabled: bool = False
    hierarchy_child_resolution: float = 1.0
    hierarchy_minimum_size: int = 20
    hierarchy_max_depth: int = 3
    hierarchy_max_communities: int = 10_000
    hierarchy_resolution_overrides: dict[str, float] = field(default_factory=dict)
    application_version: str = "0.1.0"
    igraph_version: str = ""

    @classmethod
    def from_api(cls, value: dict) -> "AnalysisConfig":
        return cls(
            name=value["name"],
            algorithm=value.get("algorithm", "LEIDEN"),
            objective=value.get("objective", "CPM"),
            resolution=float(value.get("resolution", 1.0)),
            seed=int(value.get("seed", 42)),
            iterations=int(value.get("iterations", -1)),
            object_types=tuple(value.get("objectTypes") or DEFAULT_OBJECT_TYPES),
            owners=tuple(value.get("owners") or ()),
            minimum_confidence=float(value.get("minimumConfidence", 0.8)),
            minimum_community_size=int(value.get("minimumCommunitySize", 3)),
            edge_weights=DEFAULT_EDGE_WEIGHTS | dict(value.get("edgeWeights") or {}),
            parallel_edge_weight_cap=float(value.get("parallelEdgeWeightCap", 10.0)),
            hub_policy=value.get("hubPolicy", "DEGREE_NORMALIZATION"),
            direction_policy=value.get("directionPolicy", "SYMMETRIZE_SUM"),
            include_technical_objects=bool(value.get("includeTechnicalObjects", False)),
            hierarchy_enabled=bool(value.get("hierarchyEnabled", False)),
            hierarchy_child_resolution=float(value.get("hierarchyChildResolution", 1.0)),
            hierarchy_minimum_size=int(value.get("hierarchyMinimumSize", 20)),
            hierarchy_max_depth=int(value.get("hierarchyMaxDepth", 3)),
            hierarchy_max_communities=int(value.get("hierarchyMaxCommunities", 10_000)),
            hierarchy_resolution_overrides={
                str(key): float(resolution)
                for key, resolution in dict(
                    value.get("hierarchyResolutionOverrides") or {}
                ).items()
            },
            application_version=value.get("applicationVersion", "0.1.0"),
            igraph_version=value.get("igraphVersion", ""),
        )

    def to_api(self) -> dict:
        return {
            "name": self.name,
            "algorithm": self.algorithm,
            "objective": self.objective,
            "resolution": self.resolution,
            "seed": self.seed,
            "iterations": self.iterations,
            "objectTypes": list(self.object_types),
            "owners": list(self.owners),
            "minimumConfidence": self.minimum_confidence,
            "minimumCommunitySize": self.minimum_community_size,
            "edgeWeights": self.edge_weights,
            "parallelEdgeAggregation": "TYPE_MAX_THEN_CAPPED_SUM",
            "parallelEdgeWeightCap": self.parallel_edge_weight_cap,
            "hubPolicy": self.hub_policy,
            "directionPolicy": self.direction_policy,
            "includeTechnicalObjects": self.include_technical_objects,
            "hierarchyEnabled": self.hierarchy_enabled,
            "hierarchyChildResolution": self.hierarchy_child_resolution,
            "hierarchyMinimumSize": self.hierarchy_minimum_size,
            "hierarchyMaxDepth": self.hierarchy_max_depth,
            "hierarchyMaxCommunities": self.hierarchy_max_communities,
            "hierarchyResolutionOverrides": self.hierarchy_resolution_overrides,
            "applicationVersion": self.application_version,
            "igraphVersion": self.igraph_version,
        }


@dataclass(frozen=True, slots=True)
class AnalysisEdge:
    source: str
    target: str
    weight: float
    relationship_types: tuple[str, ...]
    relationship_ids: tuple[str, ...]


@dataclass(slots=True)
class AnalysisGraph:
    nodes: dict[str, GraphNode]
    directed_edges: list[AnalysisEdge]
    undirected_edges: list[AnalysisEdge]
    merged_nodes: dict[str, str]
    excluded_hub_ids: set[str]
    hub_impact: dict[str, float]
    isolated_node_ids: set[str]
    pipeline_counts: dict[str, int]


@dataclass(slots=True)
class AnalysisResult:
    membership: dict[str, int]
    community_metrics: dict[int, dict]
    community_edges: list[dict]
    centrality_results: list[dict]
    summary: dict
    hierarchy_nodes: list[dict] = field(default_factory=list)
    hierarchy_memberships: list[tuple[str, str]] = field(default_factory=list)
