from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.models import CommunitySubgraphRequest, NamedSubgraphRequest
from app.errors import AppError
from app.persistence.subgraph_repository import SubgraphRepository


router = APIRouter(prefix="/subgraphs", tags=["subgraphs"])


def _repository(request: Request) -> SubgraphRepository:
    return SubgraphRepository(request.app.state.settings.database_path)


@router.get("")
def list_subgraphs(request: Request) -> dict:
    return {"items": _repository(request).list()}


@router.post("")
def create_subgraph(payload: NamedSubgraphRequest, request: Request) -> dict:
    try:
        return _repository(request).create(
            payload.name, payload.objectIds, parent_id=payload.parentId
        )
    except ValueError as error:
        raise AppError("SUBGRAPH_INVALID", str(error), status_code=422) from error


@router.post("/from-community")
def create_subgraph_from_community(
    payload: CommunitySubgraphRequest, request: Request
) -> dict:
    try:
        return _repository(request).create_from_community(
            payload.name,
            payload.analysisId,
            payload.communityId,
            parent_id=payload.parentId,
        )
    except ValueError as error:
        raise AppError("COMMUNITY_NOT_FOUND", str(error), status_code=404) from error


@router.get("/{subgraph_id}")
def get_subgraph(subgraph_id: str, request: Request) -> dict:
    item = _repository(request).get(subgraph_id)
    if item is None:
        raise AppError("SUBGRAPH_NOT_FOUND", "A részgráf nem található.", status_code=404)
    return item


@router.get("/{subgraph_id}/graph")
def get_subgraph_graph(
    subgraph_id: str,
    request: Request,
    max_nodes: Annotated[int, Query(alias="maxNodes", ge=1, le=10_000)] = 2_000,
    max_edges: Annotated[int, Query(alias="maxEdges", ge=0, le=50_000)] = 10_000,
) -> dict:
    graph = _repository(request).graph(
        subgraph_id, max_nodes=max_nodes, max_edges=max_edges
    )
    if graph is None:
        raise AppError("SUBGRAPH_NOT_FOUND", "A részgráf nem található.", status_code=404)
    return graph


@router.delete("/{subgraph_id}")
def delete_subgraph(subgraph_id: str, request: Request) -> dict:
    if not _repository(request).delete(subgraph_id):
        raise AppError("SUBGRAPH_NOT_FOUND", "A részgráf nem található.", status_code=404)
    return {"deleted": True}
