"""문제 사진 → 문제 텍스트 API (POST /ocr). 가짜 Vision·Gemini·OCR 엔진으로 모델·DB·API 키 없이 돈다."""

import base64
import json
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.api import ocr as ocr_api
from app.api.deps import get_settings
from app.api.ocr import compose_problem, lines_to_text
from app.ingestion import ocr
from app.ingestion.ocr import OcrLine, OcrResult
from app.llm.gemini import GeminiClient, GeminiError, JsonResult
from app.main import create_app
from app.vision.google_vision import GoogleVisionClient


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


class _FakeEngine:
    engine = {"name": "fake"}

    def __init__(self):
        self.shapes = []

    def recognize(self, image):
        self.shapes.append(image.shape)
        lines = [
            OcrLine("① 대용량 데이터", 0.9, (10, 40, 100, 60)),
            OcrLine("다음 중 옳지 않은 것은?", 0.95, (10, 0, 200, 20)),
            OcrLine("② 패턴 발견", 0.8, (120, 42, 200, 58)),
        ]
        return OcrResult(lines, self.engine)


class _FakeLlm:
    def __init__(self, data: dict | None = None, error: bool = False):
        self.data, self.error, self.calls = data, error, []

    def close(self):
        pass

    def models_for(self, tier):
        return [f"model-{tier}"]

    def generate_json(self, models, system, user, schema, temperature, images=None):
        self.calls.append({"models": models, "system": system, "schema": schema, "images": images})
        if self.error:
            raise GeminiError("실패", [{"model": models[0], "attempt": 1, "error": "status_503"}])
        return JsonResult(data=self.data, model="gemini-test", usage={})


@pytest.fixture
def fake_ocr(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(ocr, "get_engine", lambda settings: engine)
    return engine


def _post(llm=None, files=None, settings=None, **overrides):
    """overrides로 설정을 바꾼다(기본은 gemini 엔진)."""
    app = create_app()
    if settings is not None:
        s = settings.model_copy(update={"problem_ocr_engine": "gemini", **overrides})
        app.dependency_overrides[get_settings] = lambda: s
    with TestClient(app) as client:
        # conftest가 PRELOAD_MODELS=false라 qa_models는 비어 있다 → 테스트용 가짜를 넣는다.
        app.state.qa_models = SimpleNamespace(llm=llm, judge=None) if llm is not None else None
        return client.post("/ocr", files=files or {"file": ("문제.png", _png(), "image/png")})


def test_ocr_uses_gemini(fake_ocr, settings):
    llm = _FakeLlm({
        "found": True,
        "problem_text": "데이터 분석 조직 구조에 대한 설명으로 옳은 것은?",
        "choices": ["기능 중심 조직은 …", "분산 조직은 …", " ", "이원형 조직은 …"],
        "figure_description": "",
    })
    r = _post(llm, settings=settings)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "gemini" and body["model"] == "gemini-test" and body["fallback_reason"] is None
    assert body["text"] == "데이터 분석 조직 구조에 대한 설명으로 옳은 것은?\n① 기능 중심 조직은 …\n② 분산 조직은 …\n③ 이원형 조직은 …"
    assert len(body["choices"]) == 3
    call = llm.calls[0]
    assert call["models"] == ["model-lite"]
    assert call["images"] == [(_png(), "image/png")]
    assert set(call["schema"]["required"]) == {"found", "problem_text", "choices", "figure_description"}
    assert fake_ocr.shapes == []  # Gemini가 되면 PaddleOCR는 부르지 않는다


def test_ocr_gemini_not_found(fake_ocr, settings):
    r = _post(settings=settings, llm=_FakeLlm({"found": False, "problem_text": "x", "choices": ["y"], "figure_description": ""}))
    body = r.json()
    assert body["engine"] == "gemini" and body["text"] == "" and body["choices"] == []


def test_ocr_falls_back_to_paddle_on_gemini_error(fake_ocr, settings):
    body = _post(_FakeLlm(error=True), settings=settings).json()
    assert body["engine"] == "paddleocr" and body["fallback_reason"] == "llm_failed"
    assert body["text"] == "다음 중 옳지 않은 것은?\n① 대용량 데이터 ② 패턴 발견"
    assert fake_ocr.shapes == [(30, 40, 3)]


def test_ocr_without_llm_uses_paddle(fake_ocr, settings):
    body = _post(None, settings=settings).json()
    assert body["engine"] == "paddleocr" and body["fallback_reason"] == "llm_not_configured"


def test_ocr_rejects_non_image(fake_ocr, settings):
    llm = _FakeLlm({"found": True, "problem_text": "", "choices": [], "figure_description": ""})
    assert _post(llm, files={"file": ("a.txt", b"hello", "text/plain")}, settings=settings).status_code == 400
    assert llm.calls == [] and fake_ocr.shapes == []


def test_compose_problem():
    assert compose_problem(" 문제 ", ["가", "나"], "x축 λ, 감소") == "문제\n[그림·표] x축 λ, 감소\n① 가\n② 나"
    assert compose_problem("문제", [], "") == "문제"
    assert compose_problem("문제", [str(i) for i in range(11)], "").endswith("⑩ 9\n(11) 10")


def test_lines_to_text_empty():
    assert lines_to_text([]) == ""
    assert lines_to_text([OcrLine("  ", 0.5, (0, 0, 10, 10))]) == ""


def test_gemini_sends_image_part(settings):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        answer = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
        return httpx.Response(200, json=answer)

    s = settings.model_copy(update={"gemini_api_key": SecretStr("test-key"), "gemini_model_lite": "m"})
    client = GeminiClient(s, transport=httpx.MockTransport(handler))
    try:
        r = client.generate_json(["m"], "sys", "user", {"type": "object"}, 0, images=[(b"\x89PNG", "image/png")])
    finally:
        client.close()
    assert r.data == {"ok": True}
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0] == {"text": "user"}
    assert parts[1] == {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b"\x89PNG").decode()}}


