"""Command line interface.

  spec2kb serve                 web UI + API (S2K_* environment variables)
  spec2kb convert a.pdf b.pdf   headless batch conversion -> ZIP
  spec2kb mock-server           OpenAI-compatible mock model API (offline verification)
  spec2kb doctor                installation / environment self-check
  spec2kb profiles ...          list / show / export / import profiles
  spec2kb providers ...         list / test model providers
  spec2kb schema                print the canonical JSON schema
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .config import Settings, set_settings


def _settings(args: argparse.Namespace) -> Settings:
    s = Settings()
    if getattr(args, "data_dir", None):
        s.data_dir = Path(args.data_dir).resolve()
    if getattr(args, "host", None):
        s.host = args.host
    if getattr(args, "port", None):
        s.port = args.port
    if getattr(args, "workers", None):
        s.workers = args.workers
    set_settings(s)
    return s


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .web.app import create_app
    s = _settings(args)
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(s)
    print(f"Spec-to-Knowledge {__version__}  http://{s.host}:{s.port}  (data: {s.data_dir})", flush=True)
    uvicorn.run(app, host=s.host, port=s.port, log_level=s.log_level.lower(), access_log=False)
    return 0


def cmd_mock_server(args: argparse.Namespace) -> int:
    import uvicorn

    from .mockserver import create_mock_app
    print(f"Mock model API on http://{args.host}:{args.port}/v1 (OpenAI-compatible), /ocr (custom JSON)", flush=True)
    uvicorn.run(create_mock_app(args.api_key or ""), host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    from .service import ServiceError, Workspace
    tmp = None
    if not args.data_dir:
        tmp = tempfile.TemporaryDirectory(prefix="spec2kb-")
        args.data_dir = tmp.name
    s = _settings(args)
    logging.basicConfig(level=logging.WARNING)
    ws = Workspace(s)
    options: dict = {}
    if args.pages:
        options.setdefault("parsing", {})["page_range"] = args.pages
    if args.provider:
        options.setdefault("vision", {})["provider"] = args.provider
    if args.no_vision:
        options.setdefault("vision", {})["enabled"] = False
    if args.options:
        options = json.loads(Path(args.options).read_text(encoding="utf-8")) if os.path.exists(args.options) \
            else json.loads(args.options)
    exit_code = 0
    doc_ids = []
    try:
        for pdf in args.inputs:
            with open(pdf, "rb") as fh:
                rec = ws.add_document(os.path.basename(pdf), fh, args.profile, options)
            t0 = time.monotonic()
            job = ws.start_process(rec.id)
            last = ""
            while True:
                j = ws.jobs.get(job.id)
                msg = f"{j.progress.percent:5.1f}% {j.progress.message}"
                if msg != last and not args.quiet:
                    print(f"  [{os.path.basename(pdf)}] {msg}", file=sys.stderr, flush=True)
                    last = msg
                if j.status in ("done", "failed", "cancelled"):
                    break
                time.sleep(0.2)
            if j.status != "done":
                print(f"FAILED {pdf}: {j.error}", file=sys.stderr)
                exit_code = 2
                continue
            summ = ws.get_record(rec.id).summary
            print(f"OK {pdf}: {time.monotonic() - t0:.1f}s, pages {summ.get('pages')}, headings {summ.get('headings')}, "
                  f"tables {summ.get('tables')}, figures {summ.get('figures')}, errors {summ.get('errors')}, "
                  f"warnings {summ.get('warnings')}")
            if args.fail_on_error and summ.get("errors"):
                exit_code = max(exit_code, 1)
            doc_ids.append(rec.id)
        if doc_ids:
            zip_path = ws.export_zip(doc_ids, args.kb_name or "", args.layout)
            out = Path(args.out).resolve() if args.out else Path.cwd() / zip_path.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(zip_path.read_bytes())
            print(f"ZIP: {out}")
    except ServiceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit_code = 2
    finally:
        ws.close()
        if tmp is not None:
            tmp.cleanup()
    return exit_code


def cmd_doctor(args: argparse.Namespace) -> int:
    s = _settings(args)
    ok = True

    def check(name: str, fn) -> None:
        nonlocal ok
        try:
            detail = fn()
            print(f"[ OK ] {name}{': ' + detail if detail else ''}")
        except Exception as exc:  # report everything
            ok = False
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")

    check("Python", lambda: f"{sys.version.split()[0]} ({sys.executable})" if sys.version_info >= (3, 11) else
          (_ for _ in ()).throw(RuntimeError("Python 3.11 이상이 필요합니다")))

    def imports() -> str:
        import fastapi
        import httpx
        import markdown
        import pdfplumber
        import PIL
        import pydantic
        import pypdfium2
        import uvicorn
        return (f"pdfplumber {pdfplumber.__version__}, pypdfium2 {pypdfium2.version.PYPDFIUM_INFO}, "
                f"Pillow {PIL.__version__}, pydantic {pydantic.VERSION}, fastapi {fastapi.__version__}, "
                f"uvicorn {uvicorn.__version__}, httpx {httpx.__version__}, Markdown {markdown.__version__}")
    check("Dependencies", imports)

    def data_dir() -> str:
        s.ensure_dirs()
        probe = s.data_dir / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return str(s.data_dir)
    check("Data directory writable", data_dir)

    def pdf_roundtrip() -> str:
        from .parser import PdfDoc
        sample = Path(__file__).resolve().parents[2] / "samples" / "jedec_like_spec.pdf"
        if not sample.exists():
            return "sample PDF not found (skipped)"
        with PdfDoc(sample) as pdf:
            img = pdf.render(1, None, 50)
            return f"{pdf.page_count} pages parsed, render {img.size[0]}x{img.size[1]}px"
    check("PDF parse/render", pdf_roundtrip)

    def providers() -> str:
        from .providers import ProviderStore
        ps = ProviderStore(s.providers_file, s.allow_api_key_storage, s.providers_seed)
        names = []
        for p in ps.list():
            key = "key:env" if p.api_key_env else ("key:stored" if p.api_key else "key:none")
            names.append(f"{p.id}({p.type},{key})")
        return ", ".join(names)
    check("Providers", providers)
    if args.test_provider:
        from .service import Workspace
        ws = Workspace(s)
        res = ws.test_provider(args.test_provider)
        ws.close()
        print(f"[{' OK ' if res.get('ok') else 'FAIL'}] Provider '{args.test_provider}' call: {res}")
        ok = ok and bool(res.get("ok"))
    return 0 if ok else 1


def cmd_profiles(args: argparse.Namespace) -> int:
    from .profiles import ProfileStore
    s = _settings(args)
    s.ensure_dirs()
    st = ProfileStore(s.profiles_dir)
    if args.action == "list":
        for p in st.list():
            print(f"{p['id']:<20} {'(builtin)' if p.get('builtin') else '':<10} extends={p.get('extends') or '-':<10} {p.get('name')}")
    elif args.action == "show":
        data = st.resolve(args.id).model_dump() if args.resolved else st.get_raw(args.id)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.action == "import":
        raw = json.loads(Path(args.id).read_text(encoding="utf-8"))
        print(json.dumps(st.import_raw(raw, overwrite=args.overwrite), ensure_ascii=False, indent=2))
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    s = _settings(args)
    if args.action == "list":
        from .providers import ProviderStore
        s.ensure_dirs()
        for p in ProviderStore(s.providers_file, s.allow_api_key_storage, s.providers_seed).list():
            print(f"{p.id:<16} {p.type:<12} {p.model:<24} {p.base_url}")
        return 0
    from .service import Workspace
    ws = Workspace(s)
    try:
        res = ws.test_provider(args.id)
    finally:
        ws.close()
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


def cmd_schema(args: argparse.Namespace) -> int:
    from .schema import CanonicalDocument
    text = json.dumps(CanonicalDocument.model_json_schema(), indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec2kb", description="Spec-to-Knowledge: PDF specification -> Markdown knowledge base")
    p.add_argument("--version", action="version", version=f"spec2kb {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("serve", help="웹 UI와 API 서버 실행")
    sp.add_argument("--host")
    sp.add_argument("--port", type=int)
    sp.add_argument("--data-dir")
    sp.add_argument("--workers", type=int)
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser("convert", help="명령줄 일괄 변환 (UI 없이)")
    sp.add_argument("inputs", nargs="+", help="PDF 파일")
    sp.add_argument("--profile", default="jedec")
    sp.add_argument("--out", help="출력 ZIP 경로")
    sp.add_argument("--kb-name", default="")
    sp.add_argument("--layout", choices=["mkdocs", "wiki"])
    sp.add_argument("--pages", help="페이지 범위 (예: 1-20)")
    sp.add_argument("--provider", help="Vision Provider ID")
    sp.add_argument("--no-vision", action="store_true", help="AI 그림 설명 생략")
    sp.add_argument("--options", help="문서 옵션 JSON (문자열 또는 파일 경로)")
    sp.add_argument("--data-dir", help="작업 폴더 (기본: 임시 폴더)")
    sp.add_argument("--fail-on-error", action="store_true", help="검증 오류가 있으면 종료 코드 1")
    sp.add_argument("--quiet", action="store_true")
    sp.set_defaults(fn=cmd_convert)

    sp = sub.add_parser("mock-server", help="오프라인 검증용 Mock 모델 API 서버")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=9100)
    sp.add_argument("--api-key", default="")
    sp.set_defaults(fn=cmd_mock_server)

    sp = sub.add_parser("doctor", help="설치/환경 자가 점검")
    sp.add_argument("--data-dir")
    sp.add_argument("--test-provider", help="지정한 Provider로 실제 호출 테스트")
    sp.set_defaults(fn=cmd_doctor)

    sp = sub.add_parser("profiles", help="프로필 관리")
    sp.add_argument("action", choices=["list", "show", "import"])
    sp.add_argument("id", nargs="?")
    sp.add_argument("--resolved", action="store_true")
    sp.add_argument("--overwrite", action="store_true")
    sp.add_argument("--data-dir")
    sp.set_defaults(fn=cmd_profiles)

    sp = sub.add_parser("providers", help="모델 Provider 목록/테스트")
    sp.add_argument("action", choices=["list", "test"])
    sp.add_argument("id", nargs="?")
    sp.add_argument("--data-dir")
    sp.set_defaults(fn=cmd_providers)

    sp = sub.add_parser("schema", help="Canonical JSON Schema 출력")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_schema)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
