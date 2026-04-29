"""Tests for maa_x.workers — background worker with durable task store."""

import time
import threading
from maa_x.workers import BackgroundWorker, WorkerTask, create_worker_pool


def test_worker_submit_and_status():
    worker = BackgroundWorker(num_workers=2)
    worker.register_handler("echo", lambda p: p["value"])
    worker.start()

    task_id = worker.submit("echo", {"value": 42})
    time.sleep(0.2)  # let it process

    status = worker.task_status(task_id)
    assert status is not None
    assert status.task_id == task_id
    assert status.status == "completed"
    assert status.result == 42

    worker.stop()


def test_worker_failed_handler():
    worker = BackgroundWorker(num_workers=1)
    worker.register_handler("fail", lambda p: (_ for _ in ()).throw(ValueError("boom")))
    worker.start()

    task_id = worker.submit("fail", {})
    time.sleep(0.2)

    status = worker.task_status(task_id)
    assert status is not None
    assert status.status == "failed"
    assert "boom" in (status.error or "")

    worker.stop()


def test_worker_list_tasks():
    worker = BackgroundWorker(num_workers=1)
    worker.register_handler("noop", lambda p: None)
    worker.start()

    id1 = worker.submit("noop", {})
    id2 = worker.submit("noop", {})
    time.sleep(0.3)

    all_tasks = worker.list_tasks()
    assert len(all_tasks) >= 2

    completed = worker.list_tasks(status_filter="completed")
    assert all(t.status == "completed" for t in completed)

    worker.stop()


def test_worker_stats():
    worker = BackgroundWorker(num_workers=1)
    worker.register_handler("x", lambda p: p)
    worker.start()

    worker.submit("x", {})
    worker.submit("x", {})
    time.sleep(0.3)

    stats = worker.stats()
    assert stats["total"] >= 2
    assert stats["completed"] >= 2

    worker.stop()


def test_create_worker_pool():
    pool = create_worker_pool(num_workers=3)
    assert pool._num_workers == 3
    assert isinstance(pool, BackgroundWorker)