def _vision_transport(seen: dict, response: httpx.Response):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return response

    return httpx.MockTransport(handler)


def _use_vision(monkeypatch, seen: dict, response: httpx.Response):
    monkeypatch.setattr(
        ocr_api, "vision_client", lambda s: GoogleVisionClient(s, transport=_vision_transport(seen, response))
    )


def test_ocr_uses_google_vision(fake_ocr, settings, monkeypatch):
    seen: dict = {}
    text = "16 데이터 분석 조직 구조에 대한 설명으로 옳은 것은?\n① 기능 중심 조직은 …\n"
    _use_vision(monkeypatch, seen, httpx.Response(200, json={"responses": [{"fullTextAnnotation": {"text": text}}]}))
    llm = _FakeLlm({"found": True, "problem_text": "x", "choices": [], "figure_description": ""})
    body = _post(llm, settings=settings, problem_ocr_engine="google_vision",
                 google_vision_api_key=SecretStr("vision-key"), google_vision_language_hints="ko, en").json()
    assert body["engine"] == "google_vision" and body["fallback_reason"] is None
    assert body["text"] == text.strip()
    assert seen["url"] == "https://vision.googleapis.com/v1/images:annotate" and seen["key"] == "vision-key"
    req = seen["body"]["requests"][0]
    assert req["image"]["content"] == base64.b64encode(_png()).decode()
    assert req["features"] == [{"type": "DOCUMENT_TEXT_DETECTION"}]
    assert req["imageContext"] == {"languageHints": ["ko", "en"]}
    assert llm.calls == [] and fake_ocr.shapes == []  # Vision이 되면 Gemini·PaddleOCR는 부르지 않는다


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, json={"error": {"message": "billing"}}),
        httpx.Response(200, json={"responses": [{"error": {"code": 7, "message": "denied"}}]}),
        httpx.Response(200, text="not json"),
    ],
)
def test_ocr_vision_failure_falls_back_to_paddle(fake_ocr, settings, monkeypatch, response):
    _use_vision(monkeypatch, {}, response)
    body = _post(settings=settings, problem_ocr_engine="google_vision", google_vision_api_key=SecretStr("k")).json()
    assert body["engine"] == "paddleocr" and body["fallback_reason"] == "vision_failed"
    assert fake_ocr.shapes == [(30, 40, 3)]


def test_ocr_vision_without_key_uses_paddle(fake_ocr, settings, monkeypatch):
    seen: dict = {}
    _use_vision(monkeypatch, seen, httpx.Response(200, json={"responses": [{}]}))
    body = _post(settings=settings, problem_ocr_engine="google_vision", google_vision_api_key=SecretStr("")).json()
    assert body["engine"] == "paddleocr" and body["fallback_reason"] == "vision_not_configured"
    assert seen == {}  # 키가 없으면 호출하지 않는다


def test_vision_empty_result(settings):
    s = settings.model_copy(update={"google_vision_api_key": SecretStr("k")})
    client = GoogleVisionClient(s, transport=_vision_transport({}, httpx.Response(200, json={"responses": [{}]})))
    try:
        assert client.document_text(b"x") == ""
    finally:
        client.close()
