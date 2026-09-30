"""검색 평가: 질문 세트로 hit@K와 "확인 불가" 임계값 후보를 잰다 (ARCHITECTURE "검색 평가").

    cd backend
    uv run python -m app.retrieval.evaluate                                   # 기본 질문 세트(EVAL_QUESTIONS_PATH)
    uv run python -m app.retrieval.evaluate --questions ../data/eval/x.csv --k 5
    uv run python -m app.retrieval.evaluate --check                           # 질문 파일 형식만 검사(DB·모델 안 씀)

- 질문 파일: UTF-8 CSV(BOM 허용), 머리행 `id,question,subject,pages,note`.
  subject는 page_map key(subject1~3), pages는 인쇄 쪽번호(`18|19`). pages가 비면 "자료에 없는 질문".
- 적중: 상위 K개 중 정답 과목 book의 정답 쪽 청크가 있으면 적중. 정답 순위는 EVAL_RANK_DEPTH까지 찾는다.
- 임계값: 1위 점수(cosine 유사도) ≥ t 이면 "답변 시도"(통과), 미만이면 "확인 불가"(차단).
  답할 수 있는 질문은 통과 비율, 자료에 없는 질문은 차단 비율을 본다.
- 결과: {REPORTS_DIR}/eval/{시각}.json(질문별 상위 결과 전체), .txt(요약). DB는 읽기만 한다.
"""

import argparse
import csv
import io
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.core.config import Settings, get_settings

HEADER = ["id", "question", "subject", "pages", "note"]
HIT_AT = (1, 3)  # K와 함께 보고할 고정 순위


@dataclass
class Question:
    id: str
    question: str
    subject: str  # page_map key, 자료에 없는 질문이면 ""
    pages: list[str]  # 인쇄 쪽번호(문자열, pages.printed_page_number와 같은 형식)
    note: str = ""

    @property
    def answerable(self) -> bool:
        return bool(self.pages)


@dataclass
class Result:
    question: Question
    rank: int | None  # 첫 정답 청크 순위(1부터), 깊이 안에 없으면 None. 자료에 없는 질문도 None
    top_score: float | None  # 1위 점수, 검색 결과가 없으면 None
    top: list[dict] = field(default_factory=list)  # 상위 결과(리포트용)


def parse_questions(text: str, subject_keys: set[str]) -> list[Question]:
    """CSV 본문을 검사해 질문 목록으로 바꾼다. 문제가 있으면 줄 번호를 모아 ValueError."""
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows or [h.strip() for h in rows[0]] != HEADER:
        raise ValueError(f"머리행은 {','.join(HEADER)} 이어야 합니다. 받은 값: {rows[0] if rows else '(빈 파일)'}")
    errors, out, seen = [], [], set()
    for lineno, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue  # 빈 줄
        if len(row) != len(HEADER):
            errors.append(f"{lineno}줄: 칸 수 {len(row)}개(5개여야 함, 질문에 쉼표가 있으면 큰따옴표로 감싸기)")
            continue
        qid, question, subject, pages, note = (c.strip() for c in row)
        pages_list = [p.strip() for p in pages.split("|") if p.strip()] if pages else []
        if not qid:
            errors.append(f"{lineno}줄: id가 비어 있음")
        elif qid in seen:
            errors.append(f"{lineno}줄: id 중복 {qid!r}")
        seen.add(qid)
        if not question:
            errors.append(f"{lineno}줄: question이 비어 있음")
        if subject and subject not in subject_keys:
            errors.append(f"{lineno}줄: subject {subject!r}는 page_map에 없음({', '.join(sorted(subject_keys))})")
        if pages_list and not subject:
            errors.append(f"{lineno}줄: pages가 있으면 subject도 필요")
        out.append(Question(qid, question, subject, pages_list, note))
    if errors:
        raise ValueError("질문 파일 오류:\n  " + "\n  ".join(errors))
    if not out:
        raise ValueError("질문이 하나도 없습니다.")
    return out


