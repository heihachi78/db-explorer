import statistics
import re
from collections import Counter, defaultdict
from typing import Any

import igraph as ig

from .communities import create_undirected_igraph
from .models import AnalysisConfig, AnalysisGraph, AnalysisResult


def _rounded(value: float) -> float:
    return round(float(value), 12)


NAME_STOPWORDS = {
    "API", "PKG", "PACKAGE", "TBL", "TABLE", "VIEW", "PROC", "PROCEDURE",
    "FN", "FUNCTION", "TRG", "TRIGGER", "TYPE", "BODY", "DATA", "COMMON",
}


def _suggest_community_name(
    graph: AnalysisGraph,
    node_ids: list[str],
    dominant_schema: str,
    internal_strength: Counter[str],
) -> tuple[str, str]:
    tokens: Counter[str] = Counter()
    for node_id in node_ids:
        node = graph.nodes[node_id]
        for token in re.split(r"[^A-Z0-9]+", node.name.upper()):
            if len(token) >= 2 and not token.isdigit() and token not in NAME_STOPWORDS:
                tokens[token] += 1
    top_token = next((token for token, _ in tokens.most_common() if token != dominant_schema), None)
    ranked_nodes = sorted(
        node_ids,
        key=lambda node_id: (
            graph.nodes[node_id].object_type not in {"TABLE", "PACKAGE"},
            -internal_strength[node_id],
            graph.nodes[node_id].owner,
            graph.nodes[node_id].name,
        ),
    )
    central = graph.nodes[ranked_nodes[0]]
    suggested = f"{dominant_schema} / {top_token}" if top_token else dominant_schema
    explanation = (
        f"Domináns séma: {dominant_schema}; "
        f"leggyakoribb névtoken: {top_token or 'nincs'}; "
        f"központi {central.object_type}: {central.owner}.{central.name}."
    )
    return suggested, explanation


def _community_edges(
    graph: AnalysisGraph,
    membership: dict[str, int],
) -> list[dict[str, Any]]:
    aggregated: dict[tuple[int, int], dict[str, Any]] = {}
    for edge in graph.undirected_edges:
        source_community = membership.get(edge.source, -1)
        target_community = membership.get(edge.target, -1)
        if source_community < 0 or target_community < 0 or source_community == target_community:
            continue
        key = tuple(sorted((source_community, target_community)))
        item = aggregated.setdefault(key, {
            "sourceCommunity": key[0],
            "targetCommunity": key[1],
            "edgeCount": 0,
            "totalWeight": 0.0,
            "relationshipTypeDistribution": Counter(),
            "bridgePairs": [],
            "rawForwardWeight": 0.0,
            "rawReverseWeight": 0.0,
        })
        item["edgeCount"] += 1
        item["totalWeight"] += edge.weight
        item["relationshipTypeDistribution"].update(edge.relationship_types)
        item["bridgePairs"].append({
            "source": edge.source, "target": edge.target, "weight": edge.weight,
        })
    for edge in graph.directed_edges:
        source_community = membership.get(edge.source, -1)
        target_community = membership.get(edge.target, -1)
        if source_community < 0 or target_community < 0 or source_community == target_community:
            continue
        key = tuple(sorted((source_community, target_community)))
        item = aggregated.get(key)
        if item is None:
            continue
        field = "rawForwardWeight" if source_community == key[0] else "rawReverseWeight"
        item[field] += edge.weight
    result = []
    for item in aggregated.values():
        item["totalWeight"] = _rounded(item["totalWeight"])
        raw_forward = item.pop("rawForwardWeight")
        raw_reverse = item.pop("rawReverseWeight")
        raw_total = raw_forward + raw_reverse
        forward_ratio = raw_forward / raw_total if raw_total else 0.5
        item["forwardWeight"] = _rounded(item["totalWeight"] * forward_ratio)
        item["reverseWeight"] = _rounded(item["totalWeight"] - item["forwardWeight"])
        item["relationshipTypeDistribution"] = dict(item["relationshipTypeDistribution"])
        item["bridgePairs"] = sorted(
            item["bridgePairs"], key=lambda pair: (-pair["weight"], pair["source"], pair["target"])
        )[:10]
        result.append(item)
    return sorted(result, key=lambda item: (item["sourceCommunity"], item["targetCommunity"]))


