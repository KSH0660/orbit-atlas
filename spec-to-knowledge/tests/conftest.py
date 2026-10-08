from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerThread:
    """Run an ASGI app with uvicorn in a background thread (real HTTP on localhost)."""

    def __init__(self, app, port: int | None = None):
        import uvicorn
        self.port = port or free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "ServerThread":
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("server did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture(scope="session")
def samples() -> Path:
    return SAMPLES


@pytest.fixture(scope="session")
def truth():
    def load(name: str) -> dict:
        return json.loads((SAMPLES / f"{name}.truth.json").read_text(encoding="utf-8"))
    return load


@pytest.fixture()
def settings(tmp_path):
    from spec2kb.config import Settings, set_settings
    s = Settings()
    s.data_dir = tmp_path / "data"
    s.workers = 2
    s.default_provider = "mock"
    s.basic_auth = ""
    set_settings(s)
    return s


@pytest.fixture()
def workspace(settings):
    from spec2kb.service import Workspace
    ws = Workspace(settings)
    yield ws
    ws.close()


@pytest.fixture(scope="session")
def profile_store(tmp_path_factory):
    from spec2kb.profiles import ProfileStore
    return ProfileStore(tmp_path_factory.mktemp("profiles"))


@pytest.fixture(scope="session")
def parse_sample(tmp_path_factory, profile_store):
    """Parse + assemble a sample PDF (no vision) and cache the canonical document per (name, profile)."""
    cache: dict[tuple[str, str], object] = {}

    def run(name: str, profile_id: str):
        key = (name, profile_id)
        if key in cache:
            return cache[key]
        from spec2kb.parser import PdfDoc, assemble, parse_pages_raw
        from spec2kb.schema import SourceInfo
        from spec2kb.util import sha256_file
        pdf = SAMPLES / f"{name}.pdf"
        profile = profile_store.resolve(profile_id)
        assets = tmp_path_factory.mktemp(f"assets-{name}-{profile_id}")
        with PdfDoc(pdf) as d:
            n = d.page_count
        raw, furniture, n = parse_pages_raw(pdf, profile, list(range(1, n + 1)), assets)
        src = SourceInfo(filename=pdf.name, sha256=sha256_file(pdf), size_bytes=pdf.stat().st_size, page_count=n)
        doc = assemble(name, name, src, profile, raw, furniture)
        cache[key] = (doc, profile, assets, raw)
        return cache[key]
    return run


def wait_job(client, job_id: str, timeout: float = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise TimeoutError(job_id)
