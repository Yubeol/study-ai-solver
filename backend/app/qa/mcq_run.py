"""기출 객관식 문제로 질의 API(POST /qa) 답변 품질을 확인한다.

기출 문제 블록은 청킹 때 excluded_sections(section_type='exam_question')로 빠졌고, 원문 위치
(text_uri + line_range, D-019)가 남아 있다. 그 위치로 팀 텍스트에서 블록을 꺼내 문제문·보기 ①~④·정답 번호를 파싱한다.

    cd backend
    uv run python -m app.qa.mcq_run extract
        → {REPORTS_DIR}/mcq/candidates.json/.md (모든 문제와 파싱 상태·제외 이유)
    (선택 파일 MCQ_SELECTION_PATH에 실행할 문제 key와 그림·표 때문에 뺀 문제를 적는다)
    uv run python -m app.qa.mcq_run run            # 서버를 켠 상태, 요청 간격 MCQ_REQUEST_INTERVAL_SECONDS
        → {REPORTS_DIR}/mcq/{시각}.json/.md (자동 채점: 답의 "정답은 ③" 번호 ↔ 정답 번호. 거절·번호 못 뽑음은 "검토 필요")
    uv run python -m app.qa.mcq_run report {시각}.json [--grades {시각}.grades.json] [--baseline 이전.grades.json]
        → 수동 채점(검토 필요 문제, note에 이유)을 자동 채점 위에 덮어 과목별 정답률·원인·비교용 표를 다시 쓴다
    uv run python -m app.qa.mcq_run compare A.json B.json [--baseline 이전.json]
        → {REPORTS_DIR}/mcq/compare-{시각}.md (과목별 정답률, 문제별 실행 간 바뀜·기준선 대비)

파싱은 엄격하게 한다(애매하면 제외):
- 보기: ①②③④ 기호가 각각 정확히 한 번(정답 표시로 쓰인 기호는 뺀 뒤). 기호가 깨진 블록은 제외.
- 정답: "정답" 바로 뒤의 번호(①~④, 1~4, (1)~(4)) 또는 "정답" 줄 바로 앞뒤 줄에 번호만 있는 경우.
  동그라미 번호는 보기 기호와 따로 한 번 더 나와야 정답으로 본다("정답① 보기문"처럼 보기 시작과 겹치면 정답 아님).
- 보기 끝에 붙은 손글씨 채점 표시(X, V, ×)는 답을 흘리므로 지운다.
결과 파일에는 교재 원문이 들어가므로 data/ 아래에만 둔다(커밋 금지).
"""

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings

CIRCLED = "①②③④"
VERDICTS = ("맞음", "틀림", "확인 불가", "답이 모호함")
CAUSES = ("검색 실패", "LLM 판단 오류", "정제 문제", "시각자료 필요", "기타")
_BLOCK_SPLIT = "기출유형 개념잡기"
_TAG = re.compile(r"\[?\s*\d+\s*회\s*(?:출제|기출)\s*\]?|\[?\s*출제\s*예상\s*\]?")
_HEADER = re.compile(r"ADSP\s*한\s*권으로\s*끝내기", re.IGNORECASE)
_HANGUL = re.compile(r"[가-힣]")
_ANSWER_LINE = re.compile(r"^[\[\(]?\s*([①②③④1-4])\s*[\]\)]?$")
_ANSWER_HEAD_LINE = re.compile(r"^\[?\s*정답\s*\]?$")
_ANSWER_INLINE = re.compile(r"정답\s*\]?\s*[\(\[]?\s*([①②③④]|[1-4](?![0-9.]))")
_TRAILING_MARK = re.compile(r"(?:\s+[xXvV]\.?|\s*[×✓]\.?)\s*$")
_STEM_NUMBER = re.compile(r"^(\d{1,2})\s*(?=\D)")


@dataclass
class McqItem:
    key: str  # "{과목 key}-p{쪽}-{쪽 안 순서}"
    subject: str  # page_map key (subject1~3)
    page: int  # 인쇄 쪽번호
    section_id: str
    number: int | None  # 교재의 문제 번호(파싱되면)
    status: str  # "ok" 또는 제외 이유
    stem: str = ""
    options: dict[str, str] = field(default_factory=dict)  # {"1": 보기 ①, ...}
    answer: int | None = None
    explanation: str = ""  # 교재 해설(채점 참고용)
    raw: str = ""  # 블록 원문(정리 전)


