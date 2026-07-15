from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.errors import AppError

from .communities import detect_communities
from .metrics import calculate_community_metrics
from .models import AnalysisConfig, AnalysisGraph


def induced_analysis_graph(graph: AnalysisGraph, node_ids: set[str]) -> AnalysisGraph:
    nodes = {node_id: graph.nodes[node_id] for node_id in sorted(node_ids)}
    directed_edges = [
        edge for edge in graph.directed_edges
        if edge.source in node_ids and edge.target in node_ids
    ]
    undirected_edges = [
        edge for edge in graph.undirected_edges
        if edge.source in node_ids and edge.target in node_ids
    ]
    connected = {
        node_id
        for edge in undirected_edges
        for node_id in (edge.source, edge.target)
    }
    excluded = graph.excluded_hub_ids & node_ids
    return AnalysisGraph(
        nodes=nodes,
        directed_edges=directed_edges,
        undirected_edges=undirected_edges,
        merged_nodes={
            source: target for source, target in graph.merged_nodes.items()
            if target in node_ids
        },
        excluded_hub_ids=excluded,
        hub_impact={
            node_id: impact for node_id, impact in graph.hub_impact.items()
            if node_id in node_ids
        },
        isolated_node_ids=node_ids - excluded - connected,
        pipeline_counts={
            "nodesIncluded": len(nodes),
            "directedEdgesAggregated": len(directed_edges),
            "undirectedEdges": len(undirected_edges),
            "isolatedNodes": len(node_ids - excluded - connected),
        },
    )


def _groups(membership: dict[str, int]) -> list[list[str]]:
    positive: dict[int, list[str]] = defaultdict(list)
    singletons: list[list[str]] = []
    for node_id, community_id in membership.items():
        if community_id >= 0:
            positive[community_id].append(node_id)
        elif community_id == -1:
            singletons.append([node_id])
    groups = [sorted(node_ids) for node_ids in positive.values()] + singletons
    return sorted(groups, key=lambda node_ids: node_ids[0])


def build_hierarchy(
    graph: AnalysisGraph,
    base_membership: dict[str, int],
    base_metrics: dict[int, dict[str, Any]],
    config: AnalysisConfig,
    check_cancelled: Callable[[], None],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], dict[str, Any]]:
    """Recursively split large base communities while preserving graph weights and hub policy."""
    communities: dict[int, list[str]] = defaultdict(list)
    for node_id, community_id in base_membership.items():
        if community_id >= 0:
            communities[community_id].append(node_id)

    nodes: list[dict[str, Any]] = []
    memberships: list[tuple[str, str]] = []
    truncated = False

    def append_node(
        hierarchy_id: str,
        parent_id: str | None,
        level: int,
        resolution: float,
        node_ids: list[str],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        item = {
            "hierarchyId": hierarchy_id,
            "parentId": parent_id,
            "level": level,
            "resolution": resolution,
            "splitResolution": None,
            "splitQuality": None,
            "nodeCount": len(node_ids),
            "stopReason": None,
            "metrics": metrics,
        }
        nodes.append(item)
        return item

    used_overrides: set[str] = set()

    def stop(parent: dict[str, Any], node_ids: list[str], reason: str) -> None:
        parent["stopReason"] = reason
        memberships.extend(
            (str(parent["hierarchyId"]), node_id) for node_id in sorted(node_ids)
        )

    def split(parent: dict[str, Any], node_ids: list[str]) -> None:
        nonlocal truncated
        check_cancelled()
        level = int(parent["level"])
        if level >= config.hierarchy_max_depth:
            stop(parent, node_ids, "MAX_DEPTH")
            return
        if len(node_ids) <= config.hierarchy_minimum_size:
            stop(parent, node_ids, "MINIMUM_SIZE")
            return

        parent_id = str(parent["hierarchyId"])
        if parent_id in config.hierarchy_resolution_overrides:
            used_overrides.add(parent_id)
        resolution = config.hierarchy_resolution_overrides.get(
            parent_id, config.hierarchy_child_resolution
        )
        local_graph = induced_analysis_graph(graph, set(node_ids))
        local_config = replace(
            config,
            name=f"{config.name} · {parent['hierarchyId']}",
            resolution=resolution,
            hierarchy_enabled=False,
        )
        local_membership, quality = detect_communities(local_graph, local_config)
        groups = _groups(local_membership)
        parent["splitResolution"] = resolution
        parent["splitQuality"] = round(float(quality), 12)
        if len(groups) <= 1 or (len(groups) == 1 and len(groups[0]) == len(node_ids)):
            stop(parent, node_ids, "NO_SPLIT")
            return
        if len(nodes) + len(groups) > config.hierarchy_max_communities:
            truncated = True
            stop(parent, node_ids, "COMMUNITY_LIMIT")
            return

        normalized_membership = {
            node_id: community_id
            for community_id, group in enumerate(groups)
            for node_id in group
        }
        child_metrics = calculate_community_metrics(
            local_graph, normalized_membership, local_config
        )
        for child_index, child_ids in enumerate(groups):
            hierarchy_id = f"{parent['hierarchyId']}.{child_index}"
            child = append_node(
                hierarchy_id,
                str(parent["hierarchyId"]),
                level + 1,
                resolution,
                child_ids,
                child_metrics[child_index],
            )
            split(child, child_ids)

    if len(communities) > config.hierarchy_max_communities:
        raise AppError(
            "ANALYSIS_HIERARCHY_TOO_LARGE",
            "Az alapfelosztás több közösséget hozott létre a hierarchia konfigurált limitjénél.",
            status_code=413,
            details={
                "rootCount": len(communities),
                "maxCommunities": config.hierarchy_max_communities,
                "suggestion": "Csökkentsd az alap-resolution értékét vagy emeld óvatosan a hierarchy közösséglimitet.",
            },
        )
    roots_to_split: list[tuple[dict[str, Any], list[str]]] = []
    for community_id, node_ids in sorted(communities.items()):
        node_ids.sort()
        root = append_node(
            str(community_id), None, 0, config.resolution,
            node_ids, base_metrics[community_id],
        )
        roots_to_split.append((root, node_ids))
    for root, node_ids in roots_to_split:
        split(root, node_ids)

    parent_ids = {str(node["parentId"]) for node in nodes if node["parentId"] is not None}
    leaves = [node for node in nodes if str(node["hierarchyId"]) not in parent_ids]
    summary = {
        "experimental": True,
        "baseResolution": config.resolution,
        "defaultChildResolution": config.hierarchy_child_resolution,
        "minimumSplitSize": config.hierarchy_minimum_size,
        "maximumDepth": config.hierarchy_max_depth,
        "maximumCommunities": config.hierarchy_max_communities,
        "rootCount": len(communities),
        "hierarchyNodeCount": len(nodes),
        "leafCount": len(leaves),
        "maximumDepthReached": max((int(node["level"]) for node in nodes), default=0),
        "resolutionOverrides": dict(sorted(config.hierarchy_resolution_overrides.items())),
        "unusedResolutionOverrideIds": sorted(
            set(config.hierarchy_resolution_overrides) - used_overrides
        ),
        "leafMembershipCount": len(memberships),
        "truncated": truncated,
        "warning": "A különböző resolution értékű felosztások kísérletiek és nem feltétlenül alkotnak természetes üzleti taxonómiát.",
    }
    return nodes, memberships, summary
