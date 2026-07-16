from __future__ import annotations

from collections import Counter
from typing import Any

from app.graph.models import GraphEdge, GraphNode
from app.persistence.graph_repository import GraphRepository


def _matches_node(
    node: GraphNode,
    *,
    query: str | None,
    owners: set[str],
    object_types: set[str],
    statuses: set[str],
    include_external: bool,
) -> bool:
    if node.is_external and not include_external:
        return False
    if owners and node.owner.upper() not in owners:
        return False
    if object_types and node.object_type.upper() not in object_types:
        return False
    if statuses and (node.status or "UNKNOWN").upper() not in statuses:
        return False
    if query:
        needle = query.casefold()
        haystack = f"{node.owner}.{node.name} {node.id} {node.object_type}".casefold()
        if needle not in haystack:
            return False
    return True


def _distribution(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items(), key=lambda item: (-item[1], item[0])))


def build_graph_overview(
    repository: GraphRepository,
    *,
    query: str | None,
    owners: tuple[str, ...],
    object_types: tuple[str, ...],
    statuses: tuple[str, ...],
    relationship_types: tuple[str, ...],
    minimum_confidence: float,
    include_external: bool,
) -> dict[str, Any]:
    """Return the filtered source graph and its weakly connected components."""
    all_nodes, all_edges = repository.load_source_graph()
    owner_filter = {value.upper() for value in owners}
    type_filter = {value.upper() for value in object_types}
    status_filter = {value.upper() for value in statuses}
    relationship_filter = {value.upper() for value in relationship_types}

    nodes = [
        node for node in all_nodes
        if _matches_node(
            node,
            query=query,
            owners=owner_filter,
            object_types=type_filter,
            statuses=status_filter,
            include_external=include_external,
        )
    ]
    node_by_id = {node.id: node for node in nodes}
    edges = [
        edge for edge in all_edges
        if edge.source in node_by_id
        and edge.target in node_by_id
        and edge.confidence >= minimum_confidence
        and (not relationship_filter or edge.relationship_type.upper() in relationship_filter)
    ]

    adjacency: dict[str, set[str]] = {node.id: set() for node in nodes}
    for edge in edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    raw_node_components: list[list[str]] = []
    unseen = set(node_by_id)
    while unseen:
        start = min(unseen)
        stack = [start]
        component_ids: list[str] = []
        unseen.remove(start)
        while stack:
            current = stack.pop()
            component_ids.append(current)
            neighbors = adjacency[current] & unseen
            unseen.difference_update(neighbors)
            stack.extend(sorted(neighbors, reverse=True))
        raw_node_components.append(sorted(component_ids))

    raw_index_by_node = {
        node_id: index
        for index, node_ids in enumerate(raw_node_components)
        for node_id in node_ids
    }
    raw_edge_components: list[list[GraphEdge]] = [[] for _ in raw_node_components]
    for edge in edges:
        raw_edge_components[raw_index_by_node[edge.source]].append(edge)
    raw_components = list(zip(raw_node_components, raw_edge_components, strict=True))

    raw_components.sort(key=lambda item: (-len(item[0]), -len(item[1]), item[0][0]))
    component_by_node: dict[str, str] = {}
    components: list[dict[str, Any]] = []
    for index, (node_ids, component_edges) in enumerate(raw_components, start=1):
        component_id = f"component-{index}"
        component_nodes = [node_by_id[node_id] for node_id in node_ids]
        component_by_node.update({node_id: component_id for node_id in node_ids})
        undirected_pairs = {
            tuple(sorted((edge.source, edge.target))) for edge in component_edges
            if edge.source != edge.target
        }
        if len(component_nodes) == 1 and not component_edges:
            topology = "ISOLATED"
        elif len(undirected_pairs) == len(component_nodes) - 1:
            topology = "TREE"
        else:
            topology = "CYCLIC"
        node_count = len(component_nodes)
        possible_pairs = node_count * (node_count - 1) / 2
        components.append({
            "id": component_id,
            "nodeCount": node_count,
            "edgeCount": len(component_edges),
            "topology": topology,
            "density": round(len(undirected_pairs) / possible_pairs, 12) if possible_pairs else 0.0,
            "externalNodeCount": sum(node.is_external for node in component_nodes),
            "invalidNodeCount": sum(node.status == "INVALID" for node in component_nodes),
            "owners": _distribution([node.owner for node in component_nodes]),
            "objectTypes": _distribution([node.object_type for node in component_nodes]),
            "relationshipTypes": _distribution([edge.relationship_type for edge in component_edges]),
            "sampleObjects": [
                {"id": node.id, "label": f"{node.owner}.{node.name}"}
                for node in sorted(component_nodes, key=lambda item: (item.owner, item.name, item.id))[:5]
            ],
        })

    return {
        "nodes": [node.to_api() | {"componentId": component_by_node[node.id]} for node in nodes],
        "edges": [edge.to_api() for edge in edges],
        "components": components,
        "summary": {
            "sourceNodeCount": len(all_nodes),
            "sourceEdgeCount": len(all_edges),
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "componentCount": len(components),
            "isolatedNodeCount": sum(item["topology"] == "ISOLATED" for item in components),
            "treeComponentCount": sum(item["topology"] == "TREE" for item in components),
            "cyclicComponentCount": sum(item["topology"] == "CYCLIC" for item in components),
        },
        "facets": {
            "owners": _distribution([node.owner for node in nodes]),
            "objectTypes": _distribution([node.object_type for node in nodes]),
            "statuses": _distribution([node.status or "UNKNOWN" for node in nodes]),
            "relationshipTypes": _distribution([edge.relationship_type for edge in edges]),
        },
    }
