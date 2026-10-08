from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request

from spec2kb.mockserver import create_mock_app
from spec2kb.profiles.model import Profile
from spec2kb.providers import ProviderConfig, ProviderError, ProviderStore, make_provider
from spec2kb.providers.http import extract_path, render_template
from spec2kb.schema import Figure
from spec2kb.vision import VisionCache, classify_by_rules, describe_figure, parse_model_json
from spec2kb.vision.describe import build_prompt, result_from_text

from .conftest import ServerThread

P = Profile(id="t", name="t")


def _fig(**kw):
    base = dict(id="fig-1", page=1, bbox=[0, 0, 10, 10], caption="", title="")
    base.update(kw)
    return Figure(**base)


def test_classification_caption_beats_text_rules():
    f = _fig(caption="Figure 1 — System Block Diagram", embedded_text=["CA[6:0], CK_t/CK_c", "PMIC"])
    assert classify_by_rules(f, P) == ("block_diagram", "rule")
    f = _fig(caption="Figure 2 — Something", embedded_text=["CK_t", "CK_c", "T0", "DQS_t"])
    assert classify_by_rules(f, P) == ("timing_diagram", "rule")
    assert classify_by_rules(_fig(caption="Figure 9 — Photo"), P) == ("generic", "default")


def test_prompt_contains_context_and_output_keys():
    f = _fig(number="2", title="Read Burst", embedded_text=["CK_t", "RL = 22 nCK"], prompt_extra="Mention tDQSCK.")
    rule = P.image_type("timing_diagram")
    system, prompt, h1 = build_prompt(f, rule, P, "6.1 Read Operation", "Doc", "m")
    assert "- CK_t" in prompt and "6.1 Read Operation" in prompt and "Mention tDQSCK." in prompt
    assert '- "signals": array of strings (Signals)' in prompt and '- "uncertain"' in prompt
    _, _, h2 = build_prompt(f, rule, P, "6.1 Read Operation", "Doc", "other-model")
    assert h1 != h2


def test_parse_model_json_variants():
    assert parse_model_json('```json\n{"summary": "x", "a": [1,],}\n```') == {"summary": "x", "a": [1]}
    assert parse_model_json("Sure! {\"summary\": \"y\"} hope it helps") == {"summary": "y"}
    assert parse_model_json("no json here") is None
    res = result_from_text("plain text answer", P.image_type("generic"))
    assert res.status == "uncertain" and not res.structured and res.summary == "plain text answer"


def test_template_rendering_and_paths():
    tpl = json.loads('{"m": "{{model}}", "n": "{{max_tokens}}", "msg": "Q: {{prompt}}", "img": ["{{image_base64}}"]}')
    out = render_template(tpl, {"model": "x", "max_tokens": 5, "prompt": 'hi "q"', "image_base64": "AAA"})
    assert out == {"m": "x", "n": 5, "msg": 'Q: hi "q"', "img": ["AAA"]}
    assert json.loads(json.dumps(out))["msg"] == 'Q: hi "q"'  # values stay valid JSON after substitution
    assert extract_path({"a": [{"b": {"c": "ok"}}]}, "a.0.b.c") == "ok"
    assert extract_path({"a": [{"b": "x"}]}, "a[0].b") == "x"
    with pytest.raises(ProviderError):
        extract_path({"a": 1}, "b")


def test_openai_adapter_against_mock_server_with_auth(tmp_path):
    with ServerThread(create_mock_app(api_key="sekret")) as srv:
        cfg = ProviderConfig(id="m", name="m", type="openai", base_url=srv.url + "/v1", model="mock-vision-1",
                             api_key="sekret", max_retries=0, timeout_s=10)
        resp = make_provider(cfg).complete(system="s", prompt="Reply with the word OK.", images=[b"\x89PNG"])
        assert resp.text == "OK"
        bad = make_provider(cfg.model_copy(update={"api_key": "wrong"}))
        with pytest.raises(ProviderError) as ei:
            bad.complete(system="s", prompt="x")
        assert ei.value.status == 401


