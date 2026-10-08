"""Google Cloud Vision OCR(DOCUMENT_TEXT_DETECTION) REST 호출 (D-JW-003).

- POST https://vision.googleapis.com/v1/images:annotate, 본문 requests[].image.content(base64) +
  features[{type: DOCUMENT_TEXT_DETECTION}] + imageContext.languageHints. 결과는 responses[0].fullTextAnnotation.text,
  요청별 오류는 responses[0].error.message (확인 2026-10-06, https://docs.cloud.google.com/vision/docs/ocr ).
- 인증은 API 키(공식 문서 "API key or OAuth token", https://docs.cloud.google.com/vision/docs/request ).
  키는 헤더(x-goog-api-key)로만 보내고 로그·예외 메시지에 넣지 않는다.
- 결제 계정이 연결된 프로젝트에서만 동작한다(월 1,000장 무료, https://cloud.google.com/vision/pricing ).
"""

import base64

import httpx

from app.core.config import Settings

API_URL = "https://vision.googleapis.com/v1/images:annotate"


class VisionError(RuntimeError):
    pass


class GoogleVisionClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        key = settings.google_vision_api_key.get_secret_value()
        if not key:
            raise RuntimeError("GOOGLE_VISION_API_KEY가 비어 있습니다.")
        self._hints = [h.strip() for h in settings.google_vision_language_hints.split(",") if h.strip()]
        self._client = httpx.Client(
            timeout=settings.google_vision_timeout_seconds,
            headers={"x-goog-api-key": key},
            transport=transport,
        )

    def document_text(self, data: bytes) -> str:
        """사진 전체 글자(읽는 순서). 글자가 없으면 빈 문자열. 실패하면 VisionError."""
        request: dict = {
            "image": {"content": base64.b64encode(data).decode("ascii")},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        }
        if self._hints:
            request["imageContext"] = {"languageHints": self._hints}
        try:
            r = self._client.post(API_URL, json={"requests": [request]})
        except httpx.HTTPError as e:
            raise VisionError(f"http_error:{type(e).__name__}") from e
        if r.status_code != 200:
            raise VisionError(f"status_{r.status_code}")
        try:
            res = r.json()["responses"][0]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise VisionError(f"bad_response:{type(e).__name__}") from e
        if res.get("error"):
            raise VisionError(f"vision_error:{res['error'].get('code')}")
        return str((res.get("fullTextAnnotation") or {}).get("text") or "")

    def close(self) -> None:
        self._client.close()
