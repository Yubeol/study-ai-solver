"""Jev 판정기(TypeSafe 직접 API): 요청 형식, 재시도, 실패 처리. 실제 호출 없음(가짜 transport)."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.judge import get_judge
from app.judge.jev import JevJudge

EVIDENCE = [
    {"n": 1, "page": "245", "path": "장 > 절", "clean_text": " 본문1 "},
    {"n": 2, "page": "246", "path": "", "clean_text": "본문2"},
]


@pytest.fixture
def jev_settings(settings):
    return settings.model_copy(update={
        "judge_provider": "jev_typesafe", "typesafe_api_key": SecretStr("test-key"), "jev_model": "jev-latest",
        "jev_api_url": "https://jev.test/v1/systemone", "judge_max_retries": 2, "judge_retry_base_seconds": 0,
    })


def _ok(p=0.73):
    return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"can_answer": {"type": "noul", "noul": p}},
                                     "usage": {"input_tokens": 300, "output_tokens": 20}})


def _judge(s, handler):
    return JevJudge(s, transport=httpx.MockTransport(handler), sleep=lambda x: None)


def test_request_body_and_success(jev_settings):
    seen = []

    def handler(req):
        seen.append(req)
        return _ok()

    r = _judge(jev_settings, handler).can_answer("질문", EVIDENCE)
    assert (r.probability, r.model, r.error, r.attempts) == (0.73, "jev-1.13.0", None, [])
    assert r.usage == {"input_tokens": 300, "output_tokens": 20}
    req = seen[0]
    assert req.headers["authorization"] == "Bearer test-key" and str(req.url) == "https://jev.test/v1/systemone"
    body = json.loads(req.content)
    assert body["model"] == "jev-latest"
    # 질문 + 근거 K개(번호·쪽·제목 경로·clean_text)
    assert body["state"] == {"question": "질문", "evidence": [
        {"n": 1, "page": "245", "path": "장 > 절", "text": "본문1"}, {"n": 2, "page": "246", "path": "", "text": "본문2"}]}
    q = body["questions"]["can_answer"]
    assert q["type"] == "noul" and q["instructions"] and set(q["criteria"]) == {"true", "false"}


def test_retry_on_529_then_success(jev_settings):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(529) if len(calls) < 3 else _ok(0.2)

    r = _judge(jev_settings, handler).can_answer("q", EVIDENCE)
    assert r.probability == 0.2 and [a["error"] for a in r.attempts] == ["status_529", "status_529"]


def test_non_retryable_and_exhausted(jev_settings):
    calls = []

    def unauthorized(req):
        calls.append(1)
        return httpx.Response(401, json={"detail": "bad key"})

    r = _judge(jev_settings, unauthorized).can_answer("q", EVIDENCE)
    assert r.probability is None and r.error == "status_401" and len(calls) == 1
    assert "test-key" not in json.dumps(r.attempts)

    def timeout(req):
        raise httpx.ReadTimeout("느림", request=req)

    r = _judge(jev_settings, timeout).can_answer("q", EVIDENCE)
    assert r.error == "timeout" and len(r.attempts) == 3  # 첫 시도 + 재시도 2번


def test_bad_response(jev_settings):
    r = _judge(jev_settings, lambda req: httpx.Response(200, json={"answers": {}})).can_answer("q", EVIDENCE)
    assert r.probability is None and r.error == "bad_response"
    r = _judge(jev_settings, lambda req: _ok(1.5)).can_answer("q", EVIDENCE)
    assert r.error == "bad_probability"


def test_get_judge(settings, jev_settings):
    assert get_judge(settings.model_copy(update={"judge_provider": "none"})) is None
    j = get_judge(jev_settings)
    assert j.name == "jev_typesafe"
    j.close()
    with pytest.raises(RuntimeError):
        get_judge(jev_settings.model_copy(update={"typesafe_api_key": SecretStr("")}))
    with pytest.raises(NotImplementedError):
        get_judge(settings.model_copy(update={"judge_provider": "llm"}))
