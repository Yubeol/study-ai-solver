"""객관식 일관성 검사(D-028): 보기별 판정 추출과 모순 조건."""

from app.qa.mcq_check import (
    CONTRADICTED, SUPPORTED, UNKNOWN, UNVERIFIED, check_mcq, is_negative, line_verdict, option_lines,
)

NEG_Q = "빅데이터 분석 방법론에 대한 설명 중 올바르지 않은 것은?\n① 가\n② 나\n③ 다\n④ 라"
POS_Q = "상관분석에 대한 설명 중 옳은 것은?\n① 가\n② 나\n③ 다\n④ 라"


def test_negative_stem_only_before_options():
    assert is_negative(NEG_Q) and not is_negative(POS_Q)
    assert is_negative("분석 업무 파악 영역에 해당하지 않는 것은?\n① 가\n② 나")
    # 보기 안의 "적절하지 않은"은 문제 유형을 바꾸지 않는다
    assert not is_negative("옳은 것은?\n① 적절하지 않은 방법\n② 나")


def test_line_verdict_synonyms_and_last_expression():
    assert line_verdict("①은 근거에 없어 확인되지 않는다.") == UNVERIFIED
    assert line_verdict("③은 책임원칙 훼손 설명으로 옳지 않다 [1].") == CONTRADICTED
    assert line_verdict("①은 일차 분석으로도 효과를 얻는다고 하므로 정면으로 어긋난다 [2].") == CONTRADICTED
    assert line_verdict("①은 사실 분석 업무이므로 분석 업무 파악 영역에 해당한다 [1].") == SUPPORTED
    assert line_verdict("④는 탐색 방법이 아니며 회귀분석 방법이므로 적절하지 않다 [1].") == CONTRADICTED
    # 이유와 결론이 맞지 않아도 결론 표현만 본다(검사 범위 밖)
    assert line_verdict("④는 언급이 근거에 없으므로 적절하다 [1].") == SUPPORTED
    assert line_verdict("③은 소규모 웨어하우스라 할 수 있음 [3].") == UNKNOWN
    # 뒤 문장에 다른 보기 판정이 붙어도 첫 판정 문장만 본다
    assert line_verdict("①은 근거에 없어 확인되지 않는다. [1]은 … 하므로 ③은 적절하다 [1].") == UNVERIFIED


def test_option_lines_inline_and_multiline():
    lines = option_lines("①은 가이므로 적절하다 [1]. ②는 나이므로 적절하지 않다 [2].\n(3)은 근거에서 확인되지 않는다.")
    assert sorted(lines) == [1, 2, 3] and lines[2].startswith("②는")
    # 문장 중간의 "③은"은 줄 머리가 아니다
    assert sorted(option_lines("①은 ③은 다르다고 하므로 적절하다 [1].")) == [1]


def test_p84_like_inconsistent():
    exp = ("①은 근거에 없어 확인되지 않는다.\n②는 근거에 없어 확인되지 않는다.\n"
           "③은 수행할 필요가 없으므로 적절하다 [1].\n④는 위험 관리 계획서를 작성하므로 적절하다 [2].")
    c = check_mcq(NEG_Q, "정답은 ①이다 [1].", exp)
    assert c["negative"] and c["chosen"] == 1 and not c["consistent"]
    assert len(c["reasons"]) == 2 and "0개" in c["reasons"][0] and "확인되지 않는다" in c["reasons"][1]


def test_consistent_negative_and_positive():
    exp = "①은 적절하다 [1].\n②는 적절하다 [1].\n③은 근거와 어긋나므로 적절하지 않다 [2].\n④는 근거에서 확인되지 않는다."
    assert check_mcq(NEG_Q, "정답은 ③이다 [2].", exp)["consistent"]
    exp = "①은 적절하지 않다 [1].\n②는 옳지 않다 [1].\n③은 근거에서 확인되지 않는다.\n④는 적절하다 [2]."
    c = check_mcq(POS_Q, "정답은 ④이다 [2].", exp)
    assert c["consistent"] and c["option_verdicts"] == {"1": CONTRADICTED, "2": CONTRADICTED, "3": UNVERIFIED, "4": SUPPORTED}


def test_chosen_differs_and_two_supported():
    exp = "①은 적절하다 [1].\n②는 적절하지 않다 [1].\n③은 적절하지 않다 [1].\n④는 적절하지 않다 [1]."
    c = check_mcq(POS_Q, "정답은 ②이다 [1].", exp)
    assert not c["consistent"] and "다름" in c["reasons"][0]
    exp = "①은 적절하다 [1].\n②는 적절하다 [1].\n③은 적절하지 않다 [1].\n④는 적절하지 않다 [1]."
    assert "2개" in check_mcq(POS_Q, "정답은 ①이다 [1].", exp)["reasons"][0]


def test_not_mcq_or_no_choice():
    assert check_mcq("DIKW 피라미드에서 지혜란?", "지혜는 …이다 [1].", "설명 [1].") is None
    assert check_mcq(POS_Q, "근거로 판단하기 어렵다.", "") is None
