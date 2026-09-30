"""이론 청킹 규칙 (순수 함수, DB 없음). 규칙은 D-019 참고.

입력은 한 페이지의 원문 줄 목록과 앞 페이지에서 이어받은 상태(제목 경로, 기출 문제 블록 여부)다.
출력은 청크 목록, 제외 구간(기출 문제 블록), 다음 페이지로 넘길 상태다.

- raw_text: 청크에 속한 원문 줄을 수정 없이 이은 것(기출 표시 포함). 머리말/쪽번호 줄은 어느 청크에도 넣지 않는다.
- clean_text: 머리말·쪽번호 줄, 학습목표·출제 횟수 줄, 기출 표시("(★기출)" 등)를 뺀 것.
- embedding_text: "제목 경로 + 빈 줄 + clean_text". 제목 경로는 페이지를 넘어 이어받는다.
- 청크는 페이지를 넘지 않는다. 제목(절/항)이 바뀌면 새 청크, 길면 문단 단위로 나누고 겹침을 둔다.
"""

import re
from dataclasses import asdict, dataclass, field

# ---------- 줄 분류 패턴 ----------

_BOOK_HEADER = re.compile(r"AD[sS]P\s*한\s*권으로\s*끝내기")  # "2024 ADSP 한 권으로 끝내기 이론편"
_SUBJECT_FOOTER = re.compile(r"^(\|?\s*\d{1,3}\s*\|?\s*)?\d?\s*과목(\s+[^|]*)?(\s*\|?\s*\d{0,3})?$")
_CHAPTER_FOOTER = re.compile(r"^(\d{1,3}\s*\|\s*)?(\d{1,2})장\s+([^|]*[^|\s])(\s*\|\s*\d{0,3})?$")
_PIPE_ONLY = re.compile(r"^[|\s]+$")
_NO_WORD = re.compile(r"^[^\w가-힣]+$")  # 글자·숫자가 없는 조각("•", "->", "." 등)

_CHAPTER = re.compile(r"^(\d{1,2})장$")  # "1장" 다음 줄이 장 제목
_SECTION = re.compile(r"^(0\d)\s*([가-힣A-Za-z].*)$")  # "01 데이터와 정보", "03빅데이터 …"
_ITEM = re.compile(r"^(\d{1,2})\.\s*([가-힣A-Za-z(].*)$")  # "1. 데이터의 정의 (★기출)". "3.5" 같은 수치는 제외
_SUBITEM = re.compile(r"^(\d{1,2})\)\s*([가-힣A-Za-z(].*)$")  # "11) 다중공선성(Multicollinearity)"
_BOX = re.compile(r"^■\s*(\S.*)$")  # "■ 데이터 사이언스 3대 구성 요소 (★기출)"
_GLUED_BODY = "•"  # "2) 구간추정•일정한 …"처럼 제목 뒤에 본문이 붙은 줄의 경계
_TAIL_LINES = 4  # 페이지 끝 몇 줄 안의 "N장 제목"은 꼬리말로 본다

_EXAM_MARK = re.compile(r"\((★*)\s*(기출)?\)")  # "(★기출)", "(★★기출)", "(★)", "(기출)"
_STAR_RUN = re.compile(r"★+")
_EXAM_BLOCK_START = "기출유형 개념잡기"
_EXAM_BLOCK_END = ("학습정리", "용어 정리", "확대경", "학습목표")  # 이 말로 시작하는 줄(앞의 "|", "•"는 무시)에서 문제 블록이 끝난다
_EXAM_ROUND = re.compile(r"\[(\d+)회\s*출제\]")
_LEARNING_GOAL = "학습목표"
_FREQUENCY = "5년간 출제 횟수"
_CIRCLED = re.compile(r"[①-⑳]")

LEVELS = ("chapter", "section", "item", "subitem", "box")


