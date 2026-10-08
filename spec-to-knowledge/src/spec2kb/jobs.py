"""In-process background jobs (thread pool) with progress, logs, cancellation and persistence.

No external queue/broker: a job is a Python callable run in a ThreadPoolExecutor.
State is written to <data>/docs/<doc>/jobs/<job>.json on every change so that the
UI can show history, and interrupted jobs are marked as failed on restart.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .parser.pipeline import Cancelled
from .schema import utcnow
from .util import atomic_write_json, read_json

log = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]


class JobProgress(BaseModel):
    phase: str = ""
    current: int = 0
    total: int = 0
    message: str = ""
    percent: float = 0.0


class Job(BaseModel):
    id: str
    type: str
    doc_id: str
    title: str = ""
    status: JobStatus = "queued"
    progress: JobProgress = Field(default_factory=JobProgress)
    created_at: str = Field(default_factory=utcnow)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    log: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class BusyError(RuntimeError):
    pass


# weights of pipeline phases for the overall percentage
PHASE_WEIGHTS = {"scan": (0, 5), "parse": (5, 55), "ocr": (55, 62), "assemble": (62, 65),
                 "vision": (65, 92), "validate": (92, 97), "save": (97, 100)}


class JobContext:
    def __init__(self, manager: "JobManager", job: Job):
        self.manager = manager
        self.job = job
        self._cancel = threading.Event()
        self.finishing = False  # work is over; only the document record is being updated

    def progress(self, phase: str, current: int, total: int, message: str = "") -> None:
        lo, hi = PHASE_WEIGHTS.get(phase, (0, 100))
        frac = (current / total) if total else 1.0
        p = self.job.progress
        p.phase, p.current, p.total, p.message = phase, current, total, message
        p.percent = round(lo + (hi - lo) * min(1.0, frac), 1)
        self.manager._persist(self.job, throttle=True)

    def log(self, message: str) -> None:
        self.job.log.append(f"{utcnow()} {message}")
        if len(self.job.log) > 500:
            self.job.log = self.job.log[-500:]
        self.manager._persist(self.job)

    def cancelled(self) -> bool:
        return self._cancel.is_set()


class JobManager:
    def __init__(self, docs_dir: Path, workers: int = 2):
        self.docs_dir = docs_dir
        self.pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="s2k-job")
        self.jobs: dict[str, Job] = {}
        self.contexts: dict[str, JobContext] = {}
        self.active_by_doc: dict[str, str] = {}
        self._lock = threading.RLock()
        self._last_persist: dict[str, float] = {}

    # -- persistence -----------------------------------------------------------
    def _path(self, job: Job) -> Path:
        return self.docs_dir / job.doc_id / "jobs" / f"{job.id}.json"

    def _persist(self, job: Job, throttle: bool = False) -> None:
        import time
        now = time.monotonic()
        if throttle and now - self._last_persist.get(job.id, 0) < 0.5:
            return
        self._last_persist[job.id] = now
        try:
            atomic_write_json(self._path(job), job.model_dump())
        except OSError:  # the document may have been deleted meanwhile
            pass

    def recover(self) -> list[str]:
        """Mark jobs left running/queued by a previous process as failed. Returns affected doc ids."""
        affected = []
        for p in self.docs_dir.glob("*/jobs/*.json"):
            data = read_json(p)
            if not data or data.get("status") not in ("queued", "running"):
                continue
            data["status"] = "failed"
            data["error"] = "서버가 재시작되어 작업이 중단되었습니다. 다시 실행하세요."
            data["finished_at"] = utcnow()
            atomic_write_json(p, data)
            affected.append(data.get("doc_id", ""))
        return affected

    # -- API --------------------------------------------------------------------
    def submit(self, type_: str, doc_id: str, fn: Callable[[JobContext], dict[str, Any] | None],
               title: str = "", params: dict[str, Any] | None = None,
               on_finish: Callable[[Job, str], None] | None = None) -> Job:
        with self._lock:
            active = self.active_by_doc.get(doc_id)
            if active and self.jobs[active].status in ("queued", "running"):
                raise BusyError("이 문서에 이미 실행 중인 작업이 있습니다. 완료되거나 취소된 후 다시 시도하세요.")
            job = Job(id=uuid.uuid4().hex[:12], type=type_, doc_id=doc_id, title=title, params=params or {})
            ctx = JobContext(self, job)
            self.jobs[job.id] = job
            self.contexts[job.id] = ctx
            self.active_by_doc[doc_id] = job.id
            self._persist(job)
        self.pool.submit(self._run, ctx, fn, on_finish)
        return job

    def _run(self, ctx: JobContext, fn: Callable[[JobContext], dict[str, Any] | None],
             on_finish: Callable[[Job, str], None] | None) -> None:
        job = ctx.job
        job.status = "running"
        job.started_at = utcnow()
        self._persist(job)
        final: JobStatus = "failed"
        try:
            if ctx.cancelled():
                raise Cancelled()
            job.result = fn(ctx) or {}
            final = "done"
            job.progress.percent = 100.0
            job.progress.message = "완료"
        except Cancelled:
            final = "cancelled"
            job.error = "사용자가 작업을 취소했습니다."
        except Exception as exc:  # report every failure to the UI
            log.exception("job %s failed", job.id)
            final = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            job.log.append(traceback.format_exc(limit=8))
        finally:
            # update dependent state (document record) before the final status becomes visible,
            # so that anyone polling the job never reads a stale document; while finishing, the
            # job no longer counts as active (the record already shows the outcome)
            ctx.finishing = True
            if on_finish is not None:
                try:
                    on_finish(job, final)
                except Exception:  # pragma: no cover
                    log.exception("on_finish failed for job %s", job.id)
            job.finished_at = utcnow()
            job.status = final
            self._persist(job)
            with self._lock:
                if self.active_by_doc.get(job.doc_id) == job.id:
                    self.active_by_doc.pop(job.doc_id, None)

    def get(self, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job is not None:
            return job
        for p in self.docs_dir.glob(f"*/jobs/{job_id}.json"):
            data = read_json(p)
            if data:
                return Job(**data)
        return None

    def list_for_doc(self, doc_id: str, limit: int = 20) -> list[Job]:
        out: dict[str, Job] = {}
        for p in (self.docs_dir / doc_id / "jobs").glob("*.json"):
            data = read_json(p)
            if data:
                out[data["id"]] = Job(**data)
        for j in self.jobs.values():
            if j.doc_id == doc_id:
                out[j.id] = j
        return sorted(out.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def active_job(self, doc_id: str) -> Job | None:
        jid = self.active_by_doc.get(doc_id)
        job = self.jobs.get(jid) if jid else None
        ctx = self.contexts.get(jid) if jid else None
        if job is None or job.status not in ("queued", "running") or (ctx is not None and ctx.finishing):
            return None
        return job

    def cancel(self, job_id: str) -> bool:
        ctx = self.contexts.get(job_id)
        if ctx is None or ctx.job.status not in ("queued", "running"):
            return False
        ctx._cancel.set()
        ctx.job.progress.message = "취소 요청됨…"
        return True

    def wait(self, job_id: str, timeout: float = 120.0) -> Job:
        import time
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            job = self.jobs.get(job_id)
            if job and job.status in ("done", "failed", "cancelled") and \
                    self.active_by_doc.get(job.doc_id) != job.id:
                return job
            time.sleep(0.05)
        raise TimeoutError(f"job {job_id} did not finish within {timeout}s")

    def shutdown(self) -> None:
        for ctx in self.contexts.values():
            ctx._cancel.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
