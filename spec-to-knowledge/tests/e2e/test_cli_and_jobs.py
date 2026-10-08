from __future__ import annotations

import json
import subprocess
import sys
import time
import zipfile

from spec2kb.service import Workspace
from spec2kb.util import atomic_write_json


def run_cli(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "spec2kb", *args], capture_output=True, text=True, cwd=cwd,
                          env=env, timeout=300)


def test_cli_convert_schema_doctor(tmp_path, samples):
    out = tmp_path / "kb.zip"
    r = run_cli("convert", str(samples / "jedec_like_spec.pdf"), str(samples / "customer_spec.pdf"),
                "--profile", "jedec", "--out", str(out), "--kb-name", "CLI KB", "--quiet", "--fail-on-error")
    assert r.returncode == 0, r.stderr
    assert "OK " in r.stdout and out.exists()
    names = zipfile.ZipFile(out).namelist()
    assert "cli-kb/mkdocs.yml" in names and "cli-kb/docs/jesd-syn-01/index.md" in names
    r = run_cli("convert", str(samples / "jedec_like_spec.pdf"), "--no-vision", "--layout", "wiki", "--pages", "1-6",
                "--out", str(tmp_path / "w.zip"), "--quiet")
    assert r.returncode == 0, r.stderr
    assert any(n.endswith("Home.md") for n in zipfile.ZipFile(tmp_path / "w.zip").namelist())
    r = run_cli("schema", "--out", str(tmp_path / "schema.json"))
    assert r.returncode == 0 and json.loads((tmp_path / "schema.json").read_text())["title"] == "CanonicalDocument"
    r = run_cli("doctor", "--data-dir", str(tmp_path / "d"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[FAIL]" not in r.stdout
    r = run_cli("convert", str(tmp_path / "missing.pdf"), "--quiet")
    assert r.returncode != 0


def test_restart_marks_interrupted_jobs_failed(settings, samples):
    ws = Workspace(settings)
    with open(samples / "customer_spec.pdf", "rb") as fh:
        rec = ws.add_document("customer_spec.pdf", fh, "customer")
    rec.status = "processing"
    ws.docs.save_record(rec)
    atomic_write_json(settings.docs_dir / rec.id / "jobs" / "deadbeef.json",
                      {"id": "deadbeef", "type": "process", "doc_id": rec.id, "status": "running"})
    ws.close()
    ws2 = Workspace(settings)
    try:
        assert ws2.docs.record(rec.id).status == "failed"
        assert ws2.jobs.get("deadbeef").status == "failed"
        job = ws2.start_process(rec.id)  # the document can be processed again
        assert ws2.jobs.wait(job.id).status == "done"
    finally:
        ws2.close()


def test_cancel_running_job(workspace, samples):
    ws = workspace
    ws.providers.upsert({"id": "slow", "name": "slow", "type": "mock", "extra_body": {"mock_latency_ms": 1500}}, create=True)
    with open(samples / "jedec_like_spec.pdf", "rb") as fh:
        rec = ws.add_document("jedec_like_spec.pdf", fh, "jedec", {"vision": {"provider": "slow", "concurrency": 1}})
    job = ws.start_process(rec.id)
    deadline = time.monotonic() + 30
    while ws.jobs.get(job.id).progress.phase != "vision" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert ws.jobs.cancel(job.id)
    final = ws.jobs.wait(job.id, 60)
    assert final.status == "cancelled"
    assert ws.docs.record(rec.id).status == "cancelled"
    # nothing half-written: no canonical document from the cancelled first run
    assert ws.docs.canonical(rec.id) is None


def test_job_state_consistent_while_finishing(tmp_path):
    """While the document record is being updated, the job no longer counts as active, and the
    final status only becomes visible after the record update (no stale reads either way)."""
    import threading

    from spec2kb.jobs import JobManager
    jm = JobManager(tmp_path, workers=1)
    seen = {}
    gate = threading.Event()

    def on_finish(job, status):
        seen["active_during_finish"] = jm.active_job("doc1")
        seen["status_during_finish"] = job.status
        gate.wait(5)

    job = jm.submit("process", "doc1", lambda ctx: {"ok": True}, on_finish=on_finish)
    deadline = time.monotonic() + 5
    while "status_during_finish" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    assert seen["active_during_finish"] is None        # UI routes to the result, not to a running job
    assert jm.get(job.id).status == "running"          # pollers do not see "done" before the record
    gate.set()
    assert jm.wait(job.id, 5).status == "done"
    jm.shutdown()
