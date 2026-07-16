import asyncio
import threading
import uuid
from typing import Annotated
from dataclasses import replace

import igraph
from fastapi import APIRouter, Query, Request, status

from app.analysis.models import (
    TECHNICAL_OBJECT_TYPES,
    AnalysisConfig,
    DEFAULT_EDGE_WEIGHTS,
    DEFAULT_OBJECT_TYPES,
)
from app.analysis.comparison import compare_memberships
from app.analysis.service import AnalysisCancelled, AnalysisService
from app.analysis.preprocessing import build_analysis_graph
from app.api.models import (
    AnalysisCompareRequest,
    AnalysisRequest,
    HierarchyAnalysisRequest,
    ResolutionProfileRequest,
    SeedProfileRequest,
)
from app.errors import AppError
from app.persistence.analysis_repository import AnalysisRepository
from app.persistence.graph_repository import GraphRepository
from app.persistence.export_repository import ExportRepository
from app.persistence.subgraph_repository import SubgraphRepository
from app.tasks.models import TaskState


router = APIRouter(prefix="/analyses", tags=["analyses"])


def _repository(request: Request) -> AnalysisRepository:
    return AnalysisRepository(request.app.state.settings.database_path)


def _require_run(repository: AnalysisRepository, analysis_id: str) -> dict:
    run = repository.get(analysis_id)
    if run is None:
        raise AppError(
            "ANALYSIS_NOT_FOUND",
            "A kért elemzési futás nem található.",
            status_code=404,
            details={"analysisId": analysis_id},
        )
    return run


def _config(payload: AnalysisRequest) -> AnalysisConfig:
    return AnalysisConfig(
        name=payload.name,
        subgraph_id=payload.subgraphId,
        algorithm=payload.algorithm,
        objective=payload.objective,
        resolution=payload.resolution,
        seed=payload.seed,
        iterations=payload.iterations,
        object_types=tuple(payload.objectTypes or DEFAULT_OBJECT_TYPES),
        owners=tuple(payload.owners),
        minimum_confidence=payload.minimumConfidence,
        minimum_community_size=payload.minimumCommunitySize,
        edge_weights=DEFAULT_EDGE_WEIGHTS | payload.edgeWeights,
        parallel_edge_weight_cap=payload.parallelEdgeWeightCap,
        hub_policy=payload.hubPolicy,
        direction_policy=payload.directionPolicy,
        include_technical_objects=payload.includeTechnicalObjects,
        igraph_version=igraph.__version__,
    )


def _estimate(config: AnalysisConfig, request: Request) -> dict:
    settings = request.app.state.settings
    object_types = set(config.object_types)
    if config.include_technical_objects:
        object_types.update(TECHNICAL_OBJECT_TYPES)
    if config.subgraph_id and SubgraphRepository(settings.database_path).get(config.subgraph_id) is None:
        raise AppError("SUBGRAPH_NOT_FOUND", "A kiválasztott részgráf nem található.", status_code=404)
    estimate = GraphRepository(settings.database_path).estimate_analysis(
        object_types=tuple(sorted(object_types)),
        owners=config.owners,
        minimum_confidence=config.minimum_confidence,
        max_nodes=settings.analysis_max_nodes,
        max_edges=settings.analysis_max_edges,
        subgraph_id=config.subgraph_id,
    )
    if config.subgraph_id:
        estimate["subgraph"] = SubgraphRepository(settings.database_path).get(config.subgraph_id)
    return estimate