def _clean_lines(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        s = _TAG.sub(" ", line).strip()
        if not s or _HEADER.search(s):
            continue
        if _ANSWER_LINE.match(s) or "정답" in s or "해설" in s:
            out.append(s)
            continue
        # 한글·보기 기호가 없는 짧은 조각(쪽번호, "|", 그림 글자, 영문 OCR 찌꺼기)은 버린다.
        if not _HANGUL.search(s) and not any(c in s for c in CIRCLED) and len(s) < 15:
            continue
        out.append(s)
    return out


def _find_answer(lines: list[str], text: str) -> tuple[int | None, str]:
    """(정답 번호, 이유). 찾지 못하거나 후보가 둘 이상이면 None."""
    found: set[int] = set()
    for i, line in enumerate(lines):
        if _ANSWER_HEAD_LINE.match(line):
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines) and (m := _ANSWER_LINE.match(lines[j])):
                    found.add(_to_int(m.group(1)))
    pre = _before_expl(text)
    for m in _ANSWER_INLINE.finditer(pre):
        tok = m.group(1)
        if tok in CIRCLED and pre.count(tok) < 2:
            continue  # "정답① 보기문": 보기 시작 기호와 겹침
        found.add(_to_int(tok))
    if not found:
        return None, "정답 번호 없음(그림 표시이거나 해설만 있음)"
    if len(found) > 1:
        return None, f"정답 후보 여러 개 {sorted(found)}"
    return found.pop(), ""


def _before_expl(text: str) -> str:
    m = re.search(r"\[?해설", text)
    return text if m is None else text[: m.start()]


def _to_int(tok: str) -> int:
    return CIRCLED.index(tok) + 1 if tok in CIRCLED else int(tok)


def parse_question(segment: list[str]) -> tuple[str, dict]:
    """문제 한 개(기출유형 개념잡기 한 칸)를 파싱한다. (status, 필드). status가 "ok"가 아니면 제외 이유."""
    lines = _clean_lines(segment)
    text = "\n".join(lines)
    if not text.strip():
        return "빈 블록", {}
    expl = ""
    if (m := re.search(r"\[?해설\]?", text)) is not None:
        expl = " ".join(text[m.end():].split())
    if not any(c in text for c in CIRCLED):
        return "보기 ①~④ 없음(주관식·계산 문제이거나 보기 기호가 깨짐)", {"explanation": expl}
    answer, why = _find_answer(lines, text)
    if answer is None:
        return why, {"explanation": expl}

    # 정답 표시를 지운 본문에서 보기 기호 위치를 찾는다.
    for i, line in enumerate(lines):
        if _ANSWER_HEAD_LINE.match(line):
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines) and _ANSWER_LINE.match(lines[j]):
                    lines[j] = ""
    # 해설 안의 "보기 ④는 …" 같은 기호는 세지 않는다.
    body = _before_expl("\n".join(lines))
    body = _ANSWER_INLINE.sub(
        lambda m: m.group(0) if m.group(1) in CIRCLED and body.count(m.group(1)) < 2 else "정답", body)
    counts = {c: body.count(c) for c in CIRCLED}
    if any(n != 1 for n in counts.values()):
        return f"보기 기호 개수 이상 {counts}", {"explanation": expl}
    pos = sorted((body.index(c), c) for c in CIRCLED)
    stops = [m.start() for m in re.finditer(r"\[?정답|\[?해설", body)]
    if stops and min(stops) < pos[-1][0]:
        return "정답·해설 표시가 보기 사이에 있음(순서 깨짐)", {"explanation": expl}
    end = min(stops) if stops else len(body)

    stem = " ".join(body[: pos[0][0]].split())
    number = None
    if (m := _STEM_NUMBER.match(stem)) is not None:
        number, stem = int(m.group(1)), stem[m.end():].strip()
    options = {}
    for k, (p, c) in enumerate(pos):
        nxt = pos[k + 1][0] if k + 1 < len(pos) else end
        opt = " ".join(body[p + 1: nxt].split()).strip(" []")
        options[str(CIRCLED.index(c) + 1)] = _TRAILING_MARK.sub("", opt).strip()
    if not stem or any(not v for v in options.values()):
        return "문제문 또는 보기 내용 비어 있음", {"explanation": expl}
    return "ok", {"stem": stem, "options": dict(sorted(options.items())), "answer": answer,
                  "number": number, "explanation": expl}


