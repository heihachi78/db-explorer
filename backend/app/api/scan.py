from fastapi import APIRouter, Request, status

from app.api.models import ScanRequest
from app.errors import AppError


router = APIRouter(prefix="/scan", tags=["scan"])


@router.get("/status")
def get_scan_status(request: Request) -> dict:
    return request.app.state.task_manager.snapshot()


@router.post("/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_scan(request: Request) -> dict[str, bool]:
    await request.app.state.task_manager.cancel()
    return {"accepted": True}


@router.post("")
def start_scan(_: ScanRequest) -> None:
    raise AppError(
        "SCANNER_NOT_AVAILABLE",
        "The multi-schema scanner is the next implementation milestone.",
        status_code=501,
    )
