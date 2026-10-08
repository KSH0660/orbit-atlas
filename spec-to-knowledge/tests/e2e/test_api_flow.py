"""End-to-end through the HTTP API: upload -> process -> review/edit -> reprocess -> validate -> preview -> ZIP."""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

import pytest
from fastapi.testclient import TestClient

from spec2kb.web.app import create_app

from ..conftest import ServerThread, wait_job


@pytest.fixture()
def client(settings, workspace):
    app = create_app(settings, workspace)
    with TestClient(app) as c:
        yield c


def upload(client, samples: Path, name: str, profile: str) -> dict:
    with open(samples / name, "rb") as fh:
        r = client.post("/api/docs", files=[("files", (name, fh, "application/pdf"))], data={"profile_id": profile})
    assert r.status_code == 200, r.text
    return r.json()["created"][0]


def process(client, doc_id: str) -> dict:
    job = client.post(f"/api/docs/{doc_id}/process").json()
    done = wait_job(client, job["id"])
    assert done["status"] == "done", done
    return done


def test_full_flow(client, samples, tmp_path):
    jedec = upload(client, samples, "jedec_like_spec.pdf", "jedec")
    cust = upload(client, samples, "customer_spec.pdf", "customer")
    scan = upload(client, samples, "scanned_addendum.pdf", "general")
    for d in (jedec, cust, scan):
        process(client, d["id"])
    docs = {d["id"]: d for d in client.get("/api/docs").json()}
    for d in (jedec, cust):
        s = docs[d["id"]]["summary"]
        assert docs[d["id"]]["status"] == "ready"
        assert s["errors"] == 0, client.get(f"/api/docs/{d['id']}/issues").json()
    assert docs[jedec["id"]]["summary"]["tables"] == 3 and docs[jedec["id"]]["summary"]["figures"] == 3
    assert docs[jedec["id"]]["title"] == "Synthetic DDR6 SDRAM Specification"
    scan_issues = {i["code"] for i in client.get(f"/api/docs/{scan['id']}/issues").json()["issues"]}
    assert {"scanned_page", "ocr_unverified"} <= scan_issues

    jid = jedec["id"]
    # page view: original image + blocks with rendered html
    assert client.get(f"/api/docs/{jid}/pages/6/image").headers["content-type"] == "image/png"
    pv = client.get(f"/api/docs/{jid}/pages/6").json()
    types = [b["block"]["type"] for b in pv["blocks"]]
    assert "table" in types and "heading" in types
    tbl = next(b for b in pv["blocks"] if b["block"]["type"] == "table" and "Recommended" in b["markdown"])
    assert '<th colspan="3">Rating</th>' in tbl["html"]

    # edit a block: drop a value -> validation error appears on that page
    para = next(b for b in pv["blocks"] if "referenced to VSS" in b["markdown"])
    r = client.patch(f"/api/docs/{jid}/blocks/{para['block']['id']}", json={"md_override": "All voltages are referenced to ground."})
    assert r.status_code == 200
    issues = client.get(f"/api/docs/{jid}/issues").json()["issues"]
    sig = next(i for i in issues if i["code"] == "signal_missing" and i["page"] == 6)
    assert "VSS" in sig["message"]
    # ignore it, then revalidate: status persists
    client.patch(f"/api/docs/{jid}/issues/{sig['id']}", json={"status": "ignored"})
    client.post(f"/api/docs/{jid}/validate")
    again = next(i for i in client.get(f"/api/docs/{jid}/issues").json()["issues"] if i["id"] == sig["id"])
    assert again["status"] == "ignored"

    # reprocess page 6: the edit is re-applied to the same block id
    job = client.post(f"/api/docs/{jid}/reprocess", json={"pages": [6]}).json()
    assert wait_job(client, job["id"])["status"] == "done"
    pv = client.get(f"/api/docs/{jid}/pages/6").json()
    assert any(b["edited"] and "referenced to ground" in b["markdown"] for b in pv["blocks"])

    # figure: change type + redescribe with reviewer instructions; then write a reviewed description
    job = client.post(f"/api/docs/{jid}/figures/redescribe",
                      json={"figure_ids": ["fig-3"], "image_type": "state_diagram", "prompt_extra": "List PDE/PDX."}).json()
    assert wait_job(client, job["id"])["status"] == "done"
    canon = client.get(f"/api/docs/{jid}/canonical").json()
    f3 = next(f for f in canon["figures"] if f["id"] == "fig-3")
    assert f3["image_type"] == "state_diagram" and f3["image_type_source"] == "user"
    assert f3["description"]["status"] in ("ok", "uncertain") and f3["prompt_extra"] == "List PDE/PDX."
    assert [s["key"] for s in f3["description"]["sections"]][:2] == ["states", "transitions"]
    client.patch(f"/api/docs/{jid}/figures/fig-1", json={"description_override": "Ball map, top view. A1 = VDD."})
    client.patch(f"/api/docs/{jid}/metadata", json={"revision": "1.0a"})

    # busy guard: editing while a job runs is rejected
    job = client.post(f"/api/docs/{jid}/reprocess", json={"pages": [3, 4, 5]}).json()
    r = client.patch(f"/api/docs/{jid}/blocks/{para['block']['id']}", json={"md_override": "x"})
    if wait_job(client, job["id"])["status"] == "done" and r.status_code != 200:
        assert r.status_code == 409

    # preview
    info = client.post(f"/api/docs/{jid}/preview").json()
    assert info["index"].endswith("index.md") and len(info["files"]) == 9
    f = client.get(f"/api/docs/{jid}/preview/file", params={"path": info["files"][5]["path"]}).json()
    assert "<table>" in f["html"] or "<table" in f["html"]
    assert "/api/docs/" in f["html"]  # image links rewritten to the API

    # export a two-document knowledge base and inspect it
    r = client.post("/api/export", json={"doc_ids": [jid, cust["id"]], "kb_name": "Memory KB", "layout": "mkdocs"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    root = names[0].split("/")[0]
    assert root == "memory-kb"
    for must in ("mkdocs.yml", "README.md", "docs/index.md", "docs/jesd-syn-01/index.md",
                 "docs/jesd-syn-01/assets/fig-2.png", "_meta/kb.json", "_meta/jesd-syn-01/source_map.json",
                 "_meta/jesd-syn-01/canonical.json", "_meta/jesd-syn-01/profile.json",
                 "_meta/jesd-syn-01/validation_report.md", "_meta/crs-acme-0042/source_map.json",
                 "_meta/providers.json"):
        assert f"{root}/{must}" in names, must
    out = tmp_path / "kb"
    zf.extractall(out)
    kb = out / root
    _check_links(kb)
    sec = (kb / "docs/jesd-syn-01/07-command-and-timing.md").read_text(encoding="utf-8")
    assert 'revision: "1.0a"' in sec
    assert "![Figure 2 — Read Burst Timing (BL16, RL = 22)](assets/fig-2.png)" in sec
    elec = (kb / "docs/jesd-syn-01/05-pinout-and-signal-description.md").read_text(encoding="utf-8")
    assert "Reviewed description" in elec and "A1 = VDD." in elec
    providers = (kb / "_meta/providers.json").read_text(encoding="utf-8")
    assert '"api_key": ""' in providers or "api_key" not in providers
    if shutil.which("mkdocs") or _has_module("mkdocs"):
        res = subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "-q", "-d", str(tmp_path / "site")],
                             cwd=kb, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert (tmp_path / "site/jesd-syn-01/06-electrical-characteristics.html").exists()

    # wiki layout export of a single document
    r = client.get(f"/api/docs/{cust['id']}/export.zip", params={"layout": "wiki"})
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    wroot = zf.namelist()[0].split("/")[0]
    zf.extractall(tmp_path / "wiki")
    wkb = tmp_path / "wiki" / wroot
    assert (wkb / "Home.md").exists() and (wkb / "crs-acme-0042.md").exists()
    _check_links(wkb, wiki=True)


def _has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def _check_links(kb: Path, wiki: bool = False) -> None:
    all_files = {p.relative_to(kb).as_posix() for p in kb.rglob("*") if p.is_file()}
    for p in kb.rglob("*.md"):
        if "_meta" in p.parts:
            continue
        text = p.read_text(encoding="utf-8")
        base = PurePosixPath(p.relative_to(kb).as_posix()).parent
        for m in re.finditer(r"!?\[[^\]]*\]\(([^)\s]+)\)", text):
            target = m.group(1).split("#")[0]
            if not target or target.startswith(("http:", "https:")):
                continue
            resolved = str(PurePosixPath(*(base / target).parts))
            parts: list[str] = []
            for part in resolved.split("/"):
                if part == "..":
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            resolved = "/".join(parts)
            ok = resolved in all_files or (wiki and resolved + ".md" in all_files)
            assert ok, f"{p.name}: broken link {target}"


def test_upload_validation_errors(client, tmp_path):
    r = client.post("/api/docs", files=[("files", ("notes.txt", b"hello", "text/plain"))], data={"profile_id": "jedec"})
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    r = client.post("/api/docs", files=[("files", ("fake.pdf", b"not a pdf at all", "application/pdf"))], data={"profile_id": "jedec"})
    assert r.status_code == 400 and "PDF 형식" in r.json()["detail"]
    broken = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF"
    r = client.post("/api/docs", files=[("files", ("broken.pdf", broken, "application/pdf"))], data={"profile_id": "jedec"})
    assert r.status_code == 400
    r = client.post("/api/docs", files=[("files", ("x.pdf", b"%PDF-1.4", "application/pdf"))], data={"profile_id": "nope"})
    assert r.status_code == 400 and "프로필" in r.json()["detail"]
    assert client.get("/api/docs/dmissing000").status_code == 404
    assert client.get("/api/docs/../etc").status_code in (404, 400)


def test_invalid_options_and_vision_failure(client, samples):
    d = upload(client, samples, "jedec_like_spec.pdf", "jedec")
    r = client.patch(f"/api/docs/{d['id']}", json={"options": {"parsing": {"page_range": "50-60"}}})
    assert r.status_code == 400 and "페이지" in r.json()["detail"]
    # provider that always fails -> document still completes, figures marked failed, errors reported
    client.post("/api/providers", json={"id": "broken", "name": "Broken", "type": "mock", "extra_body": {"mock_fail": "always"}})
    client.patch(f"/api/docs/{d['id']}", json={"options": {"vision": {"provider": "broken"}, "parsing": {"page_range": "8-9"}}})
    process(client, d["id"])
    issues = client.get(f"/api/docs/{d['id']}/issues").json()["issues"]
    failed = [i for i in issues if i["code"] == "vision_failed"]
    assert len(failed) == 2 and "mock_fail" in failed[0]["message"]
    gaps = [i for i in issues if i["code"] == "figure_number_gap"]
    assert all(i["severity"] == "info" for i in gaps)  # partial page range -> informational only
    # unknown provider id -> failed with a clear reason, job still succeeds
    client.patch(f"/api/docs/{d['id']}", json={"options": {"vision": {"provider": "does-not-exist"}, "parsing": {"page_range": "8"}}})
    process(client, d["id"])
    issues = client.get(f"/api/docs/{d['id']}/issues").json()["issues"]
    assert any(i["code"] == "vision_failed" and "does-not-exist" in i["message"] for i in issues)


def test_profile_and_provider_api(client):
    assert {p["id"] for p in client.get("/api/profiles").json()} >= {"general", "jedec", "customer"}
    r = client.post("/api/profiles", json={"id": "team-x", "name": "Team X", "base_id": "jedec", "mode": "inherit"})
    assert r.status_code == 200
    data = client.get("/api/profiles/team-x").json()
    resolved = data["resolved"]
    resolved["markdown"]["table_format"] = "gfm"
    r = client.put("/api/profiles/team-x", json={"resolved": {k: resolved[k] for k in ("parsing", "vision", "markdown", "validation")}})
    assert r.status_code == 200 and r.json()["overrides"] == {"markdown": {"table_format": "gfm"}}
    r = client.put("/api/profiles/jedec", json={"name": "x"})
    assert r.status_code == 400
    exp = client.get("/api/profiles/team-x/export").json()
    exp["id"] = "team-y"
    assert client.post("/api/profiles-import", json={"profile": exp}).status_code == 200
    assert client.get("/api/profiles-schema").json()["title"] == "Profile"
    r = client.post("/api/providers", json={"id": "gw", "name": "GW", "type": "openai", "base_url": "http://127.0.0.1:1/v1",
                                            "model": "m", "api_key": "secret", "max_retries": 0, "timeout_s": 2})
    assert r.status_code == 200 and r.json()["api_key"] == "" and r.json()["api_key_set"]
    t = client.post("/api/providers/gw/test").json()
    assert t["ok"] is False and "연결 실패" in t["error"]
    assert client.post("/api/providers/mock/test").json()["ok"] is True


def test_http_provider_end_to_end(client, samples):
    """The real OpenAI-compatible adapter talks HTTP to the mock model server during processing."""
    from spec2kb.mockserver import create_mock_app
    mock_app = create_mock_app(api_key="k-123")
    with ServerThread(mock_app) as srv:
        import os
        os.environ["TEST_LLM_KEY"] = "k-123"
        r = client.post("/api/providers", json={"id": "gw-mock", "name": "GW mock", "type": "openai",
                                                "base_url": srv.url + "/v1", "model": "mock-vision-1",
                                                "api_key_env": "TEST_LLM_KEY", "max_retries": 1})
        assert r.status_code == 200
        d = upload(client, samples, "jedec_like_spec.pdf", "jedec")
        client.patch(f"/api/docs/{d['id']}", json={"options": {"vision": {"provider": "gw-mock"}}})
        process(client, d["id"])
        canon = client.get(f"/api/docs/{d['id']}/canonical").json()
        statuses = {f["id"]: (f["description"]["status"], f["description"]["provider"]) for f in canon["figures"]}
        assert statuses == {"fig-1": ("uncertain", "gw-mock"), "fig-2": ("ok", "gw-mock"), "fig-3": ("ok", "gw-mock")}
        assert len(mock_app.state.calls) == 3 and all(c["images"] == 1 for c in mock_app.state.calls)


def test_basic_auth(settings, workspace):
    settings.basic_auth = "admin:pw"
    app = create_app(settings, workspace)
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/docs").status_code == 401
        assert c.get("/api/docs", auth=("admin", "pw")).status_code == 200
        assert c.get("/", auth=("admin", "bad")).status_code == 401
