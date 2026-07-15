from fastapi import APIRouter, Request

from app.api.models import AnnotationPatchRequest, AnnotationRequest
from app.errors import AppError
from app.persistence.analysis_repository import AnalysisRepository


router = APIRouter(prefix="/annotations", tags=["annotations"])


def _repository(request: Request) -> AnalysisRepository:
    return AnalysisRepository(request.app.state.settings.database_path)


@router.post("")
def create_or_replace_annotation(payload: AnnotationRequest, request: Request) -> dict:
    annotation = _repository(request).upsert_annotation(
        payload.analysisId,
        payload.communityId,
        payload.name,
        payload.note,
    )
    if annotation is None:
        raise AppError(
            "COMMUNITY_NOT_FOUND",
            "A megjegyzéshez tartozó közösség nem található.",
            status_code=404,
        )
    return annotation


@router.patch("/{annotation_id}")
def update_annotation(
    annotation_id: str,
    payload: AnnotationPatchRequest,
    request: Request,
) -> dict:
    repository = _repository(request)
    current = repository.annotation(annotation_id)
    if current is None:
        raise AppError(
            "ANNOTATION_NOT_FOUND",
            "A kért megjegyzés nem található.",
            status_code=404,
        )
    name = payload.name if "name" in payload.model_fields_set else current["name"]
    note = payload.note if "note" in payload.model_fields_set else current["note"]
    return repository.upsert_annotation(
        current["analysisId"], current["communityId"], name, note
    )