@dataclass
class ChunkState:
    """페이지 사이에 이어받는 상태. page_metadata.chunking.end_state에 JSON으로 저장한다."""

    path: dict[str, str] = field(default_factory=dict)  # level → 제목(기출 표시 뺀 것)
    marks: dict[str, int] = field(default_factory=dict)  # level → 제목의 별 개수(기출 표시)
    in_exam: bool = False  # 페이지가 기출 문제 블록 안에서 끝났는지

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict | None) -> "ChunkState":
        if not d:
            return cls()
        return cls(path=dict(d.get("path") or {}), marks=dict(d.get("marks") or {}), in_exam=bool(d.get("in_exam")))

    def set_heading(self, level: str, title: str, stars: int | None) -> None:
        idx = LEVELS.index(level)
        for lv in LEVELS[idx:]:
            self.path.pop(lv, None)
            self.marks.pop(lv, None)
        self.path[level] = title
        if stars is not None:
            self.marks[level] = stars


@dataclass
class Chunk:
    sort_order: int
    title: str | None
    path: list[str]
    raw_text: str
    clean_text: str
    embedding_text: str
    exam_clues: list[dict]
    line_range: list[int]  # [시작, 끝] 페이지 원문 줄 번호(0부터, 끝 포함)
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)


@dataclass
class ExcludedBlock:
    section_type: str
    title: str
    reason: str
    line_range: list[int]
    continued: bool  # 앞 페이지에서 이어진 블록


@dataclass
class PageChunks:
    chunks: list[Chunk]
    excluded: list[ExcludedBlock]
    dropped_lines: list[int]  # 머리말·쪽번호 등으로 뺀 줄 번호
    end_state: ChunkState


@dataclass(frozen=True)
class ChunkParams:
    max_chars: int
    overlap_chars: int
    min_chars: int
    heading_max_chars: int  # 번호가 있어도 이보다 긴 줄은 본문(목록)으로 본다
    review_max_chars: int = 0  # clean_text가 이보다 짧고
    review_min_hangul_ratio: float = 0.0  # 한글 비율이 이보다 낮으면 needs_review(R 출력·그림 글자 조각)


# ---------- 줄 단위 판정 ----------


def is_page_furniture(line: str, printed_page: str | None) -> bool:
    """머리말/쪽번호/과목·장 꼬리말 줄인가. raw_text에서도 빼고 청크에 넣지 않는다."""
    s = line.strip()
    if not s:
        return True
    if _BOOK_HEADER.search(s) or _PIPE_ONLY.match(s):
        return True
    if printed_page and s.replace("|", "").strip() in (printed_page, "1" + printed_page):
        return True  # "14", "| 15", "127"(= "|27", D-018)
    if _SUBJECT_FOOTER.match(s) and len(s) <= 25:
        return True
    return bool(_CHAPTER_FOOTER.match(s) and "|" in s)


