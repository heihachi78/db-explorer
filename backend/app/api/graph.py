from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.models import GraphOverviewRequest, ImpactRequest, PathsRequest, SubgraphRequest
from app.errors import AppError
from app.graph.traversal import (
    DEFAULT_EDGE_WEIGHTS,
    ViewLimits,
    build_subgraph,
    find_paths,
    impact_graph,
)
from app.graph.overview import build_graph_overview
from app.persistence.graph_repository import GraphRepository


router = APIRouter(tags=["graph"])


def _repository(request: Request) -> GraphRepository:
    return GraphRepository(request.app.state.settings.database_path)


def _not_found(kind: str, identifier: str) -> AppError:
    return AppError(
        f"{kind.upper()}_NOT_FOUND",
        "A kért gráfelem nem található az aktuális felmérésben.",
        status_code=404,
        details={"id": identifier},
    )


@router.get("/objects")
def search_objects(
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    owner: Annotated[str | None, Query(max_length=128)] = None,
    object_type: Annotated[str | None, Query(alias="objectType", max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=64)] = None,
    is_external: Annotated[bool | None, Query(alias="isExternal")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> dict:
    return _repository(request).search_objects(
        query=q.strip() if q else None,
        owner=owner.strip() if owner else None,
        object_type=object_type.strip() if object_type else None,
        status=status.strip() if status else None,
        is_external=is_external,
        page=page,
        page_size=page_size,
    )


@router.get("/objects/{object_id}/neighbors")
def object_neighbors(
    object_id: str,
    request: Request,
    direction: Annotated[str, Query(pattern="^(INCOMING|OUTGOING|BOTH)$")] = "BOTH",
    relationship_types: Annotated[list[str] | None, Query(alias="relationshipType")] = None,
    minimum_confidence: Annotated[float, Query(alias="minimumConfidence", ge=0, le=1)] = 0.0,
    include_external: Annotated[bool, Query(alias="includeExternal")] = True,
    max_nodes: Annotated[int, Query(alias="maxNodes", ge=1, le=2_000)] = 500,
    max_edges: Annotated[int, Query(alias="maxEdges", ge=0, le=10_000)] = 2_000,
) -> dict:
    return build_subgraph(
        _repository(request),
        [object_id],
        depth=1,
        direction=direction,  # type: ignore[arg-type]
        relationship_types=tuple(relationship_types or ()),
        minimum_confidence=minimum_confidence,
        include_external=include_external,
        limits=ViewLimits(max_nodes, max_edges),
    )


@router.get("/objects/{object_id}")
def object_details(object_id: str, request: Request) -> dict:
    repository = _repository(request)
    node = repository.get_object(object_id)
    if node is None:
        raise _not_found("object", object_id)
    return node.to_api() | {
        "details": repository.get_object_details(object_id),
        "relationshipCounts": repository.relationship_counts(object_id),
    }


@router.get("/relationships/{relationship_id}")
def relationship_details(relationship_id: str, request: Request) -> dict:
    edge = _repository(request).get_edge(relationship_id)
    if edge is None:
        raise _not_found("relationship", relationship_id)
    return edge.to_api()


@router.post("/subgraph")
def subgraph(payload: SubgraphRequest, request: Request) -> dict:
    return build_subgraph(
        _repository(request),
        payload.rootObjectIds,
        depth=payload.depth,
        direction=payload.direction,
        relationship_types=tuple(payload.relationshipTypes),
        minimum_confidence=payload.minimumConfidence,
        include_external=payload.includeExternal,
        limits=ViewLimits(payload.maxNodes, payload.maxEdges),
    )


@router.post("/graph-overview")
def graph_overview(payload: GraphOverviewRequest, request: Request) -> dict:
    return build_graph_overview(
        _repository(request),
        query=payload.query,
        owners=tuple(payload.owners),
        object_types=tuple(payload.objectTypes),
        statuses=tuple(payload.statuses),
        relationship_types=tuple(payload.relationshipTypes),
        minimum_confidence=payload.minimumConfidence,
        include_external=payload.includeExternal,
    )


@router.post("/impact")
def impact(payload: ImpactRequest, request: Request) -> dict:
    return impact_graph(
        _repository(request),
        payload.objectId,
        mode=payload.mode,
        max_depth=payload.maxDepth,
        relationship_types=tuple(payload.relationshipTypes),
        minimum_confidence=payload.minimumConfidence,
        include_external=payload.includeExternal,
        limits=ViewLimits(payload.maxNodes, payload.maxEdges),
    )


@router.post("/paths")
def paths(payload: PathsRequest, request: Request) -> dict:
    return find_paths(
        _repository(request),
        payload.sourceId,
        payload.targetId,
        mode=payload.mode,
        directed=payload.directed,
        max_paths=payload.maxPaths,
        max_depth=payload.maxDepth,
        relationship_types=tuple(payload.relationshipTypes),
        minimum_confidence=payload.minimumConfidence,
        include_external=payload.includeExternal,
        edge_weights=DEFAULT_EDGE_WEIGHTS | payload.edgeWeights,
        max_expanded_nodes=payload.maxExpandedNodes,
    )
