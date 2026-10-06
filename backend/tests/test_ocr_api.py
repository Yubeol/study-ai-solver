"""문제 사진 OCR API (POST /ocr). 가짜 OCR 엔진을 써서 모델·DB 없이 돈다."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.ocr import lines_to_text
from app.ingestion import ocr
from app.ingestion.ocr import OcrLine, OcrResult
from app.main import create_app


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


@pytest.fixture
def fake_ocr(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(ocr, "get_engine", lambda settings: engine)
    return engine


def test_ocr_returns_text_in_reading_order(fake_ocr):
    with TestClient(create_app()) as client:
        r = client.post("/ocr", files={"file": ("문제.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "다음 중 옳지 않은 것은?\n① 대용량 데이터 ② 패턴 발견"
    assert body["line_count"] == 3
    assert body["mean_confidence"] == pytest.approx(0.8833, abs=1e-4)
    assert fake_ocr.shapes == [(30, 40, 3)]


def test_ocr_rejects_non_image(fake_ocr):
    with TestClient(create_app()) as client:
        r = client.post("/ocr", files={"file": ("a.txt", b"hello", "text/plain")})
        assert r.status_code == 400
        assert client.post("/ocr").status_code == 422  # 파일 없음
    assert fake_ocr.shapes == []


def test_lines_to_text_empty():
    assert lines_to_text([]) == ""
    assert lines_to_text([OcrLine("  ", 0.5, (0, 0, 10, 10))]) == ""
