from fastapi import APIRouter

from .config import router as config_router
from .analyses import router as analyses_router
from .annotations import router as annotations_router
from .connection import router as connection_router
from .graph import router as graph_router
from .exports import router as exports_router
from .scan import router as scan_router


api_router = APIRouter(prefix="/api")
api_router.include_router(config_router)
api_router.include_router(connection_router)
api_router.include_router(scan_router)
api_router.include_router(graph_router)
api_router.include_router(analyses_router)
api_router.include_router(annotations_router)
api_router.include_router(exports_router)


@api_router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
