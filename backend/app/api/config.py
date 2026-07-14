from fastapi import APIRouter, Request

from app.api.models import PublicConfig
from app.config import Settings


router = APIRouter(tags=["config"])


@router.get("/config", response_model=PublicConfig)
def get_public_config(request: Request) -> PublicConfig:
    settings: Settings = request.app.state.settings
    manager = request.app.state.task_manager
    return PublicConfig(
        oracleConfigured=settings.oracle_configured,
        oracleMode=settings.oracle_mode,
        dataFilePresent=settings.database_path.exists(),
        activeOperation=manager.active,
        limits={
            "interactiveMaxDepth": 3,
            "defaultMaxNodes": 500,
            "hardMaxNodes": 2_000,
            "defaultMaxEdges": 2_000,
            "hardMaxEdges": 10_000,
        },
    )
