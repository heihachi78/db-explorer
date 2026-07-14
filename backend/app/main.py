from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.persistence.database import initialize_database
from app.persistence.repositories import ScanStatusRepository
from app.tasks.manager import TaskManager


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.app_data_dir.mkdir(parents=True, exist_ok=True)
        initialize_database(resolved_settings.database_path)
        app.state.task_manager.persist_initial_state()
        yield
        await app.state.task_manager.shutdown()

    app = FastAPI(
        title="Oracle Graph Analyzer",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.task_manager = TaskManager(ScanStatusRepository(resolved_settings.database_path))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.app_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(api_router)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    if (frontend_dist / "index.html").is_file():
        @app.get("/{path:path}", include_in_schema=False)
        async def spa_fallback(path: str) -> FileResponse:
            candidate = (frontend_dist / path).resolve()
            if candidate.is_file() and frontend_dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