def strip_marks(text: str) -> str:
    """기출 표시를 뺀다: "(★기출)" 같은 괄호 표시와 남은 ★."""
    out = _EXAM_MARK.sub("", text)
    out = _STAR_RUN.sub("", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def mark_stars(text: str) -> int | None:
    """줄에 있는 기출 표시의 별 개수(표시가 없으면 None, "(기출)"만 있으면 0)."""
    stars = None
    for m in _EXAM_MARK.finditer(text):
        if m.group(1) or m.group(2):
            stars = max(stars or 0, len(m.group(1)))
    return stars


def parse_heading(line: str, max_chars: int) -> tuple[str, str, int | None, str] | None:
    """제목 줄이면 (level, 제목, 별 개수, 뒤에 붙은 본문). 장("1장")은 다음 줄과 합쳐야 해서 여기서 다루지 않는다.

    "4) 분석 수준 진단 결과 (★★★기출)•아래 그림 …"처럼 제목과 본문이 한 줄이면 "•" 앞을 제목으로 본다.
    """
    s = line.strip()
    found = _heading_only(s, max_chars)
    if found:
        return (*found, "")
    k = s.find(_GLUED_BODY)
    if k > 0:
        found = _heading_only(s[:k], max_chars)
        if found:
            return (*found, s[k:])
    return None


def _heading_only(s: str, max_chars: int) -> tuple[str, str, int | None] | None:
    title = strip_marks(s)
    if len(title) > max_chars or title.endswith(("다.", "다")):
        return None
    for level, pat in (("section", _SECTION), ("item", _ITEM), ("subitem", _SUBITEM), ("box", _BOX)):
        if pat.match(title):
            return level, title, mark_stars(s)
    return None


def frequency_items(text: str) -> list[dict]:
    """"① 데이터의 정의★③ 암묵지…★★" → [{"topic": "데이터의 정의", "stars": 1}, …]."""
    items = []
    for part in _CIRCLED.split(text):
        part = part.strip()
        if not part or part.startswith(_FREQUENCY):
            part = part.removeprefix(_FREQUENCY).replace("중요도", "").strip()
            if not part:
                continue
        stars = sum(len(r) for r in _STAR_RUN.findall(part))
        topic = _STAR_RUN.sub("", part).strip()
        if topic:
            items.append({"topic": topic, "stars": stars})
    return items


# ---------- 페이지 분석 ----------


@dataclass
class _Line:
    idx: int
    raw: str | None  # None이면 raw_text에 넣지 않는다(같은 원문 줄을 제목·본문으로 나눈 뒤쪽)
    clean: str | None  # None이면 clean_text에서 뺀다(학습목표·출제 횟수 등)
    heading: bool = False
    clues: list[dict] = field(default_factory=list)


def chunk_page(lines: list[str], printed_page: str | None, state: ChunkState, params: ChunkParams) -> PageChunks:
    state = ChunkState.from_json(state.to_json())  # 입력 상태는 바꾸지 않는다
    dropped: list[int] = []
    excluded: list[ExcludedBlock] = []
    # (path 스냅샷, 제목 별 표시, 줄 목록) 묶음. 제목이 바뀔 때마다 새 묶음
    groups: list[tuple[dict[str, str], dict[str, int], list[_Line]]] = []

    def current_group() -> list[_Line]:
        if not groups:
            new_group()
        return groups[-1][2]

    def new_group() -> None:
        groups.append((dict(state.path), dict(state.marks), []))

    exam: ExcludedBlock | None = None
    first = _next_content(lines, 0, printed_page, limit=len(lines))
    if state.in_exam and first is not None and looks_like_exam(lines[first]):
        exam = ExcludedBlock("exam_question", _EXAM_BLOCK_START, _exam_reason(), [first, first], continued=True)

    content = [k for k, ln in enumerate(lines) if ln.strip()]
    tail = set(content[-_TAIL_LINES:])
    _chapter_from_footer(lines, tail, state)
    mode = None  # "goal" | "freq": 학습목표·출제 횟수 줄이 이어지는 중
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if is_page_furniture(raw, printed_page) or (i in tail and _CHAPTER_FOOTER.match(s)):
            dropped.append(i)
            i += 1
            continue

        # 장 제목: "1장" + 다음 줄
        m = _CHAPTER.match(s)
        if m:
            j = _next_content(lines, i + 1, printed_page)
            if j is not None and len(lines[j].strip()) <= params.heading_max_chars:
                exam = _close_exam(exam, excluded, i - 1)
                mode = None
                state.set_heading("chapter", f"{m.group(1)}장 {strip_marks(lines[j])}", mark_stars(lines[j]))
                new_group()
                g = current_group()
                g.append(_Line(i, raw, None, heading=True))
                g.append(_Line(j, lines[j], None, heading=True))
                dropped.extend(k for k in range(i + 1, j))
                i = j + 1
                continue

        heading = parse_heading(s, params.heading_max_chars)
        if exam is not None:
            if heading is None and not s.lstrip("|•· ").startswith(_EXAM_BLOCK_END):
                if _EXAM_ROUND.search(s) and not exam.title.endswith("출제]"):
                    exam.title = f"{_EXAM_BLOCK_START} {_EXAM_ROUND.search(s).group(0)}"
                exam.line_range[1] = i
                i += 1
                continue
            exam = _close_exam(exam, excluded, i - 1)

        if s.startswith(_EXAM_BLOCK_START):
            mode = None
            exam = ExcludedBlock("exam_question", _EXAM_BLOCK_START, _exam_reason(), [i, i], continued=False)
            round_m = _EXAM_ROUND.search(s)
            if round_m:
                exam.title += f" {round_m.group(0)}"
            i += 1
            continue

        if heading is not None:
            mode = None
            level, title, stars, body = heading
            state.set_heading(level, title, stars)
            new_group()
            clues = [{"type": "heading_mark", "heading": title, "stars": stars}] if stars is not None else []
            current_group().append(_Line(i, raw, title, heading=True, clues=clues))
            if body:
                current_group().append(_Line(i, None, strip_marks(body), clues=_mark_clue(body)))
            i += 1
            continue

        # 학습목표 / 출제 횟수: exam_clues로 옮기고 clean_text에서는 뺀다
        if s.startswith(_LEARNING_GOAL):
            mode = "goal"
            rest = s.removeprefix(_LEARNING_GOAL).strip()
            clues = [{"type": "learning_goal", "text": rest}] if rest else []
            current_group().append(_Line(i, raw, None, clues=clues))
            i += 1
            continue
        if s.startswith(_FREQUENCY):
            mode = "freq"
            current_group().append(_Line(i, raw, None, clues=_freq_clue(s)))
            i += 1
            continue
        if mode == "goal" and not s.startswith(_FREQUENCY):
            current_group().append(_Line(i, raw, None, clues=[{"type": "learning_goal", "text": s}]))
            mode = None
            i += 1
            continue
        if mode == "freq" and _CIRCLED.match(s) and "★" in s:
            current_group().append(_Line(i, raw, None, clues=_freq_clue(s)))
            i += 1
            continue
        mode = None

        if _NO_WORD.match(s):
            dropped.append(i)
            i += 1
            continue

        current_group().append(_Line(i, raw, strip_marks(s), clues=_mark_clue(s)))
        i += 1

    if exam is not None:
        state.in_exam = True
        _close_exam(exam, excluded, exam.line_range[1])
    else:
        state.in_exam = False

    chunks: list[Chunk] = []
    pending: list[_Line] = []  # 본문 없는 묶음(장·절 제목, 학습목표 등)은 같은 페이지 다음 묶음 앞에 붙인다
    for path_map, marks, group in groups:
        group = pending + group
        if _body_chars(group) == 0:
            pending = group
            continue
        pending = []
        for piece in _split_group(group, params):
            chunk = _make_chunk(len(chunks), path_map, marks, piece)
            body = "\n".join(ln.clean for ln in piece if ln.clean and not ln.heading)
            if is_fragment(chunk.clean_text, body, params):
                chunk.needs_review = True
                chunk.review_reasons.append("short_low_hangul")
            chunks.append(chunk)
    return PageChunks(chunks=chunks, excluded=excluded, dropped_lines=sorted(set(dropped)), end_state=state)


def hangul_ratio(text: str) -> float:
    """공백을 뺀 글자 중 한글 음절 비율."""
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if "가" <= ch <= "힣") / len(chars)