def split_block(lines: list[str]) -> list[list[str]]:
    """블록 줄을 '기출유형 개념잡기' 단위로 나눈다(한 블록에 문제가 여러 개 있을 수 있음)."""
    segs: list[list[str]] = [[]]
    for line in lines:
        if _BLOCK_SPLIT in line:
            before, *rest = line.split(_BLOCK_SPLIT)
            if before.strip():
                segs[-1].append(before)
            for r in rest:
                segs.append([r] if r.strip() else [])
        else:
            segs[-1].append(line)
    return [s for s in segs if any(x.strip() for x in s)]


def question_text(item: dict) -> str:
    return item["stem"] + "\n" + "\n".join(f"{CIRCLED[int(k) - 1]} {v}" for k, v in item["options"].items())


_OPTION_TOKEN = r"[①②③④]|\(\s*[1-4]\s*\)|(?<![\d\[(])[1-4](?![\d\])])"
# 답변 앞머리 "정답은 ③이다", "정답: (3)", "정답은 3번" (프롬프트 규칙 8)
_CHOICE_HEAD = re.compile(r"정답\s*(?:은|는|:)?\s*(" + _OPTION_TOKEN + ")")


def option_number(tok: str) -> int:
    """보기 기호 ①~④ / (1)~(4) / 1~4 → 같은 번호 1~4."""
    tok = tok.strip().strip("()").strip()
    return _to_int(tok)


def chosen_options(answer: str) -> list[int]:
    """답변 문장에 나온 보기 번호(①~④, (N), "N번") 전체. 인용 "[n]"은 세지 않는다."""
    nums = [_to_int(c) for c in re.findall(r"[①②③④]", answer)]
    nums += [int(n) for n in re.findall(r"\(\s*([1-4])\s*\)", answer)]
    nums += [int(n) for n in re.findall(r"(?<![\d\[])([1-4])\s*번", answer)]
    return sorted(set(nums))


def extract_choice(answer: str) -> int | None:
    """모델이 고른 번호. "정답은 X"가 있으면 그 번호, 없으면 답에 나온 번호가 하나뿐일 때만 그 번호."""
    if (m := _CHOICE_HEAD.search(answer or "")) is not None:
        return option_number(m.group(1))
    nums = chosen_options(answer or "")
    return nums[0] if len(nums) == 1 else None


REVIEW = "검토 필요"


def auto_grade(rec: dict) -> dict:
    """뽑힌 번호와 정답 번호를 대조한 자동 채점. 거절·오류·번호 못 뽑음은 "검토 필요"."""
    r = rec.get("response")
    if not r:
        return {"verdict": REVIEW, "reason": "요청 실패"}
    if r.get("status") != "answered":
        return {"verdict": REVIEW, "reason": f"답변 안 함({r.get('status')})"}
    choice = extract_choice(r.get("answer") or "")
    if choice is None:
        return {"verdict": REVIEW, "reason": "번호를 못 뽑음"}
    return {"verdict": "맞음" if choice == rec["item"]["answer"] else "틀림", "reason": f"고른 번호 {choice}"}


# ---------------------------------------------------------------- extract

def load_blocks(settings: Settings) -> list[dict]:
    from app.db.connection import connect
    from app.ingestion.team_import import load_map
    from app.storage import get_storage

    subject_by_source = {b["source_name"]: b["key"] for b in load_map(settings)["books"]}
    storage = get_storage(settings)
    with connect(settings) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            sql.SQL(
                "SELECT e.id, e.source_region_ids, p.printed_page_number, b.source_name "
                "FROM {s}.excluded_sections e JOIN {s}.pages p ON p.id = e.page_id "
                "JOIN {s}.books b ON b.id = p.book_id WHERE e.section_type = 'exam_question' "
                "ORDER BY b.source_name, (p.page_metadata->>'upload_index')::int, "
                "(e.source_region_ids->0->'line_range'->>0)::int"
            ).format(s=sql.Identifier(settings.db_schema))
        ).fetchall()
    cache: dict[str, list[str]] = {}
    blocks = []
    for r in rows:
        lines: list[str] = []
        for reg in r["source_region_ids"]:
            uri = reg["text_uri"]
            if uri not in cache:
                cache[uri] = json.loads(storage.read(uri).decode("utf-8"))["text"].splitlines()
            a, b = reg["line_range"]
            lines += cache[uri][a: b + 1]
        blocks.append({"section_id": str(r["id"]), "subject": subject_by_source.get(r["source_name"], "?"),
                       "page": r["printed_page_number"], "lines": lines})
    return blocks


