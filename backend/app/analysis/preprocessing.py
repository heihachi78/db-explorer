import math
from collections import defaultdict

from app.graph.models import GraphEdge, GraphNode

from .models import (
    TECHNICAL_OBJECT_TYPES,
    AnalysisConfig,
    AnalysisEdge,
    AnalysisGraph,
)


def _package_body_mapping(nodes: list[GraphNode]) -> dict[str, str]:
    packages = {
        (node.owner, node.name): node.id
        for node in nodes
        if node.object_type == "PACKAGE"
    }
    return {
        node.id: packages[(node.owner, node.name)]
        for node in nodes
        if node.object_type == "PACKAGE_BODY" and (node.owner, node.name) in packages
    }


def _included(node: GraphNode, config: AnalysisConfig) -> bool:
    if node.is_external or node.object_type in {"PACKAGE_BODY", "TYPE_BODY"}:
        return False
    if config.owners and node.owner not in config.owners:
        return False
    if node.object_type in config.object_types:
        return True
    return config.include_technical_objects and node.object_type in TECHNICAL_OBJECT_TYPES


def _aggregate_directed(
    edges: list[GraphEdge],
    included_ids: set[str],
    merged_nodes: dict[str, str],
    config: AnalysisConfig,
) -> tuple[list[AnalysisEdge], dict[str, int]]:
    by_pair: dict[tuple[str, str], dict[str, tuple[float, list[str]]]] = defaultdict(dict)
    counters = {"relationshipsFiltered": 0, "selfLoopsRemoved": 0}
    for edge in edges:
        source = merged_nodes.get(edge.source, edge.source)
        target = merged_nodes.get(edge.target, edge.target)
        if edge.confidence < config.minimum_confidence or source not in included_ids or target not in included_ids:
            counters["relationshipsFiltered"] += 1
            continue
        if source == target:
            counters["selfLoopsRemoved"] += 1
            continue
        weight = config.edge_weights.get(edge.relationship_type, 1.0) * edge.confidence
        current = by_pair[(source, target)].get(edge.relationship_type)
        if current is None or weight > current[0]:
            by_pair[(source, target)][edge.relationship_type] = (weight, [edge.id])
        elif weight == current[0]:
            current[1].append(edge.id)

    aggregated: list[AnalysisEdge] = []
    for (source, target), per_type in sorted(by_pair.items()):
        aggregated.append(AnalysisEdge(
            source=source,
            target=target,
            weight=min(config.parallel_edge_weight_cap, sum(value[0] for value in per_type.values())),
            relationship_types=tuple(sorted(per_type)),
            relationship_ids=tuple(sorted(edge_id for _, ids in per_type.values() for edge_id in ids)),
        ))
    counters["directedEdgesAggregated"] = len(aggregated)
    return aggregated, counters


def _degrees(node_ids: set[str], edges: list[AnalysisEdge]) -> dict[str, int]:
    neighbors: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        neighbors[edge.source].add(edge.target)
        neighbors[edge.target].add(edge.source)
    return {node_id: len(values) for node_id, values in neighbors.items()}


def _excluded_hubs(degrees: dict[str, int], config: AnalysisConfig) -> set[str]:
    if config.hub_policy != "EXCLUDE_TOP_HUBS":
        return set()
    connected = [(degree, node_id) for node_id, degree in degrees.items() if degree > 0]
    if not connected:
        return set()
    count = max(1, math.floor(len(connected) * 0.01))
    connected.sort(key=lambda item: (-item[0], item[1]))
    return {node_id for _, node_id in connected[:count]}


def _symmetrize(
    edges: list[AnalysisEdge],
    degrees: dict[str, int],
    excluded_hubs: set[str],
    config: AnalysisConfig,
) -> tuple[list[AnalysisEdge], dict[str, float]]:
    pairs: dict[tuple[str, str], list[AnalysisEdge]] = defaultdict(list)
    for edge in edges:
        if edge.source in excluded_hubs or edge.target in excluded_hubs:
            continue
        key = tuple(sorted((edge.source, edge.target)))
        pairs[key].append(edge)

    result: list[AnalysisEdge] = []
    hub_impact: dict[str, float] = {
        node_id: 1.0 for node_id in excluded_hubs
    }
    for (source, target), pair_edges in sorted(pairs.items()):
        hub_factor = 1.0
        if config.hub_policy == "DEGREE_NORMALIZATION":
            hub_factor = 1.0 / math.sqrt(
                math.log(2 + degrees[source]) * math.log(2 + degrees[target])
            )
            for node_id in (source, target):
                hub_impact[node_id] = max(hub_impact.get(node_id, 0.0), 1.0 - hub_factor)
        result.append(AnalysisEdge(
            source=source,
            target=target,
            weight=min(
                config.parallel_edge_weight_cap,
                sum(edge.weight * hub_factor for edge in pair_edges),
            ),
            relationship_types=tuple(sorted({item for edge in pair_edges for item in edge.relationship_types})),
            relationship_ids=tuple(sorted({item for edge in pair_edges for item in edge.relationship_ids})),
        ))
    return result, hub_impact


def build_analysis_graph(
    source_nodes: list[GraphNode],
    source_edges: list[GraphEdge],
    config: AnalysisConfig,
) -> AnalysisGraph:
    merged_nodes = _package_body_mapping(source_nodes)
    nodes = {node.id: node for node in source_nodes if _included(node, config)}
    included_ids = set(nodes)
    directed_edges, counters = _aggregate_directed(
        source_edges, included_ids, merged_nodes, config
    )
    degrees = _degrees(included_ids, directed_edges)
    excluded_hubs = _excluded_hubs(degrees, config)
    undirected_edges, hub_impact = _symmetrize(
        directed_edges, degrees, excluded_hubs, config
    )
    connected_ids = {
        node_id
        for edge in undirected_edges
        for node_id in (edge.source, edge.target)
    }
    isolated_ids = included_ids - excluded_hubs - connected_ids
    counters.update({
        "sourceNodes": len(source_nodes),
        "sourceRelationships": len(source_edges),
        "nodesIncluded": len(nodes),
        "nodesFiltered": len(source_nodes) - len(nodes) - len(merged_nodes),
        "nodesMerged": len(merged_nodes),
        "hubsExcluded": len(excluded_hubs),
        "isolatedNodes": len(isolated_ids),
        "undirectedEdges": len(undirected_edges),
    })
    return AnalysisGraph(
        nodes=nodes,
        directed_edges=directed_edges,
        undirected_edges=undirected_edges,
        merged_nodes=merged_nodes,
        excluded_hub_ids=excluded_hubs,
        hub_impact=hub_impact,
        isolated_node_ids=isolated_ids,
        pipeline_counts=counters,
    )