async def _start_configs(
    configs: list[AnalysisConfig],
    request: Request,
    *,
    assess_stability: bool = False,
) -> list[str]:
    manager = request.app.state.task_manager
    if manager.active:
        raise AppError(
            "OPERATION_IN_PROGRESS",
            "Another long-running operation is already in progress.",
            status_code=409,
        )
    estimate = _estimate(configs[0], request)
    if not estimate["withinLimits"]:
        raise AppError(
            "ANALYSIS_TOO_LARGE",
            "A becsült elemzési gráf meghaladja a konfigurált erőforráskorlátot.",
            status_code=413,
            details=estimate | {
                "suggestion": "Szűkítsd az ownereket vagy objektumtípusokat, illetve emeld a minimum confidence értéket."
            },
        )
    repository = _repository(request)
    analysis_ids = [str(uuid.uuid4()) for _ in configs]
    for analysis_id, config in zip(analysis_ids, configs, strict=True):
        repository.create(analysis_id, config)
    request.app.state.active_analysis_ids = set(analysis_ids)

    async def operation(task_manager) -> None:
        cancelled = threading.Event()
        service = AnalysisService(
            GraphRepository(request.app.state.settings.database_path),
            repository,
            max_nodes=request.app.state.settings.analysis_max_nodes,
            max_edges=request.app.state.settings.analysis_max_edges,
        )

        def run_all() -> None:
            for analysis_id, config in zip(analysis_ids, configs, strict=True):
                if cancelled.is_set():
                    raise AnalysisCancelled("Analysis profile was cancelled.")
                service.run(analysis_id, config, task_manager.update, cancelled)
            if assess_stability:
                task_manager.update(
                    TaskState.ASSESSING_STABILITY,
                    message="Comparing seed partitions and calculating node stability.",
                )
                if cancelled.is_set():
                    raise AnalysisCancelled("Analysis profile was cancelled.")
                source_nodes, source_edges = service.graph_repository.load_source_graph(configs[0].subgraph_id)
                baseline_graph = build_analysis_graph(source_nodes, source_edges, configs[0])
                comparison = compare_memberships(
                    [
                        (analysis_id, repository.membership(analysis_id))
                        for analysis_id in analysis_ids
                    ],
                    baseline_graph.directed_edges,
                )
                repository.update_stability(analysis_ids[0], comparison)

        worker = asyncio.create_task(asyncio.to_thread(run_all))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled.set()
            try:
                await asyncio.shield(worker)
            except AnalysisCancelled:
                pass
            for analysis_id in analysis_ids:
                repository.mark_terminal(analysis_id, "CANCELLED")
            raise
        except Exception as error:
            for analysis_id in analysis_ids:
                repository.mark_terminal(analysis_id, "FAILED", str(error))
            raise
        finally:
            request.app.state.active_analysis_ids.difference_update(analysis_ids)

    try:
        await manager.start(operation, initial_state=TaskState.PREPARING_ANALYSIS)
    except BaseException:
        for analysis_id in analysis_ids:
            repository.discard_queued(analysis_id)
        request.app.state.active_analysis_ids.difference_update(analysis_ids)
        raise
    return analysis_ids


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(payload: AnalysisRequest, request: Request) -> dict:
    analysis_ids = await _start_configs([_config(payload)], request)
    analysis_id = analysis_ids[0]
    return {"accepted": True, "analysisId": analysis_id}


@router.post("/estimate")
def estimate_analysis(payload: AnalysisRequest, request: Request) -> dict:
    return _estimate(_config(payload), request)


@router.post("/hierarchy", status_code=status.HTTP_202_ACCEPTED)
async def start_hierarchy(payload: HierarchyAnalysisRequest, request: Request) -> dict:
    config = replace(
        _config(payload),
        hierarchy_enabled=True,
        hierarchy_child_resolution=payload.hierarchyChildResolution,
        hierarchy_minimum_size=payload.hierarchyMinimumSize,
        hierarchy_max_depth=payload.hierarchyMaxDepth,
        hierarchy_max_communities=payload.hierarchyMaxCommunities,
        hierarchy_resolution_overrides=payload.hierarchyResolutionOverrides,
    )
    analysis_ids = await _start_configs([config], request)
    return {"accepted": True, "analysisId": analysis_ids[0], "experimental": True}


