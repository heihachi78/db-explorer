import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from app.errors import AppError
from app.persistence.repositories import ScanStatusRepository

from .models import ACTIVE_STATES, TaskSnapshot, TaskState


TaskOperation = Callable[["TaskManager"], Awaitable[None]]


def now() -> str:
    return datetime.now(UTC).isoformat()


class TaskManager:
    """Coordinates the single allowed scan or CPU-heavy operation."""

    def __init__(self, repository: ScanStatusRepository) -> None:
        self.repository = repository
        self._snapshot = TaskSnapshot()
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def active(self) -> bool:
        return TaskState(self._snapshot.state) in ACTIVE_STATES

    def snapshot(self) -> dict[str, Any]:
        return asdict(self._snapshot)

    def persist_initial_state(self) -> None:
        self.repository.save(self._snapshot)

    async def start(self, operation: TaskOperation) -> None:
        async with self._lock:
            if self.active:
                raise AppError(
                    "OPERATION_IN_PROGRESS",
                    "Another long-running operation is already in progress.",
                    status_code=409,
                )
            self._snapshot = TaskSnapshot(
                state=TaskState.CONNECTING,
                phase=TaskState.CONNECTING,
                started_at=now(),
            )
            self.repository.save(self._snapshot)
            self._task = asyncio.create_task(self._run(operation))

    async def _run(self, operation: TaskOperation) -> None:
        try:
            await operation(self)
            if self.active:
                self.update(TaskState.SUCCEEDED, message="Operation completed.")
        except asyncio.CancelledError:
            self.update(TaskState.CANCELLED, message="Operation cancelled.")
        except Exception as error:
            error_code = error.code if isinstance(error, AppError) else type(error).__name__
            error_message = error.message if isinstance(error, AppError) else str(error)
            self.update(
                TaskState.FAILED,
                error_code=error_code,
                error_message=error_message,
                message="Operation failed.",
            )

    def update(
        self,
        state: TaskState,
        *,
        message: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
        counters: dict[str, int] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self._snapshot.state = state
        self._snapshot.phase = state if state in ACTIVE_STATES else self._snapshot.phase
        self._snapshot.message = message
        if progress_current is not None:
            self._snapshot.progress_current = progress_current
        if progress_total is not None:
            self._snapshot.progress_total = progress_total
        if counters is not None:
            self._snapshot.counters = counters
        self._snapshot.error_code = error_code
        self._snapshot.error_message = error_message
        if state in {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}:
            self._snapshot.finished_at = now()
        self.repository.save(self._snapshot)

    async def cancel(self) -> None:
        async with self._lock:
            if not self._task or self._task.done() or not self.active:
                raise AppError("NO_ACTIVE_OPERATION", "There is no active operation.", status_code=409)
            self._task.cancel()
            # If cancellation happens before _run gets its first timeslice,
            # its CancelledError handler cannot persist the terminal state.
            await asyncio.sleep(0)
            if self._task.cancelled() and self.active:
                self.update(TaskState.CANCELLED, message="Operation cancelled.")

    async def shutdown(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
