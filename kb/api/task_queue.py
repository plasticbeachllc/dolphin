"""Task queue for async KB indexing operations."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IndexTask:
    """Represents a single indexing task."""

    task_id: str
    repo: str
    files: list[str]
    status: TaskStatus = TaskStatus.QUEUED
    progress: int = 0
    total: int = 0
    indexed: int = 0  # Track indexed chunks during processing
    skipped: int = 0  # Track skipped chunks during processing
    current_file: str | None = None  # Currently processing file path
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict | None = None


class TaskQueue:
    """In-memory task queue for KB indexing operations."""

    def __init__(self):
        self.tasks: dict[str, IndexTask] = {}
        self._lock = asyncio.Lock()

    def create_task(self, repo: str, files: list[str]) -> IndexTask:
        """Create a new indexing task."""
        task = IndexTask(
            task_id=str(uuid.uuid4()), repo=repo, files=files, total=len(files)
        )
        self.tasks[task.task_id] = task
        return task

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        progress: int | None = None,
        indexed: int | None = None,
        skipped: int | None = None,
        current_file: str | None = None,
        error: str | None = None,
        result: dict | None = None,
    ):
        """Update task status and progress."""
        async with self._lock:
            if task_id not in self.tasks:
                return

            task = self.tasks[task_id]

            if status:
                task.status = status
                if status == TaskStatus.PROCESSING and not task.started_at:
                    task.started_at = datetime.now(UTC)
                elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    task.completed_at = datetime.now(UTC)

            if progress is not None:
                task.progress = progress

            if indexed is not None:
                task.indexed = indexed

            if skipped is not None:
                task.skipped = skipped

            if current_file is not None:
                task.current_file = current_file

            if error:
                task.error = error

            if result:
                task.result = result

    def get_task(self, task_id: str) -> IndexTask | None:
        """Get task by ID."""
        return self.tasks.get(task_id)

    def get_all_tasks(self, repo: str | None = None) -> list[IndexTask]:
        """Get all tasks, optionally filtered by repo."""
        tasks = list(self.tasks.values())
        if repo:
            tasks = [t for t in tasks if t.repo == repo]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    async def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """Remove completed/failed tasks older than max_age."""
        async with self._lock:
            now = datetime.now(UTC)
            to_remove = []

            for task_id, task in self.tasks.items():
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    if task.completed_at:
                        age = (now - task.completed_at).total_seconds()
                        if age > max_age_seconds:
                            to_remove.append(task_id)

            for task_id in to_remove:
                del self.tasks[task_id]

            return len(to_remove)


# Global task queue instance
_task_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    """Get the global task queue instance."""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
