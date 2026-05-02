"""Background worker pool with durable task tracking."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class WorkerTask:
    task_id: str
    handler: str
    payload: dict
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    status: str = "pending"
    result: Any = None
    error: str | None = None

    def duration_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None


class BackgroundWorker:
    """
    Background worker pool with thread-based execution and durable result storage.

    Guarantees:
    - All submitted tasks are tracked by task_id
    - task_status() returns real task state (pending/running/completed/failed)
    - Start/stop lifecycle is managed cleanly

    Parameters
    ----------
    num_workers
        Number of worker threads.
    name
        Worker pool name for logging.
    """

    def __init__(self, num_workers: int = 4, name: str = "bg-worker") -> None:
        self.name = name
        self._queue: queue.Queue[WorkerTask] = queue.Queue()
        self._handlers: dict[str, Callable] = {}
        self._threads: list[threading.Thread] = []
        self._running = False
        self._num_workers = num_workers
        # Durable task store keyed by task_id
        self._tasks: dict[str, WorkerTask] = {}
        self._lock = threading.Lock()

    def register_handler(self, name: str, handler: Callable) -> None:
        self._handlers[name] = handler

    def submit(self, handler: str, payload: dict) -> str:
        task_id = str(uuid.uuid4())
        task = WorkerTask(task_id=task_id, handler=handler, payload=payload)
        with self._lock:
            self._tasks[task_id] = task
        self._queue.put(task)
        return task_id

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"{self.name}-{i}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 5.0) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads.clear()

    def task_status(self, task_id: str) -> WorkerTask | None:
        """Return the real task by ID, or None if not found."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status_filter: str | None = None) -> list[WorkerTask]:
        """List all tasks, optionally filtered by status."""
        with self._lock:
            tasks = list(self._tasks.values())
        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]
        return tasks

    def _worker_loop(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            task.started_at = time.time()
            task.status = "running"

            handler = self._handlers.get(task.handler)
            try:
                task.result = handler(task.payload) if handler else None
                task.status = "completed"
            except Exception as exc:
                task.status = "failed"
                task.error = str(exc)
            finally:
                task.completed_at = time.time()
                self._queue.task_done()

    def stats(self) -> dict[str, Any]:
        """Return runtime statistics."""
        with self._lock:
            tasks = list(self._tasks.values())
        pending = sum(1 for t in tasks if t.status == "pending")
        running = sum(1 for t in tasks if t.status == "running")
        completed = sum(1 for t in tasks if t.status == "completed")
        failed = sum(1 for t in tasks if t.status == "failed")
        return {
            "total": len(tasks),
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "workers": self._num_workers,
            "running_flag": self._running,
        }


def create_worker_pool(num_workers: int = 4) -> BackgroundWorker:
    return BackgroundWorker(num_workers=num_workers)