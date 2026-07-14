import asyncio
import threading

from fastapi import APIRouter, Request, status

from app.api.models import ScanRequest
from app.oracle.connection import credentials_from_settings
from app.oracle.scanner import OracleScanner, ScanCancelled, ScanOptions, load_scan_summary


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
    options = ScanOptions(
        schemas=tuple(payload.schemas),
        object_types=tuple(payload.objectTypes),
        include_source_code=payload.includeSourceCode,
        resolve_external_references=payload.resolveExternalReferences,
        include_scheduler_objects=payload.includeSchedulerObjects,
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
            await asyncio.shield(worker)
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