def calculate_community_metrics(
    graph: AnalysisGraph,
    membership: dict[str, int],
    config: AnalysisConfig,
) -> dict[int, dict[str, Any]]:
    communities: dict[int, list[str]] = defaultdict(list)
    for node_id, community_id in membership.items():
        if community_id >= 0:
            communities[community_id].append(node_id)

    total_weight = sum(edge.weight for edge in graph.undirected_edges)
    total_volume = 2 * total_weight
    internal_edges: Counter[int] = Counter()
    external_edges: Counter[int] = Counter()
    internal_weight: Counter[int] = Counter()
    external_weight: Counter[int] = Counter()
    internal_strength: dict[int, Counter[str]] = defaultdict(Counter)
    external_strength: dict[int, Counter[str]] = defaultdict(Counter)
    relationship_types: dict[int, Counter[str]] = defaultdict(Counter)

    for edge in graph.undirected_edges:
        source_community = membership.get(edge.source, -1)
        target_community = membership.get(edge.target, -1)
        if source_community < 0 or target_community < 0:
            continue
        if source_community == target_community:
            community_id = source_community
            internal_edges[community_id] += 1
            internal_weight[community_id] += edge.weight
            internal_strength[community_id][edge.source] += edge.weight
            internal_strength[community_id][edge.target] += edge.weight
            relationship_types[community_id].update(edge.relationship_types)
        else:
            for community_id, node_id in (
                (source_community, edge.source),
                (target_community, edge.target),
            ):
                external_edges[community_id] += 1
                external_weight[community_id] += edge.weight
                external_strength[community_id][node_id] += edge.weight
                relationship_types[community_id].update(edge.relationship_types)

    results: dict[int, dict[str, Any]] = {}
    for community_id, node_ids in sorted(communities.items()):
        node_ids.sort()
        size = len(node_ids)
        possible_edges = size * (size - 1) / 2
        volume = 2 * internal_weight[community_id] + external_weight[community_id]
        denominator = min(volume, max(0.0, total_volume - volume))
        owner_distribution = Counter(graph.nodes[node_id].owner for node_id in node_ids)
        type_distribution = Counter(graph.nodes[node_id].object_type for node_id in node_ids)
        dominant_schema, dominant_count = owner_distribution.most_common(1)[0]
        ext_ratio_denominator = internal_weight[community_id] + external_weight[community_id]
        conductance = external_weight[community_id] / denominator if denominator > 0 else 0.0
        density = internal_edges[community_id] / possible_edges if possible_edges else 0.0
        external_ratio = (
            external_weight[community_id] / ext_ratio_denominator
            if ext_ratio_denominator else 0.0
        )
        warnings: list[str] = []
        if size < config.minimum_community_size:
            warnings.append("SMALL_COMPONENT")
        if dominant_count / size < 0.6:
            warnings.append("CROSS_SCHEMA")
        if conductance > 0.5:
            warnings.append("HIGH_CONDUCTANCE")
        suggested_name, name_explanation = _suggest_community_name(
            graph, node_ids, dominant_schema, internal_strength[community_id]
        )
        results[community_id] = {
            "communityId": community_id,
            "nodeCount": size,
            "internalEdgeCount": internal_edges[community_id],
            "externalEdgeCount": external_edges[community_id],
            "internalWeight": _rounded(internal_weight[community_id]),
            "externalWeight": _rounded(external_weight[community_id]),
            "internalDensity": _rounded(density),
            "externalRatio": _rounded(external_ratio),
            "conductance": _rounded(conductance),
            "coverage": _rounded(internal_weight[community_id] / total_weight if total_weight else 0.0),
            "schemaDistribution": dict(sorted(owner_distribution.items())),
            "dominantSchema": dominant_schema,
            "dominantSchemaRatio": _rounded(dominant_count / size),
            "objectTypeDistribution": dict(sorted(type_distribution.items())),
            "topInternalHubs": [
                {"objectId": node_id, "strength": _rounded(strength)}
                for node_id, strength in internal_strength[community_id].most_common(10)
            ],
            "topBridgeObjects": [
                {"objectId": node_id, "externalStrength": _rounded(strength)}
                for node_id, strength in external_strength[community_id].most_common(10)
            ],
            "relationshipTypeDistribution": dict(sorted(relationship_types[community_id].items())),
            "suggestedName": suggested_name,
            "nameExplanation": name_explanation,
            "stability": "NOT_ASSESSED",
            "warnings": warnings,
        }
    return results