def is_fragment(clean_text: str, body: str, params: ChunkParams) -> bool:
    """짧고 한글이 거의 없는 조각인가(R 출력, 그림 속 글자). 행은 만들되 검색에서 빼려고 needs_review로 둔다.

    길이는 clean_text 전체로, 한글 비율은 제목 줄을 뺀 본문으로 본다(제목 한글 때문에 조각이 통과하지 않도록).
    """
    return len(clean_text) < params.review_max_chars and hangul_ratio(body) < params.review_min_hangul_ratio


def _chapter_from_footer(lines: list[str], tail: set[int], state: ChunkState) -> None:
    """꼬리말 "3장 가치창조를 … |"의 장 번호가 현재 장과 다르면 장 제목을 꼬리말 값으로 바꾼다.

    장 첫 쪽의 "N장" 제목 줄이 텍스트에서 깨진 경우(1과목 3장)를 보완한다.
    """
    for k in sorted(tail):
        m = _CHAPTER_FOOTER.match(lines[k].strip())
        if not m:
            continue
        num, title = m.group(2), m.group(3).strip()
        current = state.path.get("chapter", "")
        if not current.startswith(f"{num}장"):
            state.set_heading("chapter", f"{num}장 {title}", None)
        return


def _exam_reason() -> str:
    return "기출 문제 블록(문항·보기·정답·해설): 이론 검색에서 제외"


def _close_exam(exam: ExcludedBlock | None, excluded: list[ExcludedBlock], end: int) -> None:
    if exam is not None:
        exam.line_range[1] = max(exam.line_range[0], min(exam.line_range[1], end))
        excluded.append(exam)


