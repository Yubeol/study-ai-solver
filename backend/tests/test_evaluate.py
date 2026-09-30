"""검색 평가 계산(질문 파일 검사, 정답 순위, 요약). DB·모델 없이 돈다."""

from uuid import uuid4

import pytest

from app.retrieval.evaluate import Question, Result, find_rank, parse_questions, summarize

KEYS = {"subject1", "subject2", "subject3"}


def test_parse_questions_ok_with_bom_quotes_and_empty_pages():
    text = (
        "﻿id,question,subject,pages,note\n"
        "q01,DIKW 피라미드에서 지혜란?,subject1,18,\n"
        'q02,"분석 기획, 하향식 접근법이란?",subject2,93|94,메모\n'
        "\n"
        "q03,김치찌개 끓이는 법은?,,,자료에 없음\n"
    )
    qs = parse_questions(text, KEYS)
    assert [q.id for q in qs] == ["q01", "q02", "q03"]
    assert qs[1].question == "분석 기획, 하향식 접근법이란?" and qs[1].pages == ["93", "94"]
    assert qs[0].answerable and not qs[2].answerable


def test_parse_questions_reports_all_errors_with_line_numbers():
    text = (
        "id,question,subject,pages,note\n"
        "q01,질문,subject9,18,\n"
        "q01,질문,subject1,18,\n"
        "q02,,subject1,18,\n"
        "q03,질문,,18,\n"
        "q04,쉼표, 있음,subject1,18,\n"
    )
    with pytest.raises(ValueError) as e:
        parse_questions(text, KEYS)
    msg = str(e.value)
    for expected in ["2줄: subject 'subject9'", "3줄: id 중복", "4줄: question", "5줄: pages가 있으면", "6줄: 칸 수 6개"]:
        assert expected in msg


def test_parse_questions_rejects_bad_header():
    with pytest.raises(ValueError, match="머리행"):
        parse_questions("번호,질문\n1,a\n", KEYS)


def test_find_rank_needs_same_book_and_page():
    b1, b2 = uuid4(), uuid4()
    rows = [
        {"book_id": b2, "printed_page_number": "18"},  # 쪽은 같지만 다른 과목
        {"book_id": b1, "printed_page_number": "17"},
        {"book_id": b1, "printed_page_number": "19"},
    ]
    ids = {"subject1": b1, "subject2": b2}
    assert find_rank(Question("q", "x", "subject1", ["18", "19"]), rows, ids) == 3
    assert find_rank(Question("q", "x", "subject1", ["30"]), rows, ids) is None
    assert find_rank(Question("q", "x", "", []), rows, ids) is None


def _r(qid, subject, rank, score, answerable=True):
    return Result(Question(qid, "x", subject, ["1"] if answerable else []), rank, score)


def test_summarize_hits_and_thresholds():
    results = [
        _r("a", "subject1", 1, 0.70),
        _r("b", "subject1", 3, 0.55),
        _r("c", "subject2", None, 0.45),
        _r("u1", "", None, 0.42, answerable=False),
        _r("u2", "", None, 0.52, answerable=False),
    ]
    s = summarize(results, k=5, thresholds=[0.5])
    o = s["overall"]
    assert o["n"] == 3
    assert (o["hit@1"]["count"], o["hit@3"]["count"], o["hit@5"]["count"]) == (1, 2, 2)
    assert o["mrr"] == round((1 + 1 / 3) / 3, 3)
    assert s["by_subject"]["subject1"]["hit@3"]["rate"] == 1.0
    assert s["by_subject"]["subject2"]["hit@5"]["count"] == 0
    assert s["missed"] == ["c"]
    t = s["thresholds"][0]
    assert t["answerable_pass"]["count"] == 2  # 0.70, 0.55
    assert t["answerable_pass_and_hit"]["count"] == 2
    assert t["unanswerable_block"]["count"] == 1  # 0.42만 차단
    assert s["top_score"]["unanswerable"] == {"min": 0.42, "median": 0.52, "max": 0.52}


def test_summarize_without_unanswerable_questions():
    s = summarize([_r("a", "subject1", 2, 0.6)], k=5, thresholds=[0.4])
    assert s["thresholds"][0]["unanswerable_block"]["rate"] is None
    assert s["top_score"]["unanswerable"] is None
