"""질의 흐름: 3구간 분기, 인용 검증, Gemini 재시도·폴백, query_logs 기록, /qa API. 모델·LLM은 가짜."""

import json
from uuid import uuid4

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from pydantic import SecretStr

from app.llm.gemini import GeminiClient, GeminiError, JsonResult
from app.qa import service
from app.qa.service import QaModels, answer_question, count_uncited_sentences, heading_path, validate_citations


class FakeEmbedder:
    def encode(self, texts):
        return np.zeros((len(texts), 4), dtype=np.float32)


class FakeReranker:
    def __init__(self, scores):
        self.scores = scores

    def score(self, query, texts):
        return self.scores[: len(texts)]


class FakeLlm:
    def __init__(self, data=None, error=False):
        self.data, self.error, self.calls = data, error, []

    def models_for(self, tier):
        return ["fake-model"]

    def generate_json(self, models, system, user, schema, temperature):
        self.calls.append(user)
        if self.error:
            raise GeminiError("실패", [{"model": "fake-model", "attempt": 1, "error": "status_503"}])
        return JsonResult(data=dict(self.data), model="fake-model", usage={"totalTokenCount": 10})

    def close(self):
        pass


def _rows(n=3, vector_top=0.6):
    return [
        {
            "id": uuid4(), "title": f"제목{i}", "raw_text": f"원문{i} •", "clean_text": f"본문{i}",
            "embedding_text": f"장 > 절{i}\n\n본문{i}", "book_title": "3과목", "printed_page_number": str(100 + i),
            "book_id": uuid4(), "score": vector_top - i * 0.01,
        }
        for i in range(1, n + 1)
    ]


@pytest.fixture
def logged(monkeypatch):
    out = []
    monkeypatch.setattr(service, "insert_query_log", lambda conn, settings, **kw: out.append(kw) or uuid4())
    return out


@pytest.fixture
def qa_settings(settings):
    return settings.model_copy(update={
        "search_top_k": 2, "search_candidates_n": 3, "reranker_input": "clean_text", "judge_provider": "none",
        "answerable_min_vector_score": 0.45, "answerable_min_rerank_score": 0.03, "answerable_confident_rerank_score": 0.15,
    })


def _run(monkeypatch, qa_settings, rows, rerank_scores, llm):
    monkeypatch.setattr(service, "search_theory", lambda conn, s, vec, k: rows[:k])
    models = QaModels(FakeEmbedder(), FakeReranker(rerank_scores) if rerank_scores else None, llm, None)
    return answer_question(None, qa_settings, models, "질문")


def test_heading_path():
    assert heading_path({"embedding_text": "A > B\n\n본문", "clean_text": "본문", "title": "B"}) == "A > B"
    assert heading_path({"embedding_text": "본문", "clean_text": "본문", "title": "B"}) == "B"


def test_validate_citations_removes_out_of_range():
    data = {"cited": [2, 7, 2, 0, "1", True], "answer": "답 [2][9]", "explanation": "설명 [1]", "confusions": ""}
    cited, check = validate_citations(data, 3)
    assert cited == [2]
    assert check["invalid_cited"] == [7, 0, "1", True]
    assert check["invalid_inline"] == [9] and data["answer"] == "답 [2]"
    assert check["inline_not_in_cited"] == [1]


def test_validate_citations_multi_number_brackets():
    data = {"cited": [1], "answer": "답 [1, 9]", "explanation": "가 [2, 3].", "confusions": ""}
    _, check = validate_citations(data, 2)
    assert data["answer"] == "답 [1]" and data["explanation"] == "가 [2]."
    assert check["invalid_inline"] == [9, 3] and check["inline_not_in_cited"] == [2]


def test_uncited_sentence_count():
    data = {"cited": [1], "answer": "답이다.",
            "explanation": "가는 나다 [1]. 다는 라다. 마는 바다. [2]\n- 사는 아다",
            "confusions": "자는 차다 [1], [2]."}
    _, check = validate_citations(data, 2)
    # "다는 라다."와 "- 사는 아다"가 인용 없음. "마는 바다. [2]"는 문장 뒤 인용으로 인정. answer는 세지 않음
    assert check["uncited_sentences"] == {"explanation": 2, "confusions": 0}
    assert check["uncited_sentence_count"] == 2
    assert count_uncited_sentences("") == 0 and count_uncited_sentences("값은 0.5이다 [1].") == 0


