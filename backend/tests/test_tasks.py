import asyncio
from pathlib import Path

import pytest

from app.persistence.database import initialize_database
from app.persistence.repositories import ScanStatusRepository
from app.tasks.manager import TaskManager
from app.tasks.models import TaskState


@pytest.mark.asyncio
async def test_task_manager_completes_operation(tmp_path: Path) -> None:
    path = tmp_path / "graph.db"
    initialize_database(path)
    manager = TaskManager(ScanStatusRepository(path))

    async def operation(task: TaskManager) -> None:
        task.update(TaskState.EXTRACTING_OBJECTS, progress_current=2, progress_total=2)

    await manager.start(operation)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert manager.snapshot()["state"] == TaskState.SUCCEEDED


@pytest.mark.asyncio
async def test_task_manager_cancels_operation(tmp_path: Path) -> None:
    path = tmp_path / "graph.db"
    initialize_database(path)
    manager = TaskManager(ScanStatusRepository(path))

    async def operation(_: TaskManager) -> None:
        await asyncio.Event().wait()

    await manager.start(operation)
    await manager.cancel()
    await asyncio.sleep(0)

    assert manager.snapshot()["state"] == TaskState.CANCELLED
