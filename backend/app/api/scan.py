import asyncio
import threading

from fastapi import APIRouter, Request, status

from app.api.models import ScanRequest
from app.errors import AppError
from app.oracle.connection import credentials_from_settings
from app.oracle.scanner import OracleScanner, ScanCancelled, ScanOptions, load_scan_summary
from app.persistence.export_repository import ExportRepository
from app.persistence.database import database


router = APIRouter(prefix="/scan", tags=["scan"])


@router.get("/status")
def get_scan_status(request: Request) -> dict:
    return request.app.state.task_manager.snapshot()


@router.post("/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_scan(request: Request) -> dict[str, bool]:
    await request.app.state.task_manager.cancel()
    return {"accepted": True}


@router.get("/statistics")
@router.get("/summary", include_in_schema=False)
def get_scan_summary(request: Request) -> dict:
    summary = load_scan_summary(request.app.state.settings.database_path)
    return {"available": summary is not None, "summary": summary}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_scan(payload: ScanRequest, request: Request) -> dict[str, bool]:
    settings = request.app.state.settings
    credentials = credentials_from_settings(settings)
    if settings.database_path.exists():
        with database(settings.database_path, read_only=True) as connection:
            previous_scan = connection.execute(
                "SELECT 1 FROM app_meta WHERE key = 'scan_summary'"
            ).fetchone()
        if previous_scan is not None:
            raise AppError(
                "WORKSPACE_RESET_REQUIRED",
                "Új metaadatgyűjtés előtt indíts új felmérést a munkaterület törlésével.",
                status_code=409,
            )
    options = ScanOptions(
        schemas=tuple(payload.schemas),
        object_types=tuple(payload.objectTypes),
        resolve_external_references=payload.resolveExternalReferences,
        synonym_max_depth=payload.synonymMaxDepth,
    )

    async def operation(manager) -> None:
        cancelled = threading.Event()
        published = threading.Event()
        publication_lock = threading.Lock()
        scanner = OracleScanner(
            credentials,
            settings.next_database_path,
            settings.database_path,
        )

        def report(*args, **kwargs) -> None:
            if not cancelled.is_set():
                manager.update(*args, **kwargs)

        worker = asyncio.create_task(
            asyncio.to_thread(
                scanner.run, options, report, cancelled, publication_lock, published
            )
        )
        try:
            await asyncio.wait_for(
                asyncio.shield(worker), timeout=settings.scan_max_seconds
            )
            ExportRepository(settings.database_path).cleanup_files(settings.export_dir)
        except TimeoutError:
            with publication_lock:
                if published.is_set():
                    ExportRepository(settings.database_path).cleanup_files(settings.export_dir)
                    return
                cancelled.set()
            try:
                await asyncio.shield(worker)
            except ScanCancelled:
                pass
            raise AppError(
                "SCAN_TIMEOUT",
                f"Az adatgyűjtés túllépte a konfigurált {settings.scan_max_seconds} másodperces időkorlátot.",
                status_code=408,
            )
        except asyncio.CancelledError:
            with publication_lock:
                if published.is_set():
                    return
                cancelled.set()
            try:
                await asyncio.shield(worker)
            except ScanCancelled:
                pass
            raise

    await request.app.state.task_manager.start(operation)
    return {"accepted": True}