def find_rank(q: Question, rows: list[dict], book_ids: dict[str, UUID]) -> int | None:
    """검색 결과(점수 내림차순)에서 첫 정답 청크 순위."""
    if not q.answerable:
        return None
    gold_book, gold_pages = book_ids.get(q.subject), set(q.pages)
    for i, r in enumerate(rows, 1):
        if r["book_id"] == gold_book and str(r["printed_page_number"]) in gold_pages:
            return i
    return None


def summarize(results: list[Result], k: int, thresholds: list[float]) -> dict:
    """hit@1/3/K(전체·과목별), 정답 순위, 임계값별 통과·차단 비율."""
    answerable = [r for r in results if r.question.answerable]
    unanswerable = [r for r in results if not r.question.answerable]
    ks = sorted({*HIT_AT, k})

    def hits(rs: list[Result]) -> dict:
        n = len(rs)
        d = {"n": n}
        for kk in ks:
            h = sum(1 for r in rs if r.rank is not None and r.rank <= kk)
            d[f"hit@{kk}"] = _ratio(h, n)
        d["mrr"] = round(sum(1 / r.rank for r in rs if r.rank) / n, 3) if n else None
        return d

    by_subject = {}
    for subj in sorted({r.question.subject for r in answerable}):
        by_subject[subj] = hits([r for r in answerable if r.question.subject == subj])

    def scores(rs: list[Result]) -> list[float]:
        return [r.top_score for r in rs if r.top_score is not None]

    thr = []
    for t in thresholds:
        passed = sum(1 for r in answerable if r.top_score is not None and r.top_score >= t)
        # 통과했고 K 안에 정답도 있는 비율(실제로 제대로 답할 수 있는 비율)
        passed_hit = sum(
            1 for r in answerable if r.top_score is not None and r.top_score >= t and r.rank and r.rank <= k
        )
        blocked = sum(1 for r in unanswerable if r.top_score is None or r.top_score < t)
        thr.append(
            {
                "threshold": t,
                "answerable_pass": _ratio(passed, len(answerable)),
                "answerable_pass_and_hit": _ratio(passed_hit, len(answerable)),
                "unanswerable_block": _ratio(blocked, len(unanswerable)),
            }
        )
    return {
        "k": k,
        "overall": hits(answerable),
        "by_subject": by_subject,
        "missed": [r.question.id for r in answerable if not (r.rank and r.rank <= k)],
        "top_score": {
            "answerable": _range(scores(answerable)),
            "unanswerable": _range(scores(unanswerable)),
            "unanswerable_n": len(unanswerable),
        },
        "thresholds": thr,
    }


def _ratio(a: int, n: int) -> dict:
    return {"count": a, "of": n, "rate": round(a / n, 3) if n else None}