def extract_items(blocks: list[dict]) -> list[McqItem]:
    items: list[McqItem] = []
    seq: dict[tuple[str, int], int] = {}
    for b in blocks:
        for seg in split_block(b["lines"]):
            k = (b["subject"], b["page"])
            seq[k] = seq.get(k, 0) + 1
            status, f = parse_question(seg)
            items.append(McqItem(key=f"{b['subject']}-p{b['page']}-{seq[k]}", subject=b["subject"], page=b["page"],
                                 section_id=b["section_id"], number=f.get("number"), status=status,
                                 stem=f.get("stem", ""), options=f.get("options", {}), answer=f.get("answer"),
                                 explanation=f.get("explanation", ""), raw="\n".join(x for x in seg if x.strip())))
    return items


def candidates_markdown(items: list[McqItem]) -> str:
    ok = [i for i in items if i.status == "ok"]
    lines = ["# 기출 문제 파싱 결과", "",
             f"- 전체 {len(items)}문제, 파싱 성공 {len(ok)}"]
    for subj in sorted({i.subject for i in items}):
        sub = [i for i in items if i.subject == subj]
        lines.append(f"  - {subj}: {len(sub)}문제, 성공 {sum(i.status == 'ok' for i in sub)}")
    lines += ["", "| key | 번호 | 상태 | 문제문 앞부분 |", "|---|---|---|---|"]
    for i in items:
        head = (i.stem or i.raw.replace("\n", " "))[:50].replace("|", "/")
        lines.append(f"| {i.key} | {i.number or ''} | {i.status if i.status != 'ok' else f'ok(정답 {i.answer})'} | {head} |")
    lines += ["", "## 파싱 성공 문제", ""]
    for i in ok:
        lines += [f"### {i.key} (정답 {CIRCLED[i.answer - 1]})", "", question_text(asdict(i)).replace("\n", "  \n"),
                  "", f"해설: {i.explanation}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- run

def run_items(settings: Settings, items: list[dict], url: str, interval: float) -> list[dict]:
    results = []
    with httpx.Client(base_url=url, timeout=300) as client:
        for n, it in enumerate(items):
            if n:
                time.sleep(interval)  # Gemini 무료 한도 보호
            rec = {"item": it, "question_text": question_text(it)}
            try:
                resp = client.post("/qa", json={"question": rec["question_text"]})
                resp.raise_for_status()
                r = resp.json()
                rec["response"] = r
                rec["chosen"] = chosen_options(r.get("answer") or "")
                rec["choice"] = extract_choice(r.get("answer") or "")
                print(f"{it['key']}: {r['zone']}/{r['status']} 고른 번호 {rec['choice']} 정답 {it['answer']} "
                      f"인용 {[c['n'] for c in r['citations']]} {r['timings_ms']['total_ms']}ms")
            except httpx.HTTPError as e:
                rec |= {"response": None, "error": f"{type(e).__name__}: {e}"}
                print(f"{it['key']}: 실패 {rec['error']}")
            results.append(rec)
    return results


# ---------------------------------------------------------------- report

COUNT_KEYS = (*VERDICTS, REVIEW, "미채점")


def final_grades(results: list[dict], manual: dict) -> dict:
    """자동 채점 + 수동 채점(manual이 있으면 우선). 각 값에 source(자동/수동)와 auto(자동 결과)를 붙인다."""
    out = {}
    for rec in results:
        key, auto = rec["item"]["key"], auto_grade(rec)
        if key in manual:
            out[key] = {**manual[key], "source": "수동", "auto": auto["verdict"], "reason": auto["reason"]}
        else:
            out[key] = {**auto, "source": "자동"}
    return out


def summarize(results: list[dict], grades: dict) -> dict:
    by_subject: dict[str, dict] = {}
    causes: dict[str, list[str]] = {}
    for rec in results:
        key, subj = rec["item"]["key"], rec["item"]["subject"]
        g = grades.get(key) or {}
        s = by_subject.setdefault(subj, {"total": 0, **{v: 0 for v in COUNT_KEYS}})
        s["total"] += 1
        s[g.get("verdict") or "미채점"] += 1
        if g.get("verdict") and g["verdict"] != "맞음" and g.get("cause"):
            causes.setdefault(g["cause"], []).append(key)
    total = {"total": sum(s["total"] for s in by_subject.values())}
    for v in COUNT_KEYS:
        total[v] = sum(s[v] for s in by_subject.values())
    return {"by_subject": by_subject, "total": total, "causes": causes}


def _short(verdict: str) -> str:
    return "모호" if verdict == "답이 모호함" else verdict


def summary_table(summary: dict) -> list[str]:
    lines = ["| 과목 | 문제 | 맞음 | **틀림** | 확인 불가 | 모호 | 검토 필요 | 정답률 |", "|---|---|---|---|---|---|---|---|"]
    for subj, s in [*sorted(summary["by_subject"].items()), ("전체", summary["total"])]:
        rate = f"{s['맞음'] / s['total']:.0%}" if s["total"] else "-"
        extra = f" (+미채점 {s['미채점']})" if s["미채점"] else ""
        lines.append(f"| {subj} | {s['total']}{extra} | {s['맞음']} | **{s['틀림']}** | {s['확인 불가']} | "
                     f"{s['답이 모호함']} | {s[REVIEW]} | {rate} |")
    return lines


def compare_row(rec: dict, g: dict) -> dict:
    """비교용 표 한 줄: 문제 ID / 정답 / 고른 번호 / 판정 / 인용 쪽 / 걸린 시간."""
    r = rec.get("response") or {}
    choice = rec.get("choice") if "choice" in rec else extract_choice(r.get("answer") or "")
    if r and r.get("status") != "answered":
        choice = None
    total_ms = (r.get("timings_ms") or {}).get("total_ms")
    return {
        "key": rec["item"]["key"],
        "answer": CIRCLED[rec["item"]["answer"] - 1],
        "choice": CIRCLED[choice - 1] if choice else "-",
        "verdict": _short(g.get("verdict") or "미채점"),
        "pages": ", ".join(str(c["page"]) for c in r.get("citations", [])) or "-",
        "seconds": f"{total_ms / 1000:.1f}" if total_ms is not None else "-",
    }


def compare_table(results: list[dict], grades: dict, baseline: dict | None = None) -> list[str]:
    head = "| 문제 ID | 정답 | 고른 번호 | 판정 | 인용 쪽 | 시간(초) | 채점 |" + (" 이전 판정 |" if baseline else "")
    lines = [head, "|---|---|---|---|---|---|---|" + ("---|" if baseline else "")]
    for rec in results:
        g = grades.get(rec["item"]["key"]) or {}
        c = compare_row(rec, g)
        how = g.get("source", "")
        if g.get("source") == "수동":
            how += f"(자동: {g.get('auto')})"
        elif g.get("verdict") == REVIEW:
            how += f"({g.get('reason')})"
        row = (f"| {c['key']} | {c['answer']} | {c['choice']} | {c['verdict']} | {c['pages']} | {c['seconds']} | "
               f"{how} |")
        if baseline:
            row += f" {_short((baseline.get(c['key']) or {}).get('verdict', ''))} |"
        lines.append(row)
    return lines


def report_markdown(results: list[dict], grades: dict, summary: dict, baseline: dict | None) -> str:
    lines = ["# 기출 객관식으로 본 답변 품질", ""]
    meta = results[0].get("meta", {}) if results else {}
    if meta:
        lines += [f"- 실행: {meta.get('run_at')} / 서버 {meta.get('url')} / 요청 간격 {meta.get('interval')}초", ""]
    lines += ["## 요약", "", *summary_table(summary)]
    lines += ["", "맞지 않은 문제 원인: " + (", ".join(f"{c} {len(k)}({', '.join(k)})" for c, k in summary["causes"].items())
                                       or "없음"), ""]
    lines += ["## 비교용 표", "", "채점: 자동 = 고른 번호와 정답 번호 대조, 거절·번호 못 뽑음은 검토 필요 → 수동 채점(아래 메모).", "",
              *compare_table(results, grades, baseline), ""]
    notes = [(k, g) for k, g in grades.items() if g.get("source") == "수동"]
    if notes:
        lines += ["수동 채점 메모:", ""]
        lines += [f"- {k}: {g['verdict']}" + (f" / {g['cause']}" if g.get("cause") else "") + f" — {g.get('note') or '(이유 없음)'}"
                  for k, g in notes]
        lines.append("")
    for rec in results:
        it, r, g = rec["item"], rec.get("response") or {}, grades.get(rec["item"]["key"]) or {}
        lines += [f"## {it['key']} — 공식 정답 {CIRCLED[it['answer'] - 1]}", "",
                  rec["question_text"].replace("\n", "  \n"), "", f"- 교재 해설: {it['explanation']}"]
        if not r:
            lines += [f"- 요청 실패: {rec.get('error')}", ""]
            continue
        s = r["scores"]
        lines.append(f"- 판정: zone=`{r['zone']}`({r['zone_reason']}) / status=`{r['status']}` / 확신 낮음={r['low_confidence']}"
                     f" / 벡터 1위 {s['vector_top']} / 리랭커 1위 {s['rerank_top']} / {r['timings_ms']['total_ms']}ms")
        cc = (r.get("llm") or {}).get("citation_check")
        if cc:
            lines.append(f"- 인용 검증: {json.dumps(cc, ensure_ascii=False)}")
        c = compare_row(rec, g)
        lines.append(f"- 고른 번호: {c['choice']} / 인용 쪽: {c['pages']} / {c['seconds']}초")
        if g:
            lines.append(f"- **채점({g.get('source', '수동')}): {g.get('verdict')}**"
                         + (f" / 원인: {g['cause']}" if g.get("cause") else "")
                         + (f" — {g['note']}" if g.get("note") else (f" — {g['reason']}" if g.get("reason") else "")))
        # 답변 전문(줄바꿈 유지)
        lines += ["", f"**답**: {r['answer']}", ""]
        if r.get("explanation"):
            lines += ["**설명**:  ", r["explanation"].replace("\n", "  \n"), ""]
        if r.get("confusions"):
            lines += ["**헷갈리는 개념**:  ", r["confusions"].replace("\n", "  \n"), ""]
        lines.append("**넘긴 근거**: " + ", ".join(
            f"[{e['n']}] {e['page']}쪽(리랭커 {e['rerank_score']}){' ✔' if e['cited'] else ''}" for e in r["evidence"]))
        lines.append("")
        for c in r["citations"]:
            raw = c["raw_text"].strip().replace("\n", "\n> ")
            lines += [f"**인용 [{c['n']}]** {c['page']}쪽 · {c['path']}", "", f"> {raw}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="기출 객관식으로 /qa 답변 품질 확인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract", help="기출 블록 파싱 → mcq/candidates.json/.md")
    p_run = sub.add_parser("run", help="선택한 문제를 /qa로 실행(서버 필요)")
    p_run.add_argument("--url", default="http://127.0.0.1:8000")
    p_run.add_argument("--selection", default=None, help="선택 파일(기본 MCQ_SELECTION_PATH)")
    p_run.add_argument("--keys", default=None, help="선택 파일 대신 key 목록(쉼표 구분)")
    p_rep = sub.add_parser("report", help="자동 채점 + 수동 채점 파일을 합쳐 요약")
    p_rep.add_argument("result", help="run 결과 json(파일명만 주면 mcq 폴더에서 찾음)")
    p_rep.add_argument("--grades", default=None,
                       help="수동 채점 json {key: {verdict, cause, note}}(검토 필요 문제만, note에 이유). 없으면 자동 채점만")
    p_rep.add_argument("--baseline", default=None, help="비교할 이전 채점 json")
    p_cmp = sub.add_parser("compare", help="여러 실행 결과를 한 표로 비교 → mcq/compare-{시각}.md")
    p_cmp.add_argument("runs", nargs="+", help="run 결과 json들(같은 이름의 .grades.json이 있으면 수동 채점으로 씀)")
    p_cmp.add_argument("--baseline", default=None, help="기준선 run 결과 json(수정 전)")
    args = ap.parse_args(argv)

    settings = get_settings()
    out_dir = settings.reports_path / "mcq"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.cmd == "extract":
        items = extract_items(load_blocks(settings))
        (out_dir / "candidates.json").write_text(
            json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=1), encoding="utf-8")
        (out_dir / "candidates.md").write_text(candidates_markdown(items), encoding="utf-8")
        print(f"{len(items)}문제, 파싱 성공 {sum(i.status == 'ok' for i in items)} → {out_dir / 'candidates'}.json/.md")
        return 0

    if args.cmd == "run":
        cands = {c["key"]: c for c in json.loads((out_dir / "candidates.json").read_text(encoding="utf-8"))}
        if args.keys:
            keys = [k.strip() for k in args.keys.split(",") if k.strip()]
        else:
            sel_path = Path(args.selection) if args.selection else settings.mcq_selection_file
            keys = json.loads(sel_path.read_text(encoding="utf-8"))["selected"]
        bad = [k for k in keys if k not in cands or cands[k]["status"] != "ok"]
        if bad:
            print(f"파싱 성공 목록에 없는 key: {', '.join(bad)}")
            return 2
        if len(keys) > settings.mcq_max_questions:
            print(f"한 번에 {settings.mcq_max_questions}문제까지(MCQ_MAX_QUESTIONS, Gemini 무료 한도)")
            return 2
        meta = {"run_at": datetime.now().isoformat(timespec="seconds"), "url": args.url,
                "interval": settings.mcq_request_interval_seconds}
        results = run_items(settings, [cands[k] for k in keys], args.url, settings.mcq_request_interval_seconds)
        for r in results:
            r["meta"] = meta
        stem = datetime.now().strftime("%Y%m%d-%H%M%S")
        (out_dir / f"{stem}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        grades = final_grades(results, {})
        summary = summarize(results, grades)
        (out_dir / f"{stem}.md").write_text(report_markdown(results, grades, summary, None), encoding="utf-8")
        t = summary["total"]
        print(f"저장: {out_dir / stem}.json / .md — 자동 채점 맞음 {t['맞음']}, 틀림 {t['틀림']}, 검토 필요 {t[REVIEW]}"
              f" (검토 필요는 {stem}.grades.json에 수동 채점 후 report)")
        return 0

    if args.cmd == "compare":
        return _compare(out_dir, args.runs, args.baseline)

    path = _find(out_dir, args.result)
    results = json.loads(path.read_text(encoding="utf-8"))
    manual = _load_grades(_find(out_dir, args.grades)) if args.grades else {}
    for k, g in manual.items():
        if not g.get("note"):
            print(f"경고: {k} 수동 채점에 이유(note)가 없음")
    grades = final_grades(results, manual)
    baseline = _load_grades(_find(out_dir, args.baseline)) if args.baseline else None
    summary = summarize(results, grades)
    path.with_suffix(".md").write_text(report_markdown(results, grades, summary, baseline), encoding="utf-8")
    for r in results:
        r["grade"] = grades.get(r["item"]["key"])
    path.with_name(path.stem + ".graded.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    t = summary["total"]
    print(f"전체 {t['total']}: 맞음 {t['맞음']}, 틀림 {t['틀림']}, 확인 불가 {t['확인 불가']}, 모호 {t['답이 모호함']}, "
          f"검토 필요 {t[REVIEW]} → {path.with_suffix('.md')}")
    return 0


def _find(out_dir: Path, name: str) -> Path:
    p = Path(name)
    return p if p.exists() else out_dir / p


def _load_run(out_dir: Path, name: str) -> tuple[str, list[dict], dict]:
    """(이름, 결과, 최종 채점). 같은 이름의 .grades.json을 수동 채점으로 쓴다."""
    path = _find(out_dir, name)
    results = json.loads(path.read_text(encoding="utf-8"))
    gp = path.with_name(path.stem + ".grades.json")
    manual = _load_grades(gp) if gp.exists() else {}
    return path.stem, results, final_grades(results, manual)


def compare_markdown(runs: list[tuple[str, list[dict], dict]], baseline: tuple[str, list[dict], dict] | None) -> str:
    allruns = ([baseline] if baseline else []) + runs
    lines = ["# 기출 객관식 실행 비교", ""]
    if baseline:
        lines.append(f"- 기준선(수정 전): {baseline[0]}")
    lines += [f"- 비교 실행: {', '.join(r[0] for r in runs)}", ""]

    lines += ["## 과목별 정답률", ""]
    subjects = sorted({rec["item"]["subject"] for _, res, _ in allruns for rec in res})
    lines += ["| 실행 | " + " | ".join(subjects) + " | 전체 | **틀림** | 확인 불가 | 모호 | 검토 필요 |",
              "|---|" + "---|" * (len(subjects) + 5)]
    for name, res, grades in allruns:
        s = summarize(res, grades)
        cells = []
        for subj in subjects:
            b = s["by_subject"].get(subj)
            cells.append(f"{b['맞음']}/{b['total']}" if b else "-")
        t = s["total"]
        label = f"{name}(기준선)" if baseline and name == baseline[0] else name
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {t['맞음']}/{t['total']} ({t['맞음'] / t['total']:.0%}) | "
                     f"**{t['틀림']}** | {t['확인 불가']} | {t['답이 모호함']} | {t[REVIEW]} |")
    lines.append("")

    lines += ["## 문제별 비교", "", "칸: 고른 번호 판정. \"실행 간 바뀜\"은 비교 실행끼리(기준선 제외) 고른 번호나 판정이 다른 문제.", ""]
    lines += ["| 문제 ID | 정답 | " + " | ".join(r[0] for r in allruns) + " | 실행 간 바뀜 | 기준선 대비 |",
              "|---|---|" + "---|" * (len(allruns) + 2)]
    keys = [rec["item"]["key"] for rec in runs[0][1]]
    changed, vs_base = [], []
    for key in keys:
        cells, run_sig = [], []
        answer = ""
        for name, res, grades in allruns:
            rec = next((x for x in res if x["item"]["key"] == key), None)
            if rec is None:
                cells.append("-")
                continue
            c = compare_row(rec, grades.get(key) or {})
            answer = c["answer"]
            cells.append(f"{c['choice']} {c['verdict']}")
            if not (baseline and name == baseline[0]):
                run_sig.append((c["choice"], c["verdict"]))
        moved = len(set(run_sig)) > 1
        base_cell = cells[0] if baseline else ""
        base_diff = bool(baseline) and any(cell.split(" ", 1)[-1] != base_cell.split(" ", 1)[-1] for cell in cells[1:])
        if moved:
            changed.append(key)
        if base_diff:
            vs_base.append(key)
        lines.append(f"| {key} | {answer} | " + " | ".join(cells) + f" | {'바뀜' if moved else ''} | "
                     f"{'다름' if base_diff else ''} |")
    lines += ["", f"- 실행 간 바뀐 문제: {', '.join(changed) or '없음'}",
              f"- 기준선과 판정이 다른 문제: {', '.join(vs_base) or '없음'}" if baseline else "",
              "- 문제별 답변 전문: " + ", ".join(f"{name}.md" for name, _, _ in allruns) + " (같은 폴더)", ""]

    for name, res, grades in allruns:
        lines += [f"## {name}", "", *summary_table(summarize(res, grades)), "", *compare_table(res, grades), ""]
        notes = [(k, g) for k, g in grades.items() if g.get("source") == "수동" and g.get("note")]
        if notes and not (baseline and name == baseline[0]):
            lines += ["수동 채점 메모:", ""] + [f"- {k}: {g['verdict']} — {g['note']}" for k, g in notes] + [""]
    return "\n".join(lines)


def _compare(out_dir: Path, run_names: list[str], baseline_name: str | None) -> int:
    runs = [_load_run(out_dir, n) for n in run_names]
    baseline = _load_run(out_dir, baseline_name) if baseline_name else None
    stem = "compare-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / f"{stem}.md").write_text(compare_markdown(runs, baseline), encoding="utf-8")
    print(f"저장: {out_dir / stem}.md")
    return 0


def _load_grades(path: Path) -> dict:
    grades = json.loads(path.read_text(encoding="utf-8"))
    for k, g in grades.items():
        if g.get("verdict") not in VERDICTS:
            raise ValueError(f"{k}: verdict는 {VERDICTS} 중 하나")
        if g.get("cause") and g["cause"] not in CAUSES:
            raise ValueError(f"{k}: cause는 {CAUSES} 중 하나")
    return grades


if __name__ == "__main__":
    sys.exit(main())
