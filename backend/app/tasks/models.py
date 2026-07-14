from dataclasses import dataclass, field
from enum import StrEnum


class TaskState(StrEnum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    DISCOVERING_SCHEMAS = "DISCOVERING_SCHEMAS"
    EXTRACTING_OBJECTS = "EXTRACTING_OBJECTS"
    EXTRACTING_RELATIONSHIPS = "EXTRACTING_RELATIONSHIPS"
    NORMALIZING = "NORMALIZING"
    VALIDATING = "VALIDATING"
    PUBLISHING = "PUBLISHING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_STATES = {
    TaskState.CONNECTING,
    TaskState.DISCOVERING_SCHEMAS,
    TaskState.EXTRACTING_OBJECTS,
    TaskState.EXTRACTING_RELATIONSHIPS,
    TaskState.NORMALIZING,
    TaskState.VALIDATING,
    TaskState.PUBLISHING,
}


@dataclass(slots=True)
class TaskSnapshot:
    state: str = TaskState.IDLE
    phase: str | None = None
    progress_current: int = 0
    progress_total: int | None = None
    message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    counters: dict[str, int] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
