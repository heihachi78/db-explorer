import threading
import time
from collections.abc import Callable

from app.persistence.analysis_repository import AnalysisRepository
from app.persistence.graph_repository import GraphRepository
from app.tasks.models import TaskState
from app.errors import AppError

from .communities import detect_communities
from .hierarchy import build_hierarchy
from .metrics import assemble_result
from .models import AnalysisConfig
from .preprocessing import build_analysis_graph


class AnalysisCancelled(RuntimeError):
    pass


class AnalysisService:
    def __init__(
        self,
        graph_repository: GraphRepository,
        analysis_repository: AnalysisRepository,
        *,
        max_nodes: int = 500_000,
        max_edges: int = 5_000_000,
    ) -> None:
        self.graph_repository = graph_repository
        self.analysis_repository = analysis_repository
        self.max_nodes = max_nodes
        self.max_edges = max_edges

    @staticmethod
    def _check_cancelled(cancelled: threading.Event) -> None:
        if cancelled.is_set():
            raise AnalysisCancelled("Analysis was cancelled.")

    def run(
        self,
        analysis_id: str,
        config: AnalysisConfig,
        report: Callable[..., None],
        cancelled: threading.Event,
    ) -> None:
        try:
            self._run(analysis_id, config, report, cancelled)
        except MemoryError as error:
            raise AppError(
                "ANALYSIS_MEMORY_EXHAUSTED",
                "Az elemzéshez nem áll rendelkezésre elegendő memória; szűkítsd az ownereket vagy objektumtípusokat.",
                status_code=507,
            ) from error

    def _run(
        self,
        analysis_id: str,
        config: AnalysisConfig,
        report: Callable[..., None],
        cancelled: threading.Event,
    ) -> None:
        started = time.perf_counter()
        if not self.analysis_repository.mark_running(analysis_id):
            raise AnalysisCancelled("Analysis was cancelled before it started.")
        report(TaskState.PREPARING_ANALYSIS, message="Loading and preprocessing the source graph.")
        source_nodes, source_edges = self.graph_repository.load_source_graph()
        self._check_cancelled(cancelled)
        graph = build_analysis_graph(source_nodes, source_edges, config)
        if not graph.nodes:
            raise AppError(
                "ANALYSIS_EMPTY_GRAPH",
                "No objects remain after applying the analysis filters.",
                status_code=422,
            )
        if len(graph.nodes) > self.max_nodes or len(graph.directed_edges) > self.max_edges:
            raise AppError(
                "ANALYSIS_TOO_LARGE",
                "Az elemzési gráf meghaladja a konfigurált erőforráskorlátot.",
                status_code=413,
                details={
                    "nodeCount": len(graph.nodes),
                    "edgeCount": len(graph.directed_edges),
                    "maxNodes": self.max_nodes,
                    "maxEdges": self.max_edges,
                    "suggestion": "Szűkítsd az ownereket vagy objektumtípusokat, illetve emeld a minimum confidence értéket.",
                },
            )
        report(
            TaskState.DETECTING_COMMUNITIES,
            message="Running Leiden community detection by connected component.",
            counters=graph.pipeline_counts,
        )
        self._check_cancelled(cancelled)
        membership, quality = detect_communities(graph, config)
        report(
            TaskState.CALCULATING_METRICS,
            message="Calculating community metrics and centrality.",
            counters=graph.pipeline_counts | {
                "communities": len({value for value in membership.values() if value >= 0})
            },
        )
        self._check_cancelled(cancelled)
        result = assemble_result(
            graph, membership, quality, config, time.perf_counter() - started
        )
        if config.hierarchy_enabled:
            report(
                TaskState.DETECTING_COMMUNITIES,
                message="Recursively splitting large communities for the experimental hierarchy.",
                counters=graph.pipeline_counts,
            )
            hierarchy_nodes, hierarchy_memberships, hierarchy_summary = build_hierarchy(
                graph,
                membership,
                result.community_metrics,
                config,
                lambda: self._check_cancelled(cancelled),
            )
            result.hierarchy_nodes = hierarchy_nodes
            result.hierarchy_memberships = hierarchy_memberships
            result.summary["hierarchy"] = hierarchy_summary
        result.summary["runtimeSeconds"] = round(time.perf_counter() - started, 12)
        self._check_cancelled(cancelled)
        report(TaskState.SAVING_RESULTS, message="Saving reproducible analysis results.")
        if not self.analysis_repository.save_success(analysis_id, result):
            raise AnalysisCancelled("Analysis was cancelled before results were committed.")
