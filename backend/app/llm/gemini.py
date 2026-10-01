"""Gemini REST 호출(generateContent) + JSON 구조화 출력 + 재시도·폴백 (D-006, D-010).

- 구조화 출력: generationConfig.responseMimeType="application/json" + responseJsonSchema
  (확인 2026-10-01, https://ai.google.dev/api/generate-content , gemini-3.5-flash-lite 실제 호출로 확인).
- 429/5xx/시간 초과/JSON 아님 → 같은 모델로 GEMINI_MAX_RETRIES번까지 지수 백오프 재시도.
  그래도 실패하면 다음 모델(폴백)로 넘어간다. 모든 모델이 실패하면 GeminiError.
- API 키는 헤더(x-goog-api-key)로만 보내고 로그·예외 메시지에 넣지 않는다.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from app.core.config import Settings

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
RETRY_STATUS = {429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class JsonResult:
    data: dict
    model: str  # 실제로 응답한 모델
    usage: dict  # usageMetadata(토큰 수)
    attempts: list[dict] = field(default_factory=list)  # 실패한 시도 기록(모델, 시도 번호, 오류)


class GeminiClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        if not settings.gemini_api_key.get_secret_value():
            raise RuntimeError("GEMINI_API_KEY가 비어 있습니다.")
        self._settings = settings
        self._sleep = sleep
        self._client = httpx.Client(
            timeout=settings.gemini_timeout_seconds,
            headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()},
            transport=transport,
        )

    def models_for(self, tier: str) -> list[str]:
        """tier(lite/strong)의 모델 순서. strong이면 lite를 폴백으로 붙인다."""
        s = self._settings
        order = [s.gemini_model_strong, s.gemini_model_lite] if tier == "strong" else [s.gemini_model_lite]
        out = [m for i, m in enumerate(order) if m and m not in order[:i]]
        if not out:
            raise RuntimeError("GEMINI_MODEL_LITE/STRONG이 비어 있습니다.")
        return out

    def generate_json(self, models: list[str], system: str, user: str, schema: dict,
                      temperature: float) -> JsonResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "temperature": temperature,
            },
        }
        attempts: list[dict] = []
        s = self._settings
        for model in models:
            for attempt in range(1, s.gemini_max_retries + 2):
                result, retryable = self._call(model, body)
                if isinstance(result, JsonResult):
                    result.attempts = attempts
                    return result
                attempts.append({"model": model, "attempt": attempt, "error": result})
                if not retryable:
                    break
                if attempt <= s.gemini_max_retries:
                    self._sleep(s.gemini_retry_base_seconds * 2 ** (attempt - 1))
        raise GeminiError("Gemini 호출 실패(모든 모델·재시도)", attempts)

    def _call(self, model: str, body: dict) -> tuple[JsonResult | str, bool]:
        """(결과, _) 또는 (오류 설명, 재시도 가능 여부)."""
        try:
            r = self._client.post(f"{API_BASE}/{model}:generateContent", json=body)
        except httpx.TimeoutException:
            return "timeout", True
        except httpx.HTTPError as e:
            return f"http_error:{type(e).__name__}", True
        if r.status_code != 200:
            return f"status_{r.status_code}", r.status_code in RETRY_STATUS
        try:
            d = r.json()
            cand = d["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("JSON 객체가 아님")
        except (ValueError, KeyError, IndexError, TypeError) as e:
            # 차단(finishReason=SAFETY 등)이나 잘린 JSON. 다시 시도해 본다.
            return f"bad_response:{type(e).__name__}", True
        return JsonResult(data=data, model=d.get("modelVersion") or model, usage=d.get("usageMetadata", {})), False

    def close(self) -> None:
        self._client.close()
