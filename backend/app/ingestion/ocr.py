"""인쇄체 OCR (PaddleOCR, D-008 / D-013).

- 모델 캐시 위치는 `OCR_MODEL_DIR` → `PADDLE_PDX_CACHE_HOME`. paddlex가 import 시점에 읽으므로
  paddleocr는 이 모듈 안에서만, 환경변수를 설정한 뒤 지연 import한다.
- 엔진은 프로세스당 1개만 만든다(모델 로딩이 느림). 추론 객체의 스레드 안전성이 문서에 없고
  BackgroundTasks는 스레드풀에서 돌기 때문에 추론은 잠금으로 직렬화한다.
- 결과 텍스트는 교재 원문 그대로 둔다(교정하지 않음).
"""

import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.core.config import Settings

_CACHE_ENV = "PADDLE_PDX_CACHE_HOME"


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x_min, y_min, x_max, y_max (원본 이미지 픽셀)


@dataclass(frozen=True)
class OcrResult:
    lines: list[OcrLine]
    engine: dict  # 엔진·버전·언어·모델 이름

    @property
    def mean_confidence(self) -> float | None:
        if not self.lines:
            return None
        return round(sum(line.confidence for line in self.lines) / len(self.lines), 4)

    def to_json(self) -> dict:
        return {"engine": self.engine, "lines": [asdict(line) for line in self.lines]}


def lines_from_paddle(res) -> list[OcrLine]:
    """PaddleOCR 결과 1건(rec_texts / rec_scores / rec_boxes)을 줄 목록으로 바꾼다."""
    texts, scores, boxes = res["rec_texts"], res["rec_scores"], res["rec_boxes"]
    return [
        OcrLine(text=str(t), confidence=round(float(s), 4), bbox=tuple(int(v) for v in b))
        for t, s, b in zip(texts, scores, boxes, strict=True)
    ]


class PaddleOcrEngine:
    def __init__(self, settings: Settings):
        if settings.ocr_model_dir is not None:
            os.environ[_CACHE_ENV] = str(settings.ocr_model_dir)
        import paddle
        import paddleocr
        import paddlex.utils.cache
        from paddleocr import PaddleOCR

        # paddlex가 이미 다른 값으로 import됐다면 모델이 엉뚱한 곳(C:)에 받아지므로 막는다.
        if settings.ocr_model_dir is not None:
            actual = Path(paddlex.utils.cache.CACHE_DIR).resolve()
            if actual != settings.ocr_model_dir.resolve():
                raise RuntimeError(f"PaddleX 캐시 위치가 설정과 다름: {actual}")

        named = bool(settings.ocr_det_model or settings.ocr_rec_model)
        self._ocr = PaddleOCR(
            # 모델 이름을 지정하면 PaddleOCR가 lang을 무시하므로 그때는 넘기지 않는다.
            lang=None if named else (settings.ocr_lang or None),
            text_detection_model_name=settings.ocr_det_model or None,
            text_recognition_model_name=settings.ocr_rec_model or None,
            device=settings.ocr_device,
            # 스캔 교재에는 문서 방향 분류·왜곡 보정·줄 방향 분류가 필요 없고 모델만 늘어난다.
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # paddlepaddle 3.3.x CPU에서 oneDNN 경로가 NotImplementedError를 낸다(D-013).
            enable_mkldnn=False,
        )
        pipeline = getattr(self._ocr, "paddlex_pipeline", None)
        self.engine = {
            "name": "paddleocr",
            "version": paddleocr.__version__,
            "paddle_version": paddle.__version__,
            "lang": settings.ocr_lang,
            "det_model": _model_name(pipeline, "text_det_model") or settings.ocr_det_model,
            "rec_model": _model_name(pipeline, "text_rec_model") or settings.ocr_rec_model,
        }
        self._lock = threading.Lock()

    def recognize(self, image_bgr: np.ndarray) -> OcrResult:
        with self._lock:
            res = self._ocr.predict(image_bgr)[0]
        return OcrResult(lines=lines_from_paddle(res), engine=self.engine)


def _model_name(pipeline, attr: str) -> str:
    model = getattr(pipeline, attr, None)
    return getattr(model, "model_name", "") or ""


_engine: PaddleOcrEngine | None = None
_engine_lock = threading.Lock()


def get_engine(settings: Settings) -> PaddleOcrEngine:
    """처음 호출할 때 모델을 로드하고, 이후에는 같은 엔진을 돌려준다."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = PaddleOcrEngine(settings)
    return _engine
