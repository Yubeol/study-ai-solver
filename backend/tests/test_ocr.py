"""OCR 모듈. 기본 테스트는 모델 없이 변환·디코딩만 확인하고,
실제 PaddleOCR 모델 테스트는 `ocr_model` mark로 분리한다(`uv run pytest -m ocr_model`).
"""

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.ingestion.images import InvalidImage, decode_bgr
from app.ingestion.ocr import OcrLine, OcrResult, lines_from_paddle

MALGUN = Path(r"C:\Windows\Fonts\malgun.ttf")


def korean_page_png(lines: list[str], size=(900, 120)) -> bytes:
    """맑은 고딕으로 글자를 그린 테스트 이미지. 교재 이미지는 쓰지 않는다."""
    if not MALGUN.exists():
        pytest.skip("맑은 고딕 폰트 없음")
    img = Image.new("RGB", (size[0], size[1] * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(MALGUN), 40)
    for i, text in enumerate(lines):
        draw.text((30, 30 + i * size[1]), text, fill="black", font=font)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_lines_from_paddle_result():
    res = {
        "rec_texts": ["데이터 분석", "회귀분석"],
        "rec_scores": [np.float32(0.99876), 0.9],
        "rec_boxes": np.array([[30, 31, 400, 83], [30, 130, 500, 180]], dtype=np.int16),
    }
    lines = lines_from_paddle(res)
    assert lines == [
        OcrLine("데이터 분석", 0.9988, (30, 31, 400, 83)),
        OcrLine("회귀분석", 0.9, (30, 130, 500, 180)),
    ]
    assert all(type(v) is int for v in lines[0].bbox)
    result = OcrResult(lines, {"name": "paddleocr"})
    assert result.mean_confidence == 0.9494
    assert result.to_json()["lines"][0] == {"text": "데이터 분석", "confidence": 0.9988, "bbox": (30, 31, 400, 83)}


def test_empty_result():
    res = {"rec_texts": [], "rec_scores": [], "rec_boxes": np.zeros((0, 4), dtype=np.int16)}
    result = OcrResult(lines_from_paddle(res), {})
    assert result.lines == [] and result.mean_confidence is None


def test_decode_bgr_from_bytes_saved_under_korean_path(tmp_path):
    path = tmp_path / "자료실" / "페이지 1.png"
    path.parent.mkdir()
    img = Image.new("RGB", (20, 10), (255, 0, 0))
    img.save(path)  # Pillow로 저장한 파일을 바이트로 읽어 디코딩
    arr = decode_bgr(path.read_bytes())
    assert arr.shape == (10, 20, 3)
    assert tuple(arr[0, 0]) == (0, 0, 255)  # BGR 순서


def test_decode_bgr_rejects_garbage():
    with pytest.raises(InvalidImage):
        decode_bgr(b"not an image")


@pytest.mark.ocr_model
def test_real_paddleocr_reads_korean(settings):
    from app.ingestion.ocr import get_engine

    data = korean_page_png(["데이터 분석 준전문가", "회귀분석의 가정"])
    result = get_engine(settings).recognize(decode_bgr(data))
    texts = [line.text.replace(" ", "") for line in result.lines]
    assert "데이터분석준전문가" in texts
    assert "회귀분석의가정" in texts
    assert result.mean_confidence > 0.8
    assert result.engine["rec_model"]