def test_custom_http_adapter_against_mock_ocr(tmp_path):
    with ServerThread(create_mock_app()) as srv:
        cfg = ProviderConfig(id="c", name="c", type="custom_http", base_url=srv.url, endpoint_path="/ocr",
                             request_template='{"prompt": "{{prompt}}", "image": "{{image_base64}}"}',
                             response_path="result.text", max_retries=0)
        resp = make_provider(cfg).complete(system="", prompt="Transcribe all text on this scanned page",
                                           images=[b"img"])
        assert resp.text.startswith("MOCK OCR TRANSCRIPTION")


def test_retry_on_503_then_success():
    app = FastAPI()
    calls = {"n": 0}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        calls["n"] += 1
        if calls["n"] == 1:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "busy"}, status_code=503, headers={"Retry-After": "0"})
        return {"choices": [{"message": {"content": "fine"}}], "model": "x"}

    with ServerThread(app) as srv:
        cfg = ProviderConfig(id="r", name="r", type="openai", base_url=srv.url + "/v1", model="x", max_retries=2)
        assert make_provider(cfg).complete(system="", prompt="p").text == "fine"
        assert calls["n"] == 2


def test_connection_refused_is_reported():
    cfg = ProviderConfig(id="d", name="d", type="openai", base_url="http://127.0.0.1:1/v1", model="x", max_retries=0,
                         timeout_s=2)
    with pytest.raises(ProviderError) as ei:
        make_provider(cfg).complete(system="", prompt="p")
    assert "연결 실패" in str(ei.value)


def test_provider_store_masks_and_keeps_keys(tmp_path):
    st = ProviderStore(tmp_path / "p.json")
    st.upsert({"id": "gw", "name": "GW", "type": "openai", "base_url": "http://x/v1", "api_key": "k1"}, create=True)
    assert st.get("gw").public()["api_key"] == "" and st.get("gw").public()["api_key_set"]
    st.upsert({"id": "gw", "name": "GW2", "type": "openai", "base_url": "http://x/v1", "api_key": ""}, create=False)
    assert st.get("gw").api_key == "k1" and st.get("gw").name == "GW2"
    with pytest.raises(ProviderError):
        st.upsert({"id": "mock", "name": "x"}, create=False)
    with pytest.raises(ProviderError):
        st.upsert({"id": "bad", "name": "b", "type": "custom_http", "request_template": "{nope"}, create=True)
    st2 = ProviderStore(tmp_path / "q.json", allow_key_storage=False)
    with pytest.raises(ProviderError):
        st2.upsert({"id": "z1", "name": "z", "api_key": "secret"}, create=True)


def test_hallucinated_value_is_flagged_and_cache_used(parse_sample, tmp_path):
    doc, profile, assets, _ = parse_sample("jedec_like_spec", "jedec")
    fig = doc.figure("fig-2").model_copy(deep=True)
    fig.image_type = "timing_diagram"
    cfg = ProviderConfig(id="mock-h", name="h", type="mock", extra_body={"mock_hallucinate": True})
    cache = VisionCache(tmp_path / "cache")
    page_text = doc.page(8).source_text
    res = describe_figure(fig, assets / fig.asset, make_provider(cfg), profile, "6.1", "Doc", page_text, cache)
    assert res.status == "uncertain"
    assert any("9.99 ns" in w and "tFAKE" in w for w in res.warnings)
    again = describe_figure(fig, assets / fig.asset, make_provider(cfg), profile, "6.1", "Doc", page_text, cache)
    assert again.cached and again.status == "uncertain"


def test_provider_failure_marks_figure_failed(parse_sample, tmp_path):
    doc, profile, assets, _ = parse_sample("jedec_like_spec", "jedec")
    fig = doc.figure("fig-3").model_copy(deep=True)
    cfg = ProviderConfig(id="mock-f", name="f", type="mock", extra_body={"mock_fail": "always"})
    res = describe_figure(fig, assets / fig.asset, make_provider(cfg), profile, "", "", "", None)
    assert res.status == "failed" and "mock_fail" in res.error
