"""객관식 일관성 검사 (D-028). 답변 풀이의 보기별 판정과 고른 번호가 서로 맞는지 코드로 본다.

프롬프트 규칙 8(D-027)대로 explanation은 보기마다 "①은 ~이므로 적절하다 [n]." 한 줄이다.
- 보기 줄의 판정: 판정 표현이 있는 첫 문장에서 **마지막 표현**(예: "근거에 없어 확인되지 않는다" → 확인되지 않는다).
  적절하다(옳다·올바르다·맞다·해당한다) / 적절하지 않다(옳지 않다·올바르지 않다·부적절하다·틀리다·어긋난다·해당하지 않는다)
  / 확인되지 않는다(확인할 수 없다). 못 뽑으면 "알 수 없음"(기록만).
- 모순 조건:
  - 부정형 문제(문제 본문에 "적절하지 않은/옳지 않은/올바르지 않은/부적절한/틀린/아닌 것/해당하지 않는"):
    "적절하지 않다"가 정확히 하나이고 그 번호가 고른 번호와 같아야 한다.
  - 긍정형 문제: "적절하다"가 정확히 하나이고 그 번호가 고른 번호와 같아야 한다.
  - 고른 번호의 줄이 "확인되지 않는다"이면 모순.
- 모순이어도 답을 거절로 바꾸지 않는다(호출 측이 "근거 확신 낮음"을 붙이고 이유를 기록).
- 판정 이유와 결론이 맞는지(예: "근거에 없으므로 적절하다")는 보지 않는다.
"""

import re

from app.qa.mcq_run import extract_choice

SUPPORTED = "적절하다"
CONTRADICTED = "적절하지 않다"
UNVERIFIED = "확인되지 않는다"
UNKNOWN = "알 수 없음"
_CIRCLED = "①②③④"

# 부정형 문제 본문 표현
_NEGATIVE_STEM = re.compile(r"적절하지\s*않은|옳지\s*않은|올바르지\s*않은|부적절한|틀린|아닌\s*것|해당하지\s*않는")
# 판정 표현. 같은 위치에서는 앞 대안이 먼저 맞으므로 부정·미확인을 긍정보다 앞에 둔다("적절하지 않" ⊃ "적절하").
_VERDICT = re.compile(
    r"(?P<neg>부적절하|적절하지\s*않|옳지\s*않|올바르지\s*않|맞지\s*않|해당하지\s*않|틀리|틀린|어긋나|어긋난)"
    r"|(?P<unv>확인되지\s*않|확인할\s*수\s*없)"
    r"|(?P<pos>적절하|옳다|옳으므로|옳은|올바르|맞다|맞으므로|해당한다|해당하므로|해당된다)"
)
# 보기 줄 안의 문장 경계(마침표 뒤 공백, 줄바꿈). "0.5"처럼 공백 없는 점은 경계가 아니다.
_LINE_SENTENCE = re.compile(r"(?<=\.)\s+|\n+")
# 보기 줄 머리: "①은", "② 는", "(3)은"
_OPTION_HEAD = re.compile(r"([①②③④]|\(\s*[1-4]\s*\))\s*(?:은|는)")


def is_negative(question: str) -> bool:
    return bool(_NEGATIVE_STEM.search(_stem(question)))


def _stem(question: str) -> str:
    """첫 보기 기호 앞까지(문제 본문)."""
    m = re.search(r"[①②③④]", question)
    return question if m is None else question[: m.start()]


def _num(tok: str) -> int:
    tok = tok.strip().strip("()").strip()
    return _CIRCLED.index(tok) + 1 if tok in _CIRCLED else int(tok)


def option_lines(explanation: str) -> dict[int, str]:
    """보기 번호 → 그 보기 줄. 줄 머리는 글 처음·줄바꿈 뒤·문장 끝(". " 또는 "] ") 뒤에 오는 "①은" 형태만 인정한다."""
    heads = []
    for m in _OPTION_HEAD.finditer(explanation):
        before = explanation[: m.start()].rstrip(" \t")
        if not before or before.endswith(("\n", ".", "]", "다")):
            heads.append(m)
    lines: dict[int, str] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(explanation)
        lines.setdefault(_num(m.group(1)), explanation[m.start():end].strip())
    return lines


def line_verdict(line: str) -> str:
    """판정 표현이 있는 첫 문장의 마지막 표현. 보기 줄에 다른 보기 이야기가 이어 붙은 경우
    ("①은 … 확인되지 않는다. [1]은 … ③은 적절하다")에 뒤 문장 판정을 가져오지 않기 위해 첫 문장만 본다."""
    for sentence in _LINE_SENTENCE.split(line):
        matches = list(_VERDICT.finditer(sentence))
        if matches:
            return {"neg": CONTRADICTED, "unv": UNVERIFIED, "pos": SUPPORTED}[matches[-1].lastgroup]
    return UNKNOWN


def check_mcq(question: str, answer: str, explanation: str) -> dict | None:
    """객관식이 아니면 None. 객관식이면 {is_mcq, negative, chosen, option_verdicts, consistent, reasons}."""
    if len(set(re.findall(r"[①②③④]", question))) < 2:
        return None
    chosen = extract_choice(answer or "")
    if chosen is None:
        return None
    negative = is_negative(question)
    verdicts = {n: line_verdict(t) for n, t in sorted(option_lines(explanation or "").items())}
    target = CONTRADICTED if negative else SUPPORTED
    hits = [n for n, v in verdicts.items() if v == target]
    reasons = []
    kind = "부정형" if negative else "긍정형"
    if len(hits) != 1:
        reasons.append(f"{kind}인데 '{target}' 보기가 {len(hits)}개({_fmt(hits)})")
    elif hits[0] != chosen:
        reasons.append(f"'{target}' 보기 {_fmt(hits)}와 고른 번호 {_fmt([chosen])}가 다름")
    if verdicts.get(chosen) == UNVERIFIED:
        reasons.append(f"고른 번호 {_fmt([chosen])}의 줄이 '{UNVERIFIED}'")
    return {
        "is_mcq": True,
        "negative": negative,
        "chosen": chosen,
        "option_verdicts": {str(n): v for n, v in verdicts.items()},
        "consistent": not reasons,
        "reasons": reasons,
    }


def _fmt(nums: list[int]) -> str:
    return ",".join(_CIRCLED[n - 1] for n in nums) if nums else "없음"
