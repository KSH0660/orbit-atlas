"""FastAPI application: JSON API + static no-build web UI."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import secrets
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .. import __version__
from ..config import Settings, get_settings
from ..profiles import ProfileError
from ..profiles.model import Profile
from ..providers import ProviderConfig, ProviderError
from ..service import ServiceError, Workspace

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, credentials: str):
        super().__init__(app)
        self.user, _, self.password = credentials.partition(":")

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/health":
            return await call_next(request)
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(user, self.user) and secrets.compare_digest(pw, self.password)
            except (binascii.Error, UnicodeDecodeError):
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="spec2kb"'})
        return await call_next(request)


def create_app(settings: Settings | None = None, workspace: Workspace | None = None) -> FastAPI:
    settings = settings or get_settings()
    ws = workspace or Workspace(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        ws.close()

    app = FastAPI(title="Spec-to-Knowledge", version=__version__, docs_url="/api/docs-ui", redoc_url=None,
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.ws = ws
    if settings.basic_auth:
        app.add_middleware(BasicAuthMiddleware, credentials=settings.basic_auth)

    @app.exception_handler(ServiceError)
    async def _svc(_: Request, exc: ServiceError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(ProfileError)
    async def _prof(_: Request, exc: ProfileError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ProviderError)
    async def _prov(_: Request, exc: ProviderError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def _any(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": f"서버 오류: {type(exc).__name__}: {exc}"}, status_code=500)

    # -- system ------------------------------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return ws.health()

    # -- documents ---------------------------------------------------------------------------
    @app.get("/api/docs")
    def list_docs() -> list[dict[str, Any]]:
        return [ws.doc_summary(r) for r in ws.docs.list()]

    @app.post("/api/docs")
    def upload(files: list[UploadFile] = File(...), profile_id: str = Form("jedec"),
               options: str = Form("")) -> dict[str, Any]:
        opts = json.loads(options) if options.strip() else {}
        created, errors = [], []
        for f in files:
            try:
                rec = ws.add_document(f.filename or "document.pdf", f.file, profile_id, opts)
                created.append(rec.model_dump())
            except ServiceError as exc:
                errors.append({"filename": f.filename, "error": str(exc)})
        if not created and errors:
            raise ServiceError("; ".join(f"{e['filename']}: {e['error']}" for e in errors))
        return {"created": created, "errors": errors}

    @app.get("/api/docs/{doc_id}")
    def get_doc(doc_id: str) -> dict[str, Any]:
        rec = ws.get_record(doc_id)
        data = ws.doc_summary(rec)
        doc = ws.docs.canonical(doc_id)
        data["has_result"] = doc is not None
        data["profile_resolved"] = ws.resolve_profile(rec).model_dump(include={"id", "name"})
        if doc is not None:
            data["metadata"] = doc.metadata.model_dump()
            data["metadata_effective"] = doc.effective_metadata().model_dump()
            data["outline"] = doc.outline()
            data["processing"] = doc.processing.model_dump()
        data["jobs"] = [j.model_dump(exclude={"log"}) for j in ws.jobs.list_for_doc(doc_id, 10)]
        return data

    @app.patch("/api/docs/{doc_id}")
    def patch_doc(doc_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        rec = ws.update_document(doc_id, profile_id=body.get("profile_id"), options=body.get("options"),
                                 title=body.get("title"))
        return rec.model_dump()

    @app.delete("/api/docs/{doc_id}")
    def delete_doc(doc_id: str) -> dict[str, str]:
        ws.delete_document(doc_id)
        return {"status": "deleted"}

    @app.get("/api/docs/{doc_id}/source.pdf")
    def source_pdf(doc_id: str) -> FileResponse:
        rec = ws.get_record(doc_id)
        return FileResponse(ws.docs.source_path(doc_id), media_type="application/pdf", filename=rec.filename)

    @app.get("/api/docs/{doc_id}/pages/{page}/image")
    def page_image(doc_id: str, page: int, dpi: int | None = Query(None)) -> FileResponse:
        return FileResponse(ws.page_image(doc_id, page, dpi), media_type="image/png",
                            headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/docs/{doc_id}/pages")
    def pages(doc_id: str) -> list[dict[str, Any]]:
        return ws.pages_overview(doc_id)

    @app.get("/api/docs/{doc_id}/pages/{page}")
    def page_view(doc_id: str, page: int) -> dict[str, Any]:
        return ws.page_view(doc_id, page)

    @app.get("/api/docs/{doc_id}/figures")
    def figures(doc_id: str) -> list[dict[str, Any]]:
        return ws.figures_overview(doc_id)

    @app.get("/api/docs/{doc_id}/canonical")
    def canonical(doc_id: str) -> Response:
        doc = ws._canonical(doc_id)
        return Response(doc.model_dump_json(indent=1), media_type="application/json")

    @app.get("/api/docs/{doc_id}/assets/{name:path}")
    def asset(doc_id: str, name: str) -> FileResponse:
        return FileResponse(ws.asset_file(doc_id, name))

    @app.post("/api/docs/{doc_id}/process")
    def process(doc_id: str) -> dict[str, Any]:
        return ws.start_process(doc_id).model_dump()

    @app.post("/api/docs/{doc_id}/reprocess")
    def reprocess(doc_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return ws.start_reprocess_pages(doc_id, list(body.get("pages") or [])).model_dump()

    @app.post("/api/docs/{doc_id}/figures/redescribe")
    def redescribe(doc_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return ws.start_redescribe(doc_id, list(body.get("figure_ids") or []), body.get("image_type") or None,
                                   body.get("prompt_extra")).model_dump()

    @app.patch("/api/docs/{doc_id}/blocks/{block_id}")
    def edit_block(doc_id: str, block_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        ws.edit_block(doc_id, block_id, body.get("md_override"))
        return {"status": "ok"}

    @app.patch("/api/docs/{doc_id}/tables/{table_id}")
    def edit_table(doc_id: str, table_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        ws.edit_table(doc_id, table_id, body.get("md_override"))
        return {"status": "ok"}

    @app.patch("/api/docs/{doc_id}/figures/{figure_id}")
    def edit_figure(doc_id: str, figure_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        ws.edit_figure(doc_id, figure_id, body)
        return {"status": "ok"}

    @app.patch("/api/docs/{doc_id}/metadata")
    def edit_metadata(doc_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        doc = ws.edit_metadata(doc_id, body)
        return doc.effective_metadata().model_dump()

    @app.get("/api/docs/{doc_id}/issues")
    def issues(doc_id: str) -> dict[str, Any]:
        doc = ws._canonical(doc_id)
        from ..validator import summarize
        return {"summary": summarize(doc), "issues": [i.model_dump() for i in doc.issues]}

    @app.patch("/api/docs/{doc_id}/issues/{issue_id}")
    def issue_status(doc_id: str, issue_id: str, body: dict[str, Any] = Body(...)) -> dict[str, str]:
        ws.set_issue_status(doc_id, issue_id, str(body.get("status", "")))
        return {"status": "ok"}

    @app.post("/api/docs/{doc_id}/validate")
    def validate(doc_id: str) -> dict[str, Any]:
        return ws.revalidate(doc_id)

    @app.post("/api/docs/{doc_id}/preview")
    def build_preview(doc_id: str) -> dict[str, Any]:
        return ws.build_preview(doc_id)

    @app.get("/api/docs/{doc_id}/preview/file")
    def preview_file(doc_id: str, path: str = Query(...)) -> dict[str, Any]:
        return ws.preview_file(doc_id, path)

    @app.get("/api/docs/{doc_id}/preview/raw")
    def preview_raw(doc_id: str, path: str = Query(...)) -> FileResponse:
        return FileResponse(ws.preview_raw(doc_id, path))

    @app.get("/api/docs/{doc_id}/export.zip")
    def export_doc(doc_id: str, layout: str | None = Query(None)) -> FileResponse:
        p = ws.export_zip([doc_id], layout=layout)
        return FileResponse(p, media_type="application/zip", filename=p.name)

    @app.post("/api/export")
    def export_kb(body: dict[str, Any] = Body(...)) -> FileResponse:
        p = ws.export_zip(list(body.get("doc_ids") or []), str(body.get("kb_name") or ""), body.get("layout"))
        return FileResponse(p, media_type="application/zip", filename=p.name)

    # -- jobs -------------------------------------------------------------------------------------
    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        j = ws.jobs.get(job_id)
        if j is None:
            raise HTTPException(404, "작업을 찾을 수 없습니다.")
        return j.model_dump()

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        return {"cancelled": ws.jobs.cancel(job_id)}

    # -- profiles ---------------------------------------------------------------------------------
    @app.get("/api/profiles")
    def profiles() -> list[dict[str, Any]]:
        return ws.profiles.list()

    @app.get("/api/profiles-schema")
    def profile_schema() -> dict[str, Any]:
        return Profile.model_json_schema()

    @app.get("/api/profiles/{pid}")
    def profile(pid: str) -> dict[str, Any]:
        raw = ws.profiles.get_raw(pid)
        return {"raw": raw, "resolved": ws.profiles.resolve(pid).model_dump(),
                "parent_resolved": ws.profiles.parent_resolved_dict(pid), "chain": ws.profiles.chain(pid)}

    @app.post("/api/profiles")
    def create_profile(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return ws.profiles.create(str(body.get("id", "")).strip(), str(body.get("name") or body.get("id")),
                                  body.get("base_id") or None, str(body.get("mode", "inherit")),
                                  str(body.get("description", "")))

    @app.put("/api/profiles/{pid}")
    def update_profile(pid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if "extends" in body:
            kwargs["extends"] = body["extends"]
        return ws.profiles.update(pid, name=body.get("name"), description=body.get("description"),
                                  overrides=body.get("overrides"), resolved=body.get("resolved"), **kwargs)

    @app.delete("/api/profiles/{pid}")
    def delete_profile(pid: str) -> dict[str, str]:
        in_use = [r.filename for r in ws.docs.list() if r.profile_id == pid]
        if in_use:
            raise ServiceError(f"이 프로필을 사용하는 문서가 있습니다: {', '.join(in_use[:5])}")
        ws.profiles.delete(pid)
        return {"status": "deleted"}

    @app.get("/api/profiles/{pid}/export")
    def export_profile(pid: str, resolved: bool = Query(False)) -> Response:
        data = ws.profiles.resolve(pid).model_dump() if resolved else ws.profiles.get_raw(pid)
        return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="profile-{pid}.json"'})

    @app.post("/api/profiles-import")
    def import_profile(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return ws.profiles.import_raw(body.get("profile") or {}, bool(body.get("overwrite")))

    # -- providers ------------------------------------------------------------------------------
    @app.get("/api/providers")
    def providers() -> list[dict[str, Any]]:
        return [p.public() for p in ws.providers.list()]

    @app.get("/api/providers-schema")
    def provider_schema() -> dict[str, Any]:
        return ProviderConfig.model_json_schema()

    @app.post("/api/providers")
    def create_provider(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return ws.providers.upsert(body, create=True).public()

    @app.put("/api/providers/{pid}")
    def update_provider(pid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        body = dict(body)
        body["id"] = pid
        return ws.providers.upsert(body, create=False).public()

    @app.delete("/api/providers/{pid}")
    def delete_provider(pid: str) -> dict[str, str]:
        ws.providers.delete(pid)
        return {"status": "deleted"}

    @app.post("/api/providers/{pid}/test")
    def test_provider(pid: str) -> dict[str, Any]:
        return ws.test_provider(pid)

    # -- static UI -----------------------------------------------------------------------------
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
