import heapq
import itertools
from dataclasses import dataclass
from typing import Literal

from app.errors import AppError
from app.graph.models import GraphEdge, GraphNode
from app.persistence.graph_repository import Direction, GraphRepository


DEFAULT_EDGE_WEIGHTS = {
    "FOREIGN_KEY": 5.0,
    "TRIGGER_ON": 4.0,
    "DEPENDS_ON": 3.0,
    "POINTS_TO": 1.0,
    "INDEX_ON": 0.5,
}


@dataclass(frozen=True, slots=True)
class ViewLimits:
    max_nodes: int
    max_edges: int


def _neighbor(edge: GraphEdge, current_id: str, direction: Direction) -> str | None:
    if direction == "OUTGOING":
        return edge.target if edge.source == current_id else None
    if direction == "INCOMING":
        return edge.source if edge.target == current_id else None
    if edge.source == current_id:
        return edge.target
    if edge.target == current_id:
        return edge.source
    return None


def _require_objects(repository: GraphRepository, object_ids: list[str]) -> list[GraphNode]:
    nodes = repository.get_objects(object_ids)
    found = {node.id for node in nodes}
    missing = [object_id for object_id in object_ids if object_id not in found]
    if missing:
        raise AppError(
            "OBJECT_NOT_FOUND",
            "A kért objektum nem található az aktuális felmérésben.",
            status_code=404,
            details={"objectIds": missing},
        )
    return nodes


def build_subgraph(
    repository: GraphRepository,
    root_ids: list[str],
    *,
    depth: int,
    direction: Direction,
    relationship_types: tuple[str, ...],
    minimum_confidence: float,
    include_external: bool,
    limits: ViewLimits,
) -> dict:
    roots = _require_objects(repository, root_ids)
    if len(roots) > limits.max_nodes:
        raise AppError(
            "NODE_LIMIT_TOO_SMALL",
            "A node-limit kisebb a kiinduló objektumok számánál.",
            details={"rootCount": len(roots), "maxNodes": limits.max_nodes},
        )

    nodes = {node.id: node for node in roots}
    depths = {node.id: 0 for node in roots}
    frontier = [node.id for node in roots]
    selected_edges: dict[str, GraphEdge] = {}
    truncated = False

    for current_depth in range(depth):
        if not frontier:
            break
        edges = repository.adjacent_edges(
            frontier,
            direction=direction,
            relationship_types=relationship_types,
            minimum_confidence=minimum_confidence,
        )
        neighbor_ids = {
            neighbor_id
            for edge in edges
            for current_id in frontier
            if (neighbor_id := _neighbor(edge, current_id, direction)) is not None
            and neighbor_id not in nodes
        }
        neighbor_nodes = {node.id: node for node in repository.get_objects(sorted(neighbor_ids))}
        next_frontier: list[str] = []

        for edge in edges:
            matching_neighbors = [
                neighbor_id
                for current_id in frontier
                if (neighbor_id := _neighbor(edge, current_id, direction)) is not None
            ]
            if not matching_neighbors:
                continue
            neighbor_id = matching_neighbors[0]
            neighbor_node = nodes.get(neighbor_id) or neighbor_nodes.get(neighbor_id)
            if neighbor_node is None or (neighbor_node.is_external and not include_external):
                continue
            if neighbor_id not in nodes:
                if len(nodes) >= limits.max_nodes:
                    truncated = True
                    continue
                nodes[neighbor_id] = neighbor_node
                depths[neighbor_id] = current_depth + 1
                if not neighbor_node.is_external:
                    next_frontier.append(neighbor_id)
            if edge.source not in nodes or edge.target not in nodes:
                continue
            if edge.id not in selected_edges:
                if len(selected_edges) >= limits.max_edges:
                    truncated = True
                    continue
                selected_edges[edge.id] = edge
        frontier = list(dict.fromkeys(next_frontier))

    ordered_nodes = sorted(nodes.values(), key=lambda node: (depths[node.id], node.owner, node.name, node.id))
    return {
        "rootObjectIds": root_ids,
        "nodes": [node.to_api() | {"depth": depths[node.id]} for node in ordered_nodes],
        "edges": [edge.to_api() for edge in selected_edges.values()],
        "truncated": truncated,
        "limits": {"maxNodes": limits.max_nodes, "maxEdges": limits.max_edges},
        "suggestion": (
            "Szűkítsd a kapcsolattípusokat, emeld a minimum confidence értéket vagy csökkentsd a mélységet."
            if truncated else None
        ),
    }


