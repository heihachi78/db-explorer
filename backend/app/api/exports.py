import asyncio
import threading
import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse

from app.api.models import ExportRequest
from app.errors import AppError
from app.exports.service import ExportCancelled, ExportService
from app.persistence.analysis_repository import AnalysisRepository
from app.persistence.export_repository import ExportRepository
from app.tasks.models import TaskState


router = APIRouter(prefix="/export", tags=["export"])


def _repository(request: Request) -> ExportRepository:
    return ExportRepository(request.app.state.settings.database_path)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_export(payload: ExportRequest, request: Request) -> dict:
    run = AnalysisRepository(request.app.state.settings.database_path).get(payload.analysisId)
    if run is None:
        raise AppError("ANALYSIS_NOT_FOUND", "A kért elemzés nem található.", status_code=404)
    if run["status"] != "SUCCEEDED":
        raise AppError("ANALYSIS_NOT_COMPLETE", "Csak befejezett elemzés exportálható.", status_code=409)
    export_id = str(uuid.uuid4())
    repository = _repository(request)
    repository.create(export_id, payload.analysisId, payload.format)

    async def operation(task_manager) -> None:
        cancelled = threading.Event()
        service = ExportService(repository, request.app.state.settings.export_dir)
        worker = asyncio.create_task(asyncio.to_thread(
            service.run,
            export_id,
            payload.analysisId,
            payload.format,
            task_manager.update,
            cancelled,
        ))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled.set()
            try:
                await asyncio.shield(worker)
            except ExportCancelled:
                pass
            repository.mark_terminal(export_id, "CANCELLED")
            raise
        except Exception as error:
            repository.mark_terminal(export_id, "FAILED", str(error))
            raise

    try:
        await request.app.state.task_manager.start(operation, initial_state=TaskState.EXPORTING)
    except BaseException:
        repository.mark_terminal(export_id, "FAILED", "Export could not be started.")
        raise
    return {"accepted": True, "exportId": export_id}


@router.get("/{export_id}/status")
def export_status(export_id: str, request: Request) -> dict:
    job = _repository(request).get(export_id)
    if job is None:
        raise AppError("EXPORT_NOT_FOUND", "A kért export nem található.", status_code=404)
    return job


@router.get("/{export_id}/file")
def export_file(export_id: str, request: Request) -> FileResponse:
    details = _repository(request).file_details(export_id)
    if details is None:
        raise AppError("EXPORT_NOT_READY", "Az exportfájl még nem érhető el.", status_code=409)
    path, content_type, filename = details
    export_root = request.app.state.settings.export_dir.resolve()
    resolved = path.resolve()
    if export_root not in resolved.parents or not resolved.is_file():
        raise AppError("EXPORT_FILE_MISSING", "Az exportfájl nem található.", status_code=404)
    return FileResponse(resolved, media_type=content_type, filename=filename)