def test_mcq_explanation_unsupported_option_lines_not_counted_as_uncited():
    # 객관식 풀이 형식(프롬프트 규칙 8): 보기마다 한 줄, 근거 없는 보기는 인용 없이 "확인되지 않는다"
    data = {"cited": [1, 2], "answer": "정답은 ②이다 [2].",
            "explanation": "①은 가가 나이므로 적절하다 [1].\n②는 다다와 어긋나므로 적절하지 않다 [2].\n"
                           "③은 근거에서 확인되지 않는다.\n(4)는 근거에서 확인되지 않는다.",
            "confusions": ""}
    _, check = validate_citations(data, 2)
    assert check["uncited_sentence_count"] == 0
    assert check["unsupported_option_sentences"] == 2
    # 보기 줄이 아닌 문장에 같은 말이 있으면 여전히 인용 없는 문장으로 센다
    assert count_uncited_sentences("이 내용은 근거에서 확인되지 않는다.") == 1


def test_reject_zone_skips_llm(monkeypatch, qa_settings, logged):
    llm = FakeLlm({})
    r = _run(monkeypatch, qa_settings, _rows(), [0.01, 0.005, 0.0], llm)
    assert (r["zone"], r["zone_reason"], r["status"]) == ("reject", "rerank_below_floor", "unanswerable")
    assert r["answer"] == "자료에서 확인 불가" and llm.calls == [] and r["citations"] == []
    meta = logged[0]["metadata"]
    assert meta["zone"] == "reject" and "rerank_ms" in meta["timings_ms"] and "llm_ms" not in meta["timings_ms"]


def test_vector_floor_skips_rerank(monkeypatch, qa_settings, logged):
    r = _run(monkeypatch, qa_settings, _rows(vector_top=0.40), [0.9, 0.9, 0.9], FakeLlm({}))
    assert r["zone_reason"] == "vector_below_floor" and "rerank_ms" not in r["timings_ms"]


def test_gray_zone_without_judge_answers_with_low_confidence(monkeypatch, qa_settings, logged):
    llm = FakeLlm({"unanswerable": False, "answer": "답 [1]", "explanation": "설명 [3]", "confusions": "", "cited": [1, 3]})
    r = _run(monkeypatch, qa_settings, _rows(), [0.05, 0.10, 0.01], llm)
    assert (r["zone"], r["status"], r["confidence"], r["low_confidence"]) == ("gray", "answered", "low", True)
    # K=2라 근거는 2개 → [3]은 범위 밖으로 제거
    assert r["llm"]["citation_check"]["invalid_cited"] == [3] and r["explanation"] == "설명 "
    assert [c["n"] for c in r["citations"]] == [1] and r["citations"][0]["raw_text"].startswith("원문")
    assert "clean_text" not in r["evidence"][0]
    # LLM 입력에는 clean_text·제목 경로·과목·쪽
    assert "본문2" in llm.calls[-1] and "장 > 절2" in llm.calls[-1] and "3과목" in llm.calls[-1] and "102" in llm.calls[-1]


def test_answer_zone_high_confidence_and_log(monkeypatch, qa_settings, logged):
    llm = FakeLlm({"unanswerable": False, "answer": "답 [1]", "explanation": "설명 [2]", "confusions": "구분", "cited": [1, 2]})
    r = _run(monkeypatch, qa_settings, _rows(), [0.9, 0.5, 0.1], llm)
    assert (r["status"], r["confidence"], r["low_confidence"]) == ("answered", "high", False)
    kw = logged[-1]
    assert kw["question_text"] == "질문" and len(kw["retrieved_theory_ids"]) == 2
    assert "구분" in kw["answer"] and kw["token_usage"] == {"totalTokenCount": 10}
    assert kw["metadata"]["cited"] == [1, 2] and kw["metadata"]["model"] == "fake-model"
    assert set(kw["metadata"]["timings_ms"]) >= {"embed_ms", "vector_ms", "rerank_ms", "llm_ms", "total_ms"}