def looks_like_exam(line: str) -> bool:
    """앞 페이지의 기출 문제 블록이 이 줄로 이어지는가(출제 회차, 정답/해설, 보기 번호, 문항 번호+물음표)."""
    s = line.strip()
    return bool(
        _EXAM_ROUND.search(s)
        or s.startswith(("정답", "해설", "[해설"))
        or _CIRCLED.match(s)
        or re.match(r"^\d{1,2}\s+\S.*\?", s)
    )


def _next_content(lines: list[str], start: int, printed_page: str | None, limit: int = 3) -> int | None:
    for j in range(start, min(start + limit, len(lines))):
        if not is_page_furniture(lines[j], printed_page):
            return j
    return None


def _mark_clue(s: str) -> list[dict]:
    stars = mark_stars(s)
    return [{"type": "exam_mark", "stars": stars, "text": strip_marks(s)[:60]}] if stars is not None else []


def _freq_clue(s: str) -> list[dict]:
    items = frequency_items(s)
    return [{"type": "frequency", "items": items}] if items else []


def _split_group(group: list[_Line], params: ChunkParams) -> list[list[_Line]]:
    """제목 묶음 하나를 max_chars 이하 조각으로 나눈다(문단 = 원문 한 줄 단위, 문단 하나가 더 길면 자르지 않음)."""
    if not group:
        return []
    pieces: list[list[_Line]] = []
    cur: list[_Line] = []
    size = 0
    for ln in group:
        length = len(ln.clean or "")
        if cur and size + length > params.max_chars and _body_chars(cur) >= params.min_chars:
            pieces.append(cur)
            cur = _overlap_tail(cur, params.overlap_chars)
            size = sum(len(x.clean or "") for x in cur)
        cur.append(ln)
        size += length
    if pieces and _body_chars(cur) < params.min_chars:
        # 짧은 끝 조각은 앞 조각에 합친다(겹침으로 다시 넣은 줄은 빼고)
        pieces[-1].extend(x for x in cur if all(x is not y for y in pieces[-1]))
    elif cur:
        pieces.append(cur)
    return [p for p in pieces if _body_chars(p) > 0]


def _body_chars(lines: list[_Line]) -> int:
    return sum(len(x.clean) for x in lines if x.clean and not x.heading)


def _overlap_tail(lines: list[_Line], overlap_chars: int) -> list[_Line]:
    """앞 조각 끝의 본문 줄을 overlap_chars까지 다음 조각 앞에 다시 넣는다(문단 단위)."""
    tail: list[_Line] = []
    size = 0
    for ln in reversed(lines):
        if not ln.clean or ln.heading:
            break
        if tail and size + len(ln.clean) > overlap_chars:
            break
        if len(ln.clean) > overlap_chars:
            break
        tail.insert(0, ln)
        size += len(ln.clean)
    return tail


def _make_chunk(order: int, path_map: dict[str, str], marks: dict[str, int], lines: list[_Line]) -> Chunk:
    path = [path_map[lv] for lv in LEVELS if lv in path_map]
    clues: list[dict] = []
    for ln in lines:
        clues.extend(ln.clues)
    # 상위 제목에 붙은 기출 표시는 그 아래 모든 청크(다음 페이지 포함)에 이어받는다
    seen = {c["heading"] for c in clues if c["type"] == "heading_mark"}
    inherited = [
        {"type": "heading_mark", "heading": path_map[lv], "stars": marks[lv], "inherited": True}
        for lv in LEVELS
        if lv in marks and lv in path_map and path_map[lv] not in seen
    ]
    raw_text = "\n".join(ln.raw.strip() for ln in lines if ln.raw is not None)
    clean_text = "\n".join(ln.clean for ln in lines if ln.clean)
    path_text = " > ".join(path)
    return Chunk(
        sort_order=order,
        title=path[-1] if path else None,
        path=path,
        raw_text=raw_text,
        clean_text=clean_text,
        embedding_text=f"{path_text}\n\n{clean_text}" if path_text else clean_text,
        exam_clues=inherited + clues,
        line_range=[lines[0].idx, lines[-1].idx],
    )
