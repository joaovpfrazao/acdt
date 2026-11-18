"""Async job pattern for long tool calls: ``start → job_id → status → result``.

Jobs run in a small worker pool (default 1 worker: the analysis code uses matplotlib and writes files, so jobs
are serialised; ``ACDT_MCP_WORKERS`` raises it). Each job keeps a bounded log (the ``log`` callbacks of the
studies), its run id, timing and result/error. Jobs live in memory; their *results* are persisted by the run
registry, so a finished job can always be re-read with ``get_run`` after a server restart."""
from __future__ import annotations

import os
import secrets
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .registry import now_iso


class Job:
    def __init__(self, tool: str, args: dict):
        self.id = f"job-{secrets.token_hex(4)}"
        self.tool, self.args = tool, args
        self.status = "queued"
        self.created, self.started, self.finished = now_iso(), None, None
        self.t0: float | None = None
        self.result: Any = None
        self.error: str | None = None
        self.run_id: str | None = None
        self.log: deque[str] = deque(maxlen=200)
        self.done = threading.Event()

    def info(self, with_result: bool = False) -> dict:
        d = {"job_id": self.id, "tool": self.tool, "status": self.status, "created": self.created,
             "started": self.started, "finished": self.finished, "run_id": self.run_id,
             "elapsed_s": (round(time.time() - self.t0, 1) if self.t0 and not self.done.is_set() else None),
             "log_tail": list(self.log)[-15:]}
        if self.error:
            d["error"] = self.error
        if with_result and self.status == "done":
            d["result"] = self.result
        return d


class JobManager:
    def __init__(self, workers: int | None = None):
        self.pool = ThreadPoolExecutor(max_workers=workers or int(os.environ.get("ACDT_MCP_WORKERS", "1")),
                                       thread_name_prefix="acdt-job")
        self.jobs: dict[str, Job] = {}

    def submit(self, tool: str, fn: Callable[..., Any], args: dict) -> Job:
        """``fn(job, **args)`` runs in the pool; it may set ``job.run_id`` and append to ``job.log``."""
        j = Job(tool, args)
        self.jobs[j.id] = j

        def _run():
            j.status, j.started, j.t0 = "running", now_iso(), time.time()
            try:
                j.result = fn(j, **args)
                j.status = "done"
            except Exception as ex:  # report, never hide
                j.error = f"{type(ex).__name__}: {ex}"
                j.log.append(traceback.format_exc(limit=4))
                j.status = "failed"
            finally:
                j.finished = now_iso()
                j.done.set()
        self.pool.submit(_run)
        return j

    def get(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise KeyError(f"job {job_id!r} unknown (jobs are kept in memory; after a restart use get_run)")
        return self.jobs[job_id]

    def wait(self, job_id: str, timeout_s: float) -> Job:
        j = self.get(job_id)
        j.done.wait(max(0.0, timeout_s))
        return j

    def list(self) -> list[dict]:
        return [j.info() for j in self.jobs.values()]


MANAGER = JobManager()
