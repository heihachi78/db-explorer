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
    "READS_FROM": 4.0,
    "TRIGGER_ON": 4.0,
    "WRITES_TO": 4.0,
    "DEPENDS_ON": 3.0,
    "CALLS": 3.0,
    "CONTAINS": 2.0,
    "USES_SEQUENCE": 1.5,
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
    application_version: str = "0.1.0"
    igraph_version: str = ""

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
