"""리랭커 정렬·평가 연결·"확인 불가" 2단계 판단. 기본은 가짜 리랭커, 실제 모델은 `uv run pytest -m reranker_model`."""

from uuid import uuid4

import pytest

from app.retrieval.evaluate import Question, score_results, summarize
from app.retrieval.rerank import rerank
from app.retrieval.search import is_answerable


class FakeReranker:
    """텍스트에 질문 단어가 몇 개 들어 있는지로 점수(0~1)."""

    def score(self, query, texts):
        words = query.split()
        return [sum(w in t for w in words) / len(words) for t in texts]


def _row(i, text, book, page, score):
    return {
        "id": uuid4(), "title": f"t{i}", "clean_text": text, "embedding_text": "제목\n" + text,
        "book_id": book, "printed_page_number": page, "score": score,
    }


def test_rerank_reorders_and_keeps_vector_rank():
    b = uuid4()
    rows = [_row(1, "관련 없음", b, "1", 0.7), _row(2, "지니 지수 불순도", b, "2", 0.6), _row(3, "지니", b, "3", 0.5)]
    out = rerank("지니 지수", rows, FakeReranker(), "clean_text")
    assert [r["printed_page_number"] for r in out] == ["2", "3", "1"]
    assert [r["vector_rank"] for r in out] == [2, 3, 1]
    assert out[0]["vector_score"] == 0.6 and out[0]["score"] == out[0]["rerank_score"] == 1.0


def test_rerank_ties_keep_vector_order_and_uses_input_field():
    b = uuid4()
    rows = [_row(1, "a", b, "1", 0.7), _row(2, "b", b, "2", 0.6)]
    out = rerank("제목", rows, FakeReranker(), "embedding_text")  # 둘 다 embedding_text에만 "제목"
    assert [r["vector_rank"] for r in out] == [1, 2] and all(r["rerank_score"] == 1.0 for r in out)
    assert [r["rerank_score"] for r in rerank("제목", rows, FakeReranker(), "clean_text")] == [0.0, 0.0]


def test_score_results_with_reranker_and_rerank_summary():
    b = uuid4()
    ids = {"subject1": b}
    qs = [Question("a1", "지니 지수", "subject1", ["2"]), Question("n1", "카프카 토픽", "", [])]
    cands = [
        [_row(1, "엔트로피", b, "1", 0.7), _row(2, "지니 지수", b, "2", 0.6)],
        [_row(1, "토픽 모델링", b, "9", 0.55)],
    ]
    res = score_results(qs, cands, ids, FakeReranker(), "clean_text")
    a, n = res
    assert (a.vector_rank, a.rank, a.top_score, a.rerank_top_score) == (2, 1, 0.7, 1.0)
    assert a.top[0]["vector_rank"] == 2 and a.top[0]["subject"] == "subject1"
    assert n.rank is None and n.rerank_top_score == 0.5 and n.rerank_seconds is not None

    s = summarize(res, k=5, thresholds=[0.5], rerank_thresholds=[0.6])
    assert s["overall"]["hit@1"]["count"] == 1
    rt = s["rerank_thresholds"][0]
    assert rt["answerable_pass"]["count"] == 1 and rt["unanswerable_block"]["count"] == 1
    # 2단계: 하한 0.0/0.5 × 임계값 0.6
    assert [(t["vector_floor"], t["rerank_threshold"]) for t in s["two_stage"]] == [(0.0, 0.6), (0.5, 0.6)]
    assert s["rerank_top_score"]["unanswerable"]["max"] == 0.5
    assert s["rerank_seconds"]["n"] == 2


def test_score_results_without_reranker_has_no_rerank_summary():
    b = uuid4()
    res = score_results([Question("a", "x", "subject1", ["1"])], [[_row(1, "x", b, "1", 0.6)]], {"subject1": b})
    assert res[0].rerank_top_score is None and res[0].vector_rank is None
    assert "rerank_thresholds" not in summarize(res, k=5, thresholds=[0.5])


def test_is_answerable_three_zones(settings):
    s = settings.model_copy(update={
        "answerable_min_vector_score": 0.45, "answerable_min_rerank_score": 0.03, "answerable_confident_rerank_score": 0.15,
    })
    assert is_answerable(s, None, None) == ("reject", "no_result")
    assert is_answerable(s, 0.40, 0.9) == ("reject", "vector_below_floor")
    assert is_answerable(s, 0.60, 0.01) == ("reject", "rerank_below_floor")
    assert is_answerable(s, 0.60, 0.03) == ("gray", "rerank_gray")  # 하한 이상
    assert is_answerable(s, 0.60, 0.10) == ("gray", "rerank_gray")
    assert is_answerable(s, 0.60, 0.15) == ("answer", "ok")  # 상한 이상
    assert is_answerable(s, 0.60, None) == ("answer", "no_reranker")  # 리랭커 없으면 1단계만


def test_rerank_zone_bounds_must_be_ordered(settings):
    from pydantic import ValidationError

    from app.core.config import Settings

    data = settings.model_dump() | {"answerable_min_rerank_score": 0.2, "answerable_confident_rerank_score": 0.1}
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


@pytest.mark.reranker_model
def test_real_reranker_prefers_relevant_passage(settings):
    """RERANKER_MODEL(비면 BAAI/bge-reranker-v2-m3)을 실제로 로드한다. 모델이 미리 받아져 있어야 함."""
    from app.retrieval.rerank import get_reranker, release_reranker

    r = get_reranker(settings, settings.reranker_model or "BAAI/bge-reranker-v2-m3")
    try:
        good, bad = r.score(
            "의사결정나무에서 지니 지수는 무엇을 측정하나요?",
            ["지니 지수는 노드의 불순도를 측정하는 지표로, 값이 작을수록 순수하다.", "데이터베이스의 정규화는 중복을 줄인다."],
        )
        assert 0.0 <= bad < good <= 1.0
    finally:
        release_reranker()