@router.post("/resolution-profile", status_code=status.HTTP_202_ACCEPTED)
async def start_resolution_profile(payload: ResolutionProfileRequest, request: Request) -> dict:
    configs = []
    for resolution in payload.resolutions:
        config = _config(payload)
        configs.append(replace(
            config,
            name=f"{payload.name} · r={resolution:g}",
            resolution=resolution,
        ))
    analysis_ids = await _start_configs(configs, request)
    return {"accepted": True, "analysisIds": analysis_ids}


@router.post("/seed-profile", status_code=status.HTTP_202_ACCEPTED)
async def start_seed_profile(payload: SeedProfileRequest, request: Request) -> dict:
    configs = [
        replace(_config(payload), name=f"{payload.name} · seed={seed}", seed=seed)
        for seed in payload.seeds
    ]
    analysis_ids = await _start_configs(configs, request, assess_stability=True)
    return {
        "accepted": True,
        "analysisIds": analysis_ids,
        "baselineAnalysisId": analysis_ids[0],
    }


@router.get("")
def list_analyses(request: Request) -> dict:
    return {"items": _repository(request).list()}


@router.post("/compare")
def compare_analyses(payload: AnalysisCompareRequest, request: Request) -> dict:
    repository = _repository(request)
    runs = [_require_run(repository, analysis_id) for analysis_id in payload.analysisIds]
    if any(run["status"] != "SUCCEEDED" for run in runs):
        raise AppError(
            "ANALYSIS_NOT_COMPLETE",
            "Csak sikeresen befejezett elemzések hasonlíthatók össze.",
            status_code=409,
        )
    source_nodes, source_edges = GraphRepository(
        request.app.state.settings.database_path
    ).load_source_graph(AnalysisConfig.from_api(runs[0]["config"]).subgraph_id)
    baseline_graph = build_analysis_graph(
        source_nodes,
        source_edges,
        AnalysisConfig.from_api(runs[0]["config"]),
    )
    agreement = compare_memberships(
        [
            (analysis_id, repository.membership(analysis_id))
            for analysis_id in payload.analysisIds
        ],
        baseline_graph.directed_edges,
    )
    return {
        "items": [
            {
                "id": run["id"], "name": run["name"],
                "config": run["config"], "summary": run["summary"],
            }
            for run in runs
        ],
        "agreement": agreement,
    }


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str, request: Request) -> dict:
    return _require_run(_repository(request), analysis_id)


