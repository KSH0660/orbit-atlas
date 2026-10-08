"""Browser E2E: a non-developer's path through the web UI (Playwright + Chromium).

Skipped automatically when Playwright or a Chromium binary is not available
(e.g. on the closed-network server, where only the API tests run).
"""

from __future__ import annotations

import glob
import io
import os
import zipfile

import pytest

from spec2kb.mockserver import create_mock_app
from spec2kb.web.app import create_app

from ..conftest import ServerThread

pytestmark = pytest.mark.browser

sync_api = pytest.importorskip("playwright.sync_api")


def _chromium_path() -> str | None:
    if os.environ.get("S2K_TEST_CHROMIUM"):
        return os.environ["S2K_TEST_CHROMIUM"]
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return found[-1] if found else None


@pytest.fixture()
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=_chromium_path()) if _chromium_path() else p.chromium.launch()
        except Exception as exc:  # no browser installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


def test_ui_end_to_end(browser, settings, workspace, samples, tmp_path):
    page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page.set_default_timeout(60000)
    try:
        _flow(page, settings, workspace, samples)
    except Exception:
        page.screenshot(path=str(tmp_path / "failure.png"), full_page=True)
        print(f"screenshot: {tmp_path / 'failure.png'}")
        raise


def _flow(page, settings, workspace, samples):
    app = create_app(settings, workspace)
    with ServerThread(app) as srv, ServerThread(create_mock_app()) as mock:
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        base = srv.url

        # 1. upload with auto-run
        page.goto(base + "/#/docs")
        page.set_input_files("[data-testid=file-input]", [str(samples / "jedec_like_spec.pdf")])
        page.click("[data-testid=upload-btn]")
        page.wait_for_selector("tr[data-doc] >> text=오류 0", timeout=90000)

        # 2. review: page navigation, block overlay, edit with re-validation
        page.click("a.doc-link")
        page.wait_for_selector("[data-testid=blocks]")
        page.click("[data-page='6']")
        page.wait_for_selector("[data-testid=page-image] .bbox.t-table")
        card = page.locator("[data-card]", has_text="All voltages are referenced")
        card.locator("[data-testid=edit-block]").click()
        card.locator("[data-testid=block-editor]").fill("All voltages are referenced to ground.")
        card.locator("[data-testid=save-block]").click()
        page.wait_for_selector("[data-testid=page-issues] >> text=VSS")
        assert page.locator("[data-card] .badge.edited").count() >= 1

        # 3. figure re-interpretation with a reviewer instruction
        page.click("[data-page='8']")
        page.wait_for_selector("[data-testid=redescribe]")
        page.click("[data-testid=redescribe]")
        page.fill(".modal textarea", "Name the strobe preamble length.")
        page.click(".modal footer button.primary")
        page.wait_for_selector(".toast.ok >> text=그림 재해석 완료", timeout=60000)

        # 4. issues tab shows the edit-induced warning
        page.click("[data-tab=issues]")
        page.wait_for_selector("[data-testid=issue-table] >> text=신호명 누락")

        # 5. preview renders Markdown with rewritten image links
        page.click("[data-tab=preview]")
        page.wait_for_selector("[data-testid=rendered-md]")
        page.locator("[data-testid=file-tree] a", has_text="6 Command and Timing").click()
        page.wait_for_selector("[data-testid=rendered-md] img")
        src = page.locator("[data-testid=rendered-md] img").first.get_attribute("src")
        assert src.startswith("/api/docs/")
        assert page.evaluate("document.querySelector('[data-testid=rendered-md] img').naturalWidth") > 100

        # 6. ZIP download
        page.click("[data-tab=export]")
        with page.expect_download() as dl:
            page.click("[data-testid=export-btn]")
        data = open(dl.value.path(), "rb").read()
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert any(n.endswith("mkdocs.yml") for n in names)
        assert any(n.endswith("_meta/jesd-syn-01/source_map.json") for n in names)

        # 7. inherited profile edited through the generated form
        page.goto(base + "/#/profiles")
        page.click("[data-testid=new-profile]")
        page.locator(".modal input[type=text]").nth(0).fill("ui-team")
        page.locator(".modal input[type=text]").nth(1).fill("UI Team")
        page.click(".modal footer button.primary")
        page.wait_for_selector("text=상속 관계:")
        page.click("summary:has-text('Markdown 출력 규칙')")
        fld = page.locator("[data-path='markdown.split_level'] input")
        fld.fill("2")
        fld.dispatch_event("change")
        page.click("[data-testid=save-profile]")
        page.wait_for_selector(".toast.ok >> text=프로필을 저장했습니다")
        assert workspace.profiles.get_raw("ui-team")["overrides"] == {"markdown": {"split_level": 2}}

        # 8. provider registration + connection test against the mock HTTP server
        page.goto(base + "/#/providers")
        page.click("[data-testid=new-provider]")
        page.locator(".modal label:has-text('Provider ID') input").fill("ui-mock")
        page.locator(".modal label:has-text('이름') input").first.fill("UI mock")
        page.locator(".modal label:has-text('API Base URL') input").fill(mock.url + "/v1")
        page.locator(".modal label:has-text('모델 이름') input").fill("mock-vision-1")
        page.click(".modal footer button.primary")
        page.click("tr[data-provider=ui-mock] [data-testid=test-provider]")
        page.wait_for_selector(".toast.ok >> text=UI mock", timeout=20000)

        assert errors == []