def test_llm_unanswerable_and_no_citation(monkeypatch, qa_settings, logged):
    llm = FakeLlm({"unanswerable": True, "answer": "x", "explanation": "근거에 없음", "confusions": "", "cited": [1]})
    r = _run(monkeypatch, qa_settings, _rows(), [0.9, 0.5, 0.1], llm)
    assert (r["status"], r["answer"], r["citations"]) == ("unanswerable", "자료에서 확인 불가", [])
    llm = FakeLlm({"unanswerable": False, "answer": "답", "explanation": "", "confusions": "", "cited": [9]})
    r = _run(monkeypatch, qa_settings, _rows(), [0.9, 0.5, 0.1], llm)
    assert r["status"] == "answered" and r["low_confidence"] is True  # 유효 인용 없음


def test_llm_error_and_no_reranker(monkeypatch, qa_settings, logged):
    r = _run(monkeypatch, qa_settings, _rows(), None, FakeLlm(error=True))
    assert (r["zone_reason"], r["status"]) == ("no_reranker", "error")
    assert logged[-1]["metadata"]["failed_attempts"][0]["error"] == "status_503"


def _gemini_settings(settings):
    return settings.model_copy(update={
        "gemini_model_lite": "lite-m", "gemini_model_strong": "strong-m", "gemini_max_retries": 1,
        "gemini_retry_base_seconds": 0, "gemini_api_key": SecretStr("test-key"),
    })


def _ok(model):
    text = json.dumps({"answer": "a"})
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}], "modelVersion": model,
                                     "usageMetadata": {"totalTokenCount": 3}})


def test_gemini_retry_then_fallback(settings):
    calls = []

    def handler(req):
        model = req.url.path.split("/")[-1].split(":")[0]
        calls.append(model)
        assert req.headers["x-goog-api-key"] == "test-key"
        body = json.loads(req.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(503) if model == "strong-m" else _ok(model)

    c = GeminiClient(_gemini_settings(settings), transport=httpx.MockTransport(handler), sleep=lambda s: None)
    r = c.generate_json(c.models_for("strong"), "sys", "user", {"type": "object"}, 0.2)
    assert calls == ["strong-m", "strong-m", "lite-m"]  # 재시도 1번 후 폴백
    assert r.data == {"answer": "a"} and r.model == "lite-m" and len(r.attempts) == 2
    assert "test-key" not in json.dumps(r.attempts)


def test_gemini_non_retryable_and_all_fail(settings):
    c = GeminiClient(_gemini_settings(settings), transport=httpx.MockTransport(lambda req: httpx.Response(400)),
                     sleep=lambda s: None)
    with pytest.raises(GeminiError) as e:
        c.generate_json(c.models_for("lite"), "s", "u", {}, 0)
    assert e.value.attempts == [{"model": "lite-m", "attempt": 1, "error": "status_400"}]


def test_insert_query_log_roundtrip(db_conn, settings):
    from app.repositories.query_logs import insert_query_log

    qid = insert_query_log(db_conn, settings, question_text="pytest 질의 기록", retrieved_theory_ids=["x"], answer="a",
                           latency_ms=5, token_usage=None, metadata={"flow": "pytest", "zone": "gray"})
    try:
        t = sql.Identifier(settings.db_schema)
        row = db_conn.execute(sql.SQL("SELECT metadata, retrieved_theory_ids FROM {}.query_logs WHERE id = %s").format(t),
                              (qid,)).fetchone()
        assert row == ({"flow": "pytest", "zone": "gray"}, ["x"])
    finally:
        db_conn.execute(sql.SQL("DELETE FROM {}.query_logs WHERE id = %s").format(sql.Identifier(settings.db_schema)), (qid,))


def test_qa_api(monkeypatch, logged):
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        assert client.post("/qa", json={"question": "질문"}).status_code == 503  # 모델 미로드(지연 로딩 안 함)
        monkeypatch.setattr(service, "search_theory", lambda conn, s, vec, k: _rows()[:k])
        llm = FakeLlm({"unanswerable": False, "answer": "답 [1]", "explanation": "", "confusions": "", "cited": [1]})
        app.state.qa_models = QaModels(FakeEmbedder(), FakeReranker([0.9, 0.5, 0.1]), llm, None)
        r = client.post("/qa", json={"question": "질문", "k": 2})
        assert r.status_code == 200 and r.json()["status"] == "answered" and r.json()["citations"][0]["n"] == 1
        assert client.post("/qa", json={"question": ""}).status_code == 422
