from fastapi import APIRouter, Request

from app.api.models import PublicConfig
from app.config import Settings
from app.persistence.database import database


router = APIRouter(tags=["config"])


@router.get("/config", response_model=PublicConfig)
def get_public_config(request: Request) -> PublicConfig:
    settings: Settings = request.app.state.settings
    manager = request.app.state.task_manager
    dataset_id = None
    reset_required = False
    if settings.database_path.exists():
        with database(settings.database_path, read_only=True) as connection:
            rows = connection.execute(
                "SELECT key, value_json FROM app_meta WHERE key IN ('dataset_id', 'scan_summary')"
            ).fetchall()
        values = {row["key"]: row["value_json"] for row in rows}
        if "dataset_id" in values:
            import json
            dataset_id = json.loads(values["dataset_id"])
        reset_required = "scan_summary" in values
    return PublicConfig(
        oracleConfigured=settings.oracle_configured,
        oracleMode=settings.oracle_mode,
        dataFilePresent=settings.database_path.exists(),
        activeOperation=manager.active,
        datasetId=dataset_id,
        resetRequired=reset_required,
        limits={
            "interactiveMaxDepth": 3,
            "defaultMaxNodes": 500,
            "hardMaxNodes": 2_000,
            "defaultMaxEdges": 2_000,
            "hardMaxEdges": 10_000,
            "scanMaxSeconds": settings.scan_max_seconds,
            "analysisMaxNodes": settings.analysis_max_nodes,
            "analysisMaxEdges": settings.analysis_max_edges,
        },
    )