@router.post("/{analysis_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_analysis(analysis_id: str, request: Request) -> dict:
    repository = _repository(request)
    run = _require_run(repository, analysis_id)
    if run["status"] not in {"QUEUED", "RUNNING"} or analysis_id not in request.app.state.active_analysis_ids:
        raise AppError(
            "ANALYSIS_NOT_RUNNING",
            "Az elemzési futás nincs folyamatban.",
            status_code=409,
        )
    await request.app.state.task_manager.cancel()
    for active_id in tuple(request.app.state.active_analysis_ids):
        repository.mark_terminal(active_id, "CANCELLED")
    request.app.state.active_analysis_ids.clear()
    return {"accepted": True}


@router.delete("/{analysis_id}")
def delete_analysis(analysis_id: str, request: Request) -> dict:
    repository = _repository(request)
    _require_run(repository, analysis_id)
    export_repository = ExportRepository(request.app.state.settings.database_path)
    export_files = export_repository.files_for_analysis(analysis_id)
    if not repository.delete(analysis_id):
        raise AppError(
            "ANALYSIS_RUNNING",
            "Folyamatban lévő elemzés nem törölhető.",
            status_code=409,
        )
    export_root = request.app.state.settings.export_dir.resolve()
    for path in export_files:
        resolved = path.resolve()
        if export_root in resolved.parents:
            resolved.unlink(missing_ok=True)
    return {"deleted": True}


@router.get("/{analysis_id}/communities")
def list_communities(analysis_id: str, request: Request) -> dict:
    repository = _repository(request)
    run = _require_run(repository, analysis_id)
    if run["status"] != "SUCCEEDED":
        raise AppError("ANALYSIS_NOT_COMPLETE", "Az elemzés még nem fejeződött be.", status_code=409)
    return {"items": repository.communities(analysis_id)}


@router.get("/{analysis_id}/communities/{community_id}")
def get_community(analysis_id: str, community_id: int, request: Request) -> dict:
    repository = _repository(request)
    _require_run(repository, analysis_id)
    community = repository.community(analysis_id, community_id)
    if community is None:
        raise AppError(
            "COMMUNITY_NOT_FOUND", "A kért közösség nem található.", status_code=404,
            details={"analysisId": analysis_id, "communityId": community_id},
        )
    return community


@router.get("/{analysis_id}/communities/{community_id}/objects")
def get_community_objects(
    analysis_id: str,
    community_id: int,
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    owner: Annotated[str | None, Query(max_length=128)] = None,
    object_type: Annotated[str | None, Query(alias="objectType", max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
) -> dict:
    repository = _repository(request)
    _require_run(repository, analysis_id)
    result = repository.community_objects(
        analysis_id,
        community_id,
        query=q.strip() if q else None,
        owner=owner.strip() if owner else None,
        object_type=object_type.strip() if object_type else None,
        page=page,
        page_size=page_size,
    )
    if result is None:
        raise AppError("COMMUNITY_NOT_FOUND", "A kért közösség nem található.", status_code=404)
    return result


@router.get("/{analysis_id}/communities/{community_id}/subgraph")
def get_community_subgraph(
    analysis_id: str,
    community_id: int,
    request: Request,
    max_nodes: Annotated[int, Query(alias="maxNodes", ge=1, le=10_000)] = 2_000,
    max_edges: Annotated[int, Query(alias="maxEdges", ge=0, le=50_000)] = 10_000,
) -> dict:
    repository = _repository(request)
    _require_run(repository, analysis_id)
    result = repository.community_subgraph(
        analysis_id, community_id, max_nodes=max_nodes, max_edges=max_edges
    )
    if result is None:
        raise AppError("COMMUNITY_NOT_FOUND", "A kért közösség nem található.", status_code=404)
    return result


@router.get("/{analysis_id}/community-graph")
def get_community_graph(analysis_id: str, request: Request) -> dict:
    repository = _repository(request)
    run = _require_run(repository, analysis_id)
    if run["status"] != "SUCCEEDED":
        raise AppError("ANALYSIS_NOT_COMPLETE", "Az elemzés még nem fejeződött be.", status_code=409)
    return repository.community_graph(analysis_id)


@router.get("/{analysis_id}/hierarchy")
def get_hierarchy(analysis_id: str, request: Request) -> dict:
    repository = _repository(request)
    run = _require_run(repository, analysis_id)
    if run["status"] != "SUCCEEDED":
        raise AppError("ANALYSIS_NOT_COMPLETE", "Az elemzés még nem fejeződött be.", status_code=409)
    hierarchy = repository.hierarchy(analysis_id)
    if hierarchy is None:
        raise AppError(
            "HIERARCHY_NOT_AVAILABLE",
            "Ehhez a futáshoz nem készült hierarchikus felosztás.",
            status_code=404,
            details={"analysisId": analysis_id},
        )
    return hierarchy


@router.get("/{analysis_id}/hierarchy/{hierarchy_id}")
def get_hierarchy_node(analysis_id: str, hierarchy_id: str, request: Request) -> dict:
    repository = _repository(request)
    run = _require_run(repository, analysis_id)
    if run["status"] != "SUCCEEDED":
        raise AppError("ANALYSIS_NOT_COMPLETE", "Az elemzés még nem fejeződött be.", status_code=409)
    hierarchy_node = repository.hierarchy_node(analysis_id, hierarchy_id)
    if hierarchy_node is None:
        raise AppError(
            "HIERARCHY_NODE_NOT_FOUND",
            "A kért hierarchikus közösség nem található.",
            status_code=404,
            details={"analysisId": analysis_id, "hierarchyId": hierarchy_id},
        )
    return hierarchy_node