def _range(xs: list[float]) -> dict | None:
    if not xs:
        return None
    s = sorted(xs)
    return {"min": round(s[0], 3), "median": round(s[len(s) // 2], 3), "max": round(s[-1], 3)}


def format_summary(summary: dict, config: dict) -> str:
    lines = [f"설정: {json.dumps(config, ensure_ascii=False)}"]

    def fmt(d: dict) -> str:
        parts = [f"n={d['n']}"]
        for key, v in d.items():
            if key.startswith("hit@"):
                parts.append(f"{key} {v['count']}/{v['of']}" + (f"({v['rate']:.0%})" if v["rate"] is not None else ""))
        parts.append(f"MRR {d['mrr']}")
        return "  ".join(parts)

    lines.append("전체(답할 수 있는 질문): " + fmt(summary["overall"]))
    for subj, d in summary["by_subject"].items():
        lines.append(f"  {subj}: " + fmt(d))
    lines.append(f"K={summary['k']} 안에 정답 없음: {', '.join(summary['missed']) or '없음'}")
    ts = summary["top_score"]
    lines.append(f"1위 점수 — 답할 수 있는 질문: {ts['answerable']} / 자료에 없는 질문({ts['unanswerable_n']}개): {ts['unanswerable']}")
    lines.append("임계값  통과(답가능)  통과+적중  차단(자료없음)")
    for t in summary["thresholds"]:
        a, ah, u = t["answerable_pass"], t["answerable_pass_and_hit"], t["unanswerable_block"]
        lines.append(f"{t['threshold']:.2f}    {_cell(a)}  {_cell(ah)}  {_cell(u)}")
    return "\n".join(lines)


def _cell(v: dict) -> str:
    return f"{v['count']}/{v['of']}" + (f"({v['rate']:.0%})" if v["rate"] is not None else "") if v["of"] else "-"


# ---------- 실행 ----------


def _subject_book_ids(conn, settings: Settings) -> dict[str, UUID]:
    from app.ingestion.team_import import load_map
    from app.repositories import books as books_repo

    out = {}
    for c in load_map(settings)["books"]:
        ids = books_repo.find_book_ids(conn, settings, subject=c["subject"], title=c["title"], source_name=c["source_name"])
        if ids:
            out[c["key"]] = ids[0]
    return out


def run(settings: Settings, questions: list[Question], k: int, depth: int) -> tuple[list[Result], dict[str, UUID]]:
    from app.db.connection import connect
    from app.ingestion.embedding import get_embedder, to_pgvector
    from app.retrieval.search import search_theory

    vecs = get_embedder(settings).encode([q.question for q in questions])
    results = []
    with connect(settings) as conn:
        book_ids = _subject_book_ids(conn, settings)
        if missing := {q.subject for q in questions if q.subject} - set(book_ids):
            raise SystemExit(f"DB에 반입되지 않은 과목: {sorted(missing)}")
        for q, v in zip(questions, vecs, strict=True):
            rows = search_theory(conn, settings, to_pgvector(v), max(k, depth))
            results.append(
                Result(
                    question=q,
                    rank=find_rank(q, rows, book_ids),
                    top_score=float(rows[0]["score"]) if rows else None,
                    top=[
                        {
                            "rank": i,
                            "score": round(float(r["score"]), 4),
                            "subject": next((key for key, b in book_ids.items() if b == r["book_id"]), None),
                            "page": r["printed_page_number"],
                            "title": r["title"],
                            "chunk_id": str(r["id"]),
                        }
                        for i, r in enumerate(rows, 1)
                    ],
                )
            )
    return results, book_ids


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    ap = argparse.ArgumentParser(description="검색 평가(hit@K, 확인 불가 임계값)")
    ap.add_argument("--questions", type=Path, default=settings.eval_questions_file, help="질문 CSV 경로")
    ap.add_argument("--k", type=int, default=settings.search_top_k, help="hit@K의 K(기본 SEARCH_TOP_K)")
    ap.add_argument("--check", action="store_true", help="질문 파일 형식만 검사")
    args = ap.parse_args(argv)

    from app.ingestion.team_import import load_map

    subject_keys = {c["key"] for c in load_map(settings)["books"]}
    try:
        questions = parse_questions(args.questions.read_text(encoding="utf-8"), subject_keys)
    except FileNotFoundError:
        print(f"질문 파일 없음: {args.questions}")
        return 1
    except ValueError as e:
        print(e)
        return 1
    n_ans = sum(q.answerable for q in questions)
    print(f"질문 {len(questions)}개(답할 수 있는 질문 {n_ans}, 자료에 없는 질문 {len(questions) - n_ans}): {args.questions}")
    if args.check:
        return 0

    depth = max(args.k, settings.eval_rank_depth)
    results, _ = run(settings, questions, args.k, depth)
    summary = summarize(results, args.k, settings.eval_threshold_list)
    config = {
        "embedding_model": settings.embedding_model,
        "reranker": None,
        "keyword_search": None,
        "k": args.k,
        "rank_depth": depth,
        "questions": str(args.questions),
    }
    text = format_summary(summary, config)
    print(text)

    out_dir = settings.reports_path / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    detail = [
        {**asdict(r.question), "rank": r.rank, "top_score": r.top_score, "top": r.top} for r in results
    ]
    (out_dir / f"{stamp}.json").write_text(
        json.dumps({"config": config, "summary": summary, "questions": detail}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out_dir / f"{stamp}.txt").write_text(text + "\n", encoding="utf-8")
    print(f"리포트: {out_dir / stamp}.json / .txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
