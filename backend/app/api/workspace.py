from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.errors import AppError
from app.persistence.database import database, initialize_database, publish_database
from app.persistence.export_repository import ExportRepository


router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.post("/reset")
def reset_workspace(request: Request) -> dict:
    manager = request.app.state.task_manager
    if manager.active:
        raise AppError(
            "OPERATION_IN_PROGRESS",
            "A munkaterület folyamatban lévő művelet közben nem törölhető.",
            status_code=409,
        )
    settings = request.app.state.settings
    ExportRepository(settings.database_path).cleanup_files(settings.export_dir)
    for path in settings.export_dir.glob("*") if settings.export_dir.exists() else ():
        if path.is_file():
            path.unlink(missing_ok=True)
    settings.next_database_path.unlink(missing_ok=True)
    initialize_database(settings.next_database_path)
    reset_at = datetime.now(UTC).isoformat()
    with database(settings.next_database_path) as connection:
        connection.execute(
            "INSERT INTO app_meta (key, value_json, updated_at) VALUES ('workspace_reset_at', ?, ?)",
            (f'"{reset_at}"', reset_at),
        )
        connection.commit()
    publish_database(settings.next_database_path, settings.database_path)
    manager.reset()
    request.app.state.active_analysis_ids.clear()
    return {"reset": True, "resetAt": reset_at, "datasetId": None}
