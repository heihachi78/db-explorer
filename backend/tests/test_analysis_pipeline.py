import math

import pytest

from app.analysis.communities import create_undirected_igraph, detect_communities
from app.analysis.metrics import assemble_result
from app.analysis.models import AnalysisConfig
from app.analysis.preprocessing import build_analysis_graph
from app.graph.models import GraphEdge, GraphNode


def node(
    identifier: str,
    *,
    name: str | None = None,
    object_type: str = "TABLE",
    owner: str = "APP",
    external: bool = False,
) -> GraphNode:
    return GraphNode(
        id=identifier, database_key="db", container_key="pdb", owner=owner,
        name=name or identifier, subobject_name=None, object_type=object_type,
        oracle_object_type=object_type.replace("_", " "), status="VALID",
        oracle_object_id=None, created_at=None, last_ddl_at=None,
        is_external=external, metadata={},
    )


def edge(
    identifier: str,
    source: str,
    target: str,
    relationship_type: str = "DEPENDS_ON",
    confidence: float = 1.0,
) -> GraphEdge:
    return GraphEdge(
        id=identifier, source=source, target=target,
        relationship_type=relationship_type, directed=True,
        confidence=confidence, origin="TEST", metadata={}, evidence=(),
    )


def test_preprocessing_merges_package_body_aggregates_edges_and_tracks_isolates() -> None:
    nodes = [
        node("package", name="ORDER_API", object_type="PACKAGE"),
        node("body", name="ORDER_API", object_type="PACKAGE_BODY"),
        node("table"), node("isolated", object_type="VIEW"),
        node("index", object_type="INDEX"),
        node("external", object_type="EXTERNAL_OBJECT", external=True),
    ]
    edges = [
        edge("body-table-1", "body", "table", confidence=1.0),
        edge("body-table-2", "body", "table", confidence=0.9),
        edge("package-table-fk", "package", "table", "FOREIGN_KEY"),
        edge("table-package", "table", "package"),
        edge("self", "package", "body"),
        edge("external-edge", "table", "external"),
    ]
    config = AnalysisConfig(name="test", minimum_confidence=0.0, hub_policy="NONE")

    graph = build_analysis_graph(nodes, edges, config)

    assert set(graph.nodes) == {"package", "table", "isolated"}
    assert graph.merged_nodes == {"body": "package"}
    assert graph.isolated_node_ids == {"isolated"}
    assert graph.pipeline_counts["selfLoopsRemoved"] == 1
    assert len(graph.directed_edges) == 2
    assert graph.undirected_edges[0].weight == 10.0
    assert graph.undirected_edges[0].relationship_types == ("DEPENDS_ON", "FOREIGN_KEY")


def test_degree_normalization_and_top_hub_exclusion() -> None:
    nodes = [node("hub"), *(node(f"leaf-{index}") for index in range(100))]
    edges = [edge(f"edge-{index}", "hub", f"leaf-{index}") for index in range(100)]

    normalized = build_analysis_graph(
        nodes, edges,
        AnalysisConfig(name="normalized", minimum_confidence=0, hub_policy="DEGREE_NORMALIZATION"),
    )
    expected = 3.0 / math.sqrt(math.log(102) * math.log(3))
    assert normalized.undirected_edges[0].weight == pytest.approx(expected)
    assert normalized.hub_impact["hub"] == pytest.approx(1 - expected / 3.0)
    assert normalized.hub_impact["leaf-0"] == pytest.approx(1 - expected / 3.0)

    excluded = build_analysis_graph(
        nodes, edges,
        AnalysisConfig(name="excluded", minimum_confidence=0, hub_policy="EXCLUDE_TOP_HUBS"),
    )
    assert excluded.excluded_hub_ids == {"hub"}
    assert excluded.hub_impact == {"hub": 1.0}
    assert excluded.undirected_edges == []
    assert len(excluded.isolated_node_ids) == 100


def test_leiden_is_reproducible_and_metrics_describe_two_communities() -> None:
    nodes = [node(value, owner="SALES" if value < "D" else "BILLING") for value in "ABCDEF"]
    edges = [
        edge("ab", "A", "B"), edge("ba", "B", "A"),
        edge("ac", "A", "C"), edge("bc", "B", "C"),
        edge("de", "D", "E"), edge("ed", "E", "D"),
        edge("df", "D", "F"), edge("ef", "E", "F"),
        edge("bridge", "C", "D", "POINTS_TO", confidence=0.1),
    ]
    config = AnalysisConfig(
        name="communities", minimum_confidence=0, hub_policy="NONE",
        resolution=1.0, seed=42,
    )
    graph = build_analysis_graph(nodes, edges, config)

    first_membership, first_quality = detect_communities(graph, config)
    second_membership, second_quality = detect_communities(graph, config)
    result = assemble_result(graph, first_membership, first_quality, config, 0.01)

    assert first_membership == second_membership
    assert first_quality == second_quality
    assert {first_membership[value] for value in "ABC"} == {first_membership["A"]}
    assert {first_membership[value] for value in "DEF"} == {first_membership["D"]}
    assert first_membership["A"] != first_membership["D"]
    assert result.summary["communityCount"] == 2
    assert result.summary["communitySizes"] == [3, 3]
    assert result.summary["schemaPurity"] == 1.0
    assert len(result.community_edges) == 1
    assert all(metrics["internalDensity"] == 1.0 for metrics in result.community_metrics.values())
    assert {row["metric"] for row in result.centrality_results} >= {
        "PAGERANK", "BETWEENNESS", "K_CORE", "ARTICULATION_POINT",
    }


def test_modularity_quality_is_calculated_for_the_global_partition() -> None:
    nodes = [node(value) for value in "ABCDEF"]
    edges = [
        edge("ab", "A", "B"), edge("ac", "A", "C"), edge("bc", "B", "C"),
        edge("de", "D", "E"), edge("df", "D", "F"), edge("ef", "E", "F"),
    ]
    config = AnalysisConfig(
        name="modularity", objective="MODULARITY", minimum_confidence=0,
        hub_policy="NONE", seed=42,
    )
    graph = build_analysis_graph(nodes, edges, config)

    membership, quality = detect_communities(graph, config)

    ordered = [membership[node_id] for node_id in sorted(graph.nodes)]
    expected = create_undirected_igraph(graph).modularity(
        ordered, weights="weight", resolution=1.0, directed=False,
    )
    assert quality == pytest.approx(expected)
    assert quality == pytest.approx(0.5)
