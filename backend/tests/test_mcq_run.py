"""기출 객관식 파서(app.qa.mcq_run). 교재 원문 대신 같은 모양의 지어낸 문장을 쓴다."""

from app.qa.mcq_run import chosen_options, parse_question, split_block, summarize


def test_parse_answer_after_label_and_strip_marks():
    seg = [
        "7 다음 중 과일이 아닌 것은? [12회 출제]",
        "① 사과 ② 배 V",
        "③ 감자 ④ 포도",
        "정답",
        "③",
        "해설 감자는 채소다. 보기 ③ 참고",
    ]
    status, f = parse_question(seg)
    assert status == "ok"
    assert f["number"] == 7 and f["answer"] == 3
    assert f["stem"] == "다음 중 과일이 아닌 것은?"
    assert f["options"] == {"1": "사과", "2": "배", "3": "감자", "4": "포도"}
    assert f["explanation"].startswith("감자는 채소다")


def test_inline_answer_digit_and_paren():
    assert parse_question(["색이 아닌 것은?① 빨강② 파랑③ 소리④ 초록 정답(3 해설 소리"])[1]["answer"] == 3
    assert parse_question(["색이 아닌 것은?① 빨강② 파랑③ 소리④ 초록 정답3해설 소리"])[1]["answer"] == 3


def test_answer_label_glued_to_option_is_not_answer():
    # "정답① 보기문"은 보기 ① 시작이므로 정답으로 보지 않는다.
    status, _ = parse_question(["옳은 것은? 정답① 하나다. ② 둘이다. ③ 셋이다. ④ 넷이다. 해설 하나다."])
    assert status.startswith("정답 번호 없음")


def test_missing_option_marker_is_excluded():
    status, _ = parse_question(["옳은 것은?① 하나 2 둘 ③ 셋 ④ 넷", "정답 ①"])
    assert status.startswith("보기 기호 개수 이상")


def test_conflicting_answers_excluded():
    status, _ = parse_question(["옳은 것은?", "① 하나 ② 둘 ③ 셋 ④ 넷", "2", "정답", "3"])
    assert status.startswith("정답 후보 여러 개")


def test_no_options_is_excluded():
    status, _ = parse_question(["다음을 무엇이라 하는가?", "정답 점추정"])
    assert status.startswith("보기 ①~④ 없음")


def test_split_block_and_chosen_options():
    segs = split_block(["기출유형 개념잡기", "1 문제A", "기출유형 개념잡기 2 문제B", "보기"])
    assert segs == [["1 문제A"], [" 2 문제B", "보기"]]
    assert chosen_options("정답은 ③ 감자다.") == [3]
    assert chosen_options("2번이 옳다") == [2]


def test_summarize_counts():
    results = [{"item": {"key": "a", "subject": "s1"}}, {"item": {"key": "b", "subject": "s1"}},
               {"item": {"key": "c", "subject": "s2"}}]
    grades = {"a": {"verdict": "맞음"}, "b": {"verdict": "틀림", "cause": "검색 실패"}}
    s = summarize(results, grades)
    assert s["by_subject"]["s1"]["맞음"] == 1 and s["by_subject"]["s1"]["틀림"] == 1
    assert s["by_subject"]["s2"]["미채점"] == 1
    assert s["causes"] == {"검색 실패": ["b"]}