def _directed_graph(graph: AnalysisGraph) -> ig.Graph:
    node_ids = sorted(graph.nodes)
    indexes = {node_id: index for index, node_id in enumerate(node_ids)}
    result = ig.Graph(
        n=len(node_ids),
        edges=[(indexes[edge.source], indexes[edge.target]) for edge in graph.directed_edges],
        directed=True,
    )
    result.vs["name"] = node_ids
    result.es["weight"] = [edge.weight for edge in graph.directed_edges]
    return result


def calculate_centrality(
    graph: AnalysisGraph,
    membership: dict[str, int],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    directed = _directed_graph(graph)
    undirected = create_undirected_igraph(graph)
    rows: list[dict[str, Any]] = []
    structural = {"articulationObjectIds": [], "bridgeEdges": []}

    if directed.vcount():
        pagerank = directed.pagerank(directed=True, damping=0.85, weights="weight")
        total_strength = directed.strength(mode="all", weights="weight")
        in_degree = directed.degree(mode="in")
        out_degree = directed.degree(mode="out")
        for index, node_id in enumerate(directed.vs["name"]):
            for metric, value, metadata in (
                ("PAGERANK", pagerank[index], {"damping": 0.85}),
                ("TOTAL_STRENGTH", total_strength[index], {}),
                ("IN_DEGREE", in_degree[index], {}),
                ("OUT_DEGREE", out_degree[index], {}),
            ):
                rows.append({"objectId": node_id, "metric": metric, "value": _rounded(value), "metadata": metadata})

    if undirected.vcount():
        names = undirected.vs["name"]
        weights = list(undirected.es["weight"])
        costs = [1.0 / max(weight, 0.000001) for weight in weights]
        approximate = undirected.vcount() > 20_000
        if approximate:
            import random
            sample_size = min(512, undirected.vcount())
            sources = random.Random(seed).sample(range(undirected.vcount()), sample_size)
            betweenness = undirected.betweenness(directed=False, weights=costs, sources=sources)
            scale = undirected.vcount() / sample_size
            betweenness = [value * scale for value in betweenness]
        else:
            sample_size = undirected.vcount()
            betweenness = undirected.betweenness(directed=False, weights=costs)
        coreness = undirected.coreness()
        articulation = set(undirected.articulation_points())
        structural["articulationObjectIds"] = sorted(names[index] for index in articulation)
        bridge_incidence: Counter[int] = Counter()
        for edge_index in undirected.bridges():
            source, target = undirected.es[edge_index].tuple
            bridge_incidence[source] += 1
            bridge_incidence[target] += 1
            structural["bridgeEdges"].append({
                "source": names[source], "target": names[target],
            })
        structural["bridgeEdges"].sort(key=lambda edge: (edge["source"], edge["target"]))

        internal_strength: Counter[str] = Counter()
        external_strength: Counter[str] = Counter()
        for edge in graph.undirected_edges:
            if membership.get(edge.source) == membership.get(edge.target) and membership.get(edge.source, -1) >= 0:
                internal_strength[edge.source] += edge.weight
                internal_strength[edge.target] += edge.weight
            else:
                external_strength[edge.source] += edge.weight
                external_strength[edge.target] += edge.weight

        for index, node_id in enumerate(names):
            values = (
                ("BETWEENNESS", betweenness[index], {"approximated": approximate, "sampleSize": sample_size}),
                ("K_CORE", coreness[index], {}),
                ("ARTICULATION_POINT", 1.0 if index in articulation else 0.0, {}),
                ("BRIDGE_INCIDENCE", bridge_incidence[index], {}),
                ("INTERNAL_STRENGTH", internal_strength[node_id], {}),
                ("EXTERNAL_STRENGTH", external_strength[node_id], {}),
            )
            for metric, value, metadata in values:
                rows.append({"objectId": node_id, "metric": metric, "value": _rounded(value), "metadata": metadata})
    return rows, structural


def assemble_result(
    graph: AnalysisGraph,
    membership: dict[str, int],
    quality: float,
    config: AnalysisConfig,
    runtime_seconds: float,
) -> AnalysisResult:
    community_metrics = calculate_community_metrics(graph, membership, config)
    community_edges = _community_edges(graph, membership)
    centrality, structural = calculate_centrality(graph, membership, config.seed)
    conductances = [metrics["conductance"] for metrics in community_metrics.values()]
    sizes = [metrics["nodeCount"] for metrics in community_metrics.values()]
    total_weight = sum(edge.weight for edge in graph.undirected_edges)
    internal_weight = sum(
        edge.weight for edge in graph.undirected_edges
        if membership.get(edge.source, -1) >= 0
        and membership.get(edge.source) == membership.get(edge.target)
    )
    schema_purity = (
        sum(metrics["dominantSchemaRatio"] * metrics["nodeCount"] for metrics in community_metrics.values())
        / sum(sizes) if sizes else 0.0
    )
    owner_communities: dict[str, set[int]] = defaultdict(set)
    for node_id, community_id in membership.items():
        if community_id >= 0:
            owner_communities[graph.nodes[node_id].owner].add(community_id)
    schema_pair_weights: Counter[tuple[str, str]] = Counter()
    for edge in graph.undirected_edges:
        source_owner = graph.nodes[edge.source].owner
        target_owner = graph.nodes[edge.target].owner
        if source_owner != target_owner:
            schema_pair_weights[tuple(sorted((source_owner, target_owner)))] += edge.weight
    summary = {
        "algorithm": config.algorithm,
        "objective": config.objective,
        "resolution": config.resolution,
        "quality": _rounded(quality),
        "communityCount": len(community_metrics),
        "communitySizes": sorted(sizes, reverse=True),
        "singletonCount": sum(size == 1 for size in sizes),
        "smallCommunityCount": sum(size < config.minimum_community_size for size in sizes),
        "isolatedNodeCount": len(graph.isolated_node_ids),
        "sharedInfrastructureCount": len(graph.excluded_hub_ids),
        "internalWeightRatio": _rounded(internal_weight / total_weight if total_weight else 0.0),
        "averageConductance": _rounded(statistics.fmean(conductances) if conductances else 0.0),
        "medianConductance": _rounded(statistics.median(conductances) if conductances else 0.0),
        "schemaPurity": _rounded(schema_purity),
        "runtimeSeconds": _rounded(runtime_seconds),
        "estimatedPeakMemoryBytes": (
            len(graph.nodes) * 512 + (len(graph.directed_edges) + len(graph.undirected_edges)) * 256
        ),
        "hubImpact": [
            {"objectId": node_id, "weightReductionRatio": _rounded(impact)}
            for node_id, impact in sorted(
                graph.hub_impact.items(), key=lambda item: (-item[1], item[0])
            )[:100]
        ],
        "schemaSummary": {
            "ownerCommunityCounts": {
                owner: len(community_ids)
                for owner, community_ids in sorted(owner_communities.items())
            },
            "crossSchemaCommunityIds": sorted(
                community_id for community_id, metrics in community_metrics.items()
                if len(metrics["schemaDistribution"]) > 1
            ),
            "schemaPairWeights": [
                {"sourceSchema": pair[0], "targetSchema": pair[1], "weight": _rounded(weight)}
                for pair, weight in sorted(
                    schema_pair_weights.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        },
        "structuralMetrics": structural,
        "pipelineCounts": graph.pipeline_counts,
    }
    return AnalysisResult(membership, community_metrics, community_edges, centrality, summary)
