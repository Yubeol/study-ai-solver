"""Jev 판정기 — TypeSafe 직접 API (D-007, D-028).

- 요청(확인 2026-10-01, https://docs.typesafe.ai/api.md , https://docs.typesafe.ai/primitives/noul.md):
  `POST JEV_API_URL` + `Authorization: Bearer <키>`, 본문 {state, model, questions}.
  state = {"question": 질문, "evidence": [{n, page, path, text}]}(Gemini에 넘기는 근거 K개와 같은 묶음),
  questions = {"can_answer": noul 질문(prompts/judge_can_answer.json)}.
- 응답: answers.can_answer.noul = "예"일 확률(0~1), usage.input_tokens/output_tokens.
- 429/529/5xx/시간 초과는 지수 백오프로 재시도, 401/422 등은 바로 실패. 실패해도 예외를 던지지 않고
  JudgeResult(error=…)를 돌려준다(질의 흐름은 none과 같은 동작).
- 키는 헤더로만 보내고 로그·오류 기록에 넣지 않는다.
"""

import time
from collections.abc import Callable

import httpx

from app.core.config import Settings
from app.judge import JudgeResult
from app.prompts import load_json

QUESTION_KEY = "can_answer"
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class JevJudge:
    name = "jev_typesafe"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        key = settings.typesafe_api_key.get_secret_value()
        if not key:
            raise RuntimeError("TYPESAFE_API_KEY가 비어 있습니다(JUDGE_PROVIDER=jev_typesafe).")
        if not settings.jev_model:
            raise RuntimeError("JEV_MODEL이 비어 있습니다.")
        self._settings = settings
        self._sleep = sleep
        self._client = httpx.Client(
            timeout=settings.jev_timeout_seconds,
            headers={"Authorization": f"Bearer {key}"},
            transport=transport,
        )

    def request_body(self, question: str, evidence: list[dict]) -> dict:
        state = {
            "question": question,
            "evidence": [{"n": e["n"], "page": e["page"], "path": e["path"] or "", "text": e["clean_text"].strip()}
                         for e in evidence],
        }
        return {"state": state, "model": self._settings.jev_model,
                "questions": {QUESTION_KEY: load_json("judge_can_answer.json")}}

    def can_answer(self, question: str, evidence: list[dict]) -> JudgeResult:
        body = self.request_body(question, evidence)
        s = self._settings
        attempts: list[dict] = []
        for attempt in range(1, s.judge_max_retries + 2):
            error, retryable = None, False
            try:
                resp = self._client.post(s.jev_api_url, json=body)
            except httpx.TimeoutException:
                error, retryable = "timeout", True
            except httpx.HTTPError as e:
                error, retryable = f"http_error:{type(e).__name__}", True
            else:
                if resp.status_code == 200:
                    result = _parse(resp)
                    if result.error is None:
                        result.attempts = attempts
                        return result
                    error = result.error
                else:
                    error, retryable = f"status_{resp.status_code}", resp.status_code in RETRY_STATUS
            attempts.append({"attempt": attempt, "error": error})
            if not retryable or attempt > s.judge_max_retries:
                break
            self._sleep(s.judge_retry_base_seconds * 2 ** (attempt - 1))
        return JudgeResult(probability=None, attempts=attempts, error=attempts[-1]["error"])

    def close(self) -> None:
        self._client.close()


def _parse(resp: httpx.Response) -> JudgeResult:
    try:
        data = resp.json()
        p = data["answers"][QUESTION_KEY]["noul"]
    except (ValueError, KeyError, TypeError):
        return JudgeResult(probability=None, error="bad_response")
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 1:
        return JudgeResult(probability=None, error="bad_probability")
    return JudgeResult(probability=float(p), model=data.get("model"), usage=data.get("usage"))