def impact_graph(
    repository: GraphRepository,
    object_id: str,
    *,
    mode: Literal["DEPENDENTS", "DEPENDENCIES"],
    max_depth: int,
    relationship_types: tuple[str, ...],
    minimum_confidence: float,
    include_external: bool,
    limits: ViewLimits,
) -> dict:
    direction: Direction = "INCOMING" if mode == "DEPENDENTS" else "OUTGOING"
    result = build_subgraph(
        repository,
        [object_id],
        depth=max_depth,
        direction=direction,
        relationship_types=relationship_types,
        minimum_confidence=minimum_confidence,
        include_external=include_external,
        limits=limits,
    )
    result["mode"] = mode
    result["estimatedImpact"] = True
    return result


def _effective_weight(edge: GraphEdge, weights: dict[str, float]) -> float:
    return max(0.000001, weights.get(edge.relationship_type, 1.0) * edge.confidence)


def find_paths(
    repository: GraphRepository,
    source_id: str,
    target_id: str,
    *,
    mode: Literal["HOPS", "WEIGHTED"],
    directed: bool,
    max_paths: int,
    max_depth: int,
    relationship_types: tuple[str, ...],
    minimum_confidence: float,
    include_external: bool,
    edge_weights: dict[str, float],
    max_expanded_nodes: int,
) -> dict:
    required_nodes = _require_objects(repository, [source_id, target_id])
    node_cache = {node.id: node for node in required_nodes}
    if source_id == target_id:
        node = repository.get_object(source_id)
        return {
            "sourceId": source_id,
            "targetId": target_id,
            "mode": mode,
            "directed": directed,
            "paths": [{"nodes": [node.to_api()], "edges": [], "hops": 0, "totalCost": 0.0}],
            "truncated": False,
        }

    direction: Direction = "OUTGOING" if directed else "BOTH"
    queue: list[tuple[float, int, int, str, tuple[str, ...], tuple[GraphEdge, ...]]] = []
    sequence = itertools.count()
    heapq.heappush(queue, (0.0, 0, next(sequence), source_id, (source_id,), ()))
    found: list[tuple[float, tuple[str, ...], tuple[GraphEdge, ...]]] = []
    expanded = 0
    truncated = False

    while queue and len(found) < max_paths:
        cost, hops, _, current_id, node_path, edge_path = heapq.heappop(queue)
        if current_id == target_id:
            found.append((cost, node_path, edge_path))
            continue
        if hops >= max_depth:
            continue
        if expanded >= max_expanded_nodes:
            truncated = True
            break
        expanded += 1
        current_node = node_cache.get(current_id)
        if current_node is not None and current_node.is_external:
            continue
        edges = repository.adjacent_edges(
            [current_id],
            direction=direction,
            relationship_types=relationship_types,
            minimum_confidence=minimum_confidence,
        )
        neighbors = {
            neighbor_id
            for edge in edges
            if (neighbor_id := _neighbor(edge, current_id, direction)) is not None
        }
        node_cache.update({
            node.id: node
            for node in repository.get_objects(neighbors - node_cache.keys())
        })
        for edge in edges:
            neighbor_id = _neighbor(edge, current_id, direction)
            if neighbor_id is None or neighbor_id in node_path:
                continue
            neighbor = node_cache.get(neighbor_id)
            if neighbor is None or (neighbor.is_external and not include_external):
                continue
            step_cost = 1.0 if mode == "HOPS" else 1.0 / _effective_weight(edge, edge_weights)
            heapq.heappush(
                queue,
                (
                    cost + step_cost,
                    hops + 1,
                    next(sequence),
                    neighbor_id,
                    (*node_path, neighbor_id),
                    (*edge_path, edge),
                ),
            )

    paths = []
    for cost, node_ids, edges in found:
        nodes = repository.get_objects(node_ids)
        paths.append({
            "nodes": [node.to_api() for node in nodes],
            "edges": [
                edge.to_api() | {
                    "effectiveWeight": round(_effective_weight(edge, edge_weights), 12),
                    "stepCost": round(
                        1.0 if mode == "HOPS" else 1.0 / _effective_weight(edge, edge_weights),
                        12,
                    ),
                }
                for edge in edges
            ],
            "hops": len(edges),
            "totalCost": round(cost, 12),
        })
    return {
        "sourceId": source_id,
        "targetId": target_id,
        "mode": mode,
        "directed": directed,
        "paths": paths,
        "truncated": truncated,
        "expandedNodes": expanded,
    }
