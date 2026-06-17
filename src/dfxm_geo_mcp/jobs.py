"""Generic in-process async job registry (handle pattern) for long operations."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Literal

JobState = Literal["pending", "running", "succeeded", "failed"]


@dataclass
class Job:
    id: str
    state: JobState = "pending"
    progress: float = 0.0
    message: str = ""
    result: Any | None = None
    error: str | None = None
    key: tuple | None = None


class JobRegistry:
    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._by_key: dict[tuple, str] = {}
        self._lock = threading.Lock()

    def submit(self, key: tuple, fn: Callable[[Callable[[float, str], None]], Any]) -> str:
        with self._lock:
            existing = self._by_key.get(key)
            if existing and self._jobs[existing].state in ("pending", "running"):
                return existing
            job = Job(id=uuid.uuid4().hex[:12], key=key)
            self._jobs[job.id] = job
            self._by_key[key] = job.id

        def report(progress: float, message: str) -> None:
            job.progress, job.message = progress, message

        def runner() -> None:
            job.state = "running"
            try:
                job.result = fn(report)
                job.state = "succeeded"
                job.progress = 1.0
            except Exception as exc:  # captured into the job, must not crash the pool
                job.state = "failed"
                job.error = str(exc)

        self._pool.submit(runner)
        return job.id

    def status(self, job_id: str) -> Job:
        return self._jobs[job_id]

    def result(self, job_id: str) -> Any:
        job = self._jobs[job_id]
        if job.state != "succeeded":
            raise RuntimeError(f"job {job_id} is {job.state}: {job.error}")
        return job.result

    def cancel(self, job_id: str) -> bool:
        # Best-effort: work is not cleanly interruptible once running.
        return False
