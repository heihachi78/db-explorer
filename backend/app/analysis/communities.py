import random
from collections.abc import Callable

import igraph as ig

from .models import AnalysisConfig, AnalysisGraph


CommunityDetector = Callable[[AnalysisGraph, AnalysisConfig], tuple[dict[str, int], float]]


def create_undirected_igraph(graph: AnalysisGraph) -> ig.Graph:
    node_ids = sorted(set(graph.nodes) - graph.excluded_hub_ids)
    indexes = {node_id: index for index, node_id in enumerate(node_ids)}
    edges = [
        (indexes[edge.source], indexes[edge.target])
        for edge in graph.undirected_edges
    ]
    result = ig.Graph(n=len(node_ids), edges=edges, directed=False)
    result.vs["name"] = node_ids
    result.es["weight"] = [edge.weight for edge in graph.undirected_edges]
    return result


def detect_leiden(
    analysis_graph: AnalysisGraph,
    config: AnalysisConfig,
) -> tuple[dict[str, int], float]:
    graph = create_undirected_igraph(analysis_graph)
    membership = {
        node_id: -2 for node_id in sorted(analysis_graph.excluded_hub_ids)
    }
    membership.update({
        node_id: -1 for node_id in sorted(analysis_graph.isolated_node_ids)
    })
    if graph.vcount() == 0:
        return membership, 0.0

    components = [
        sorted(component)
        for component in graph.connected_components(mode="weak")
    ]
    components.sort(key=lambda vertices: min(graph.vs[index]["name"] for index in vertices))
    next_community = 0
    total_quality = 0.0

    for component_index, vertices in enumerate(components):
        names = [graph.vs[index]["name"] for index in vertices]
        if len(vertices) == 1 and graph.degree(vertices[0]) == 0:
            membership[names[0]] = -1
            continue
        subgraph = graph.subgraph(vertices)
        ig.set_random_number_generator(random.Random(config.seed + component_index))
        clustering = subgraph.community_leiden(
            objective_function=config.objective,
            weights="weight",
            resolution=config.resolution,
            n_iterations=config.iterations,
        )
        total_quality += float(clustering.quality)
        groups = [
            sorted(subgraph.vs[index]["name"] for index in group)
            for group in clustering
        ]
        groups.sort(key=lambda group: group[0])
        for group in groups:
            for node_id in group:
                membership[node_id] = next_community
            next_community += 1
    if config.objective == "MODULARITY":
        ordered_membership = [membership[node_id] for node_id in graph.vs["name"]]
        total_quality = float(graph.modularity(
            ordered_membership,
            weights="weight",
            resolution=config.resolution,
            directed=False,
        ))
    return membership, total_quality


DETECTORS: dict[str, CommunityDetector] = {"LEIDEN": detect_leiden}


def detect_communities(
    graph: AnalysisGraph,
    config: AnalysisConfig,
) -> tuple[dict[str, int], float]:
    return DETECTORS[config.algorithm](graph, config)
