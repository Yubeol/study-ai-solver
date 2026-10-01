"""질의 흐름 (ARCHITECTURE "질의 흐름"): 검색 → "확인 불가" 3구간 → 답변 생성(Gemini JSON) → 인용 검증 → query_logs.

- 검색: 질문 임베딩 → 벡터 후보 N개 → 리랭커 → 상위 K개. 벡터 1위가 하한 미만이면 리랭크도 건너뛴다.
- 3구간(search.is_answerable): reject면 LLM 호출 없이 "자료에서 확인 불가".
  gray면 판정기 can_answer(JUDGE_PROVIDER=none이면 판정 생략 → 답변하되 "근거 확신 낮음").
- LLM 입력은 근거마다 과목(책 제목)·인쇄 쪽·제목 경로·clean_text. 응답의 근거 표시는 raw_text(교재 원문 그대로).
- LLM이 unanswerable=true로 답하면 "자료에서 확인 불가"(3구간 뒤 한 겹 더).
- 인용 검증: cited와 본문의 [n] 중 넘긴 근거 번호(1..K) 밖인 것은 제거하고 metadata에 기록.
- 모델(임베딩·리랭커·LLM)은 서버 시작 시 load_qa_models로 미리 올린다(지연 로딩 안 함).
"""

import logging
import re
import time
from dataclasses import dataclass

import psycopg

from app.core.config import Settings
from app.ingestion.embedding import LocalEmbedder, get_embedder, to_pgvector
from app.judge import Judge, get_judge
from app.llm.gemini import GeminiClient, GeminiError
from app.prompts import load_json, load_text, render
from app.repositories.query_logs import insert_query_log
from app.retrieval.rerank import LocalReranker, get_reranker, rerank
from app.retrieval.search import is_answerable, search_theory

log = logging.getLogger(__name__)

UNANSWERABLE_TEXT = "자료에서 확인 불가"
LLM_ERROR_TEXT = "답변 생성 실패(잠시 후 다시 시도)"
_INLINE_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")  # [1], [1, 2]
# 문장 경계: 마침표·물음표·느낌표 뒤 공백(바로 뒤가 인용 "[n]"이면 같은 문장으로 본다) 또는 줄바꿈
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?!\[)|\n+")
CITATION_REQUIRED_FIELDS = ("explanation", "confusions")  # 모든 문장에 [n] 인용이 있어야 하는 필드


@dataclass
class QaModels:
    embedder: LocalEmbedder
    reranker: LocalReranker | None  # RERANKER_MODEL이 비면 None(벡터 순위만)
    llm: GeminiClient | None  # GEMINI_API_KEY가 비면 None(검색·판정까지만)
    judge: Judge | None  # JUDGE_PROVIDER=none이면 None


def load_qa_models(settings: Settings) -> QaModels:
    """임베딩·리랭커를 로드하고 한 번씩 돌려 둔다(첫 호출의 가중치 로딩 지연을 시작 시점으로 옮김)."""
    embedder = get_embedder(settings)
    embedder.encode(["워밍업"])
    reranker = None
    if settings.reranker_model:
        reranker = get_reranker(settings)
        reranker.score("워밍업", ["워밍업"])
    llm = GeminiClient(settings) if settings.gemini_api_key.get_secret_value() else None
    return QaModels(embedder=embedder, reranker=reranker, llm=llm, judge=get_judge(settings))


def heading_path(row: dict) -> str:
    """embedding_text = "제목 경로\\n\\nclean_text"(D-019). 경로가 없으면 청크 제목."""
    emb, clean = row.get("embedding_text") or "", row.get("clean_text") or ""
    if clean and emb.endswith(clean) and len(emb) > len(clean):
        return emb[: -len(clean)].strip()
    return row.get("title") or ""


def build_evidence(rows: list[dict]) -> list[dict]:
    return [
        {
            "n": i,
            "chunk_id": str(r["id"]),
            "book_title": r["book_title"],
            "page": r["printed_page_number"],
            "path": heading_path(r),
            "clean_text": r["clean_text"],
            "raw_text": r["raw_text"],
            "vector_score": _round(r.get("vector_score", r["score"])),
            "rerank_score": _round(r.get("rerank_score")),
        }
        for i, r in enumerate(rows, 1)
    ]


def evidence_prompt(evidence: list[dict]) -> str:
    return "\n".join(
        render("answer_evidence_item.txt", n=e["n"], book=e["book_title"], page=e["page"], path=e["path"] or "-",
               text=e["clean_text"].strip())
        for e in evidence
    )


def validate_citations(data: dict, n_evidence: int) -> tuple[list[int], dict]:
    """(유효한 cited, 기록). 범위 밖 번호는 cited와 본문 [n]에서 지운다(data를 고침).

    기록: invalid_cited, invalid_inline, inline_not_in_cited, uncited_sentences(필드별 인용 없는 문장 수),
    uncited_sentence_count(explanation·confusions 합계).
    """
    valid_range = range(1, n_evidence + 1)
    cited, invalid = [], []
    for c in data.get("cited") or []:
        if isinstance(c, int) and not isinstance(c, bool) and c in valid_range:
            if c not in cited:
                cited.append(c)
        else:
            invalid.append(c)
    inline_invalid = []

    def strip(m: re.Match) -> str:
        nums = [int(x) for x in m.group(1).split(",")]
        keep = [x for x in nums if x in valid_range]
        inline_invalid.extend(x for x in nums if x not in valid_range)
        if len(keep) == len(nums):
            return m.group(0)
        return f"[{', '.join(map(str, keep))}]" if keep else ""

    for key in ("answer", "explanation", "confusions"):
        if isinstance(data.get(key), str):
            data[key] = _INLINE_CITE.sub(strip, data[key])
    # 본문에서 인용했는데 cited에 빠진 유효 번호는 기록만 한다(cited는 LLM이 낸 목록 기준).
    inline_valid = {int(x) for k in ("answer", "explanation", "confusions")
                    for g in _INLINE_CITE.findall(data.get(k) or "") for x in g.split(",")}
    uncited = {k: count_uncited_sentences(data.get(k) or "") for k in CITATION_REQUIRED_FIELDS}
    return cited, {
        "invalid_cited": invalid,
        "invalid_inline": inline_invalid,
        "inline_not_in_cited": sorted(inline_valid - set(cited)),
        "uncited_sentences": uncited,
        "uncited_sentence_count": sum(uncited.values()),
    }


def count_uncited_sentences(text: str) -> int:
    """[n] 인용이 하나도 없는 문장 수. 글자가 없는 조각(목록 기호 등)은 세지 않는다."""
    return sum(1 for s in _SENTENCE_SPLIT.split(text)
               if re.search(r"[가-힣A-Za-z]", s) and not _INLINE_CITE.search(s))


def answer_question(conn: psycopg.Connection, settings: Settings, models: QaModels, question: str,
                    k: int | None = None) -> dict:
    k = k or settings.search_top_k
    timings: dict[str, int] = {}
    t_start = time.perf_counter()

    # 1. 검색
    t = time.perf_counter()
    vec = to_pgvector(models.embedder.encode([question])[0])
    timings["embed_ms"] = _ms(t)
    t = time.perf_counter()
    n = max(k, settings.search_candidates_n) if models.reranker else k
    rows = search_theory(conn, settings, vec, n)
    timings["vector_ms"] = _ms(t)
    vector_top = float(rows[0]["score"]) if rows else None
    rerank_top = None
    if models.reranker and rows and vector_top >= settings.answerable_min_vector_score:
        t = time.perf_counter()
        rows = rerank(question, rows, models.reranker, settings.reranker_input)
        timings["rerank_ms"] = _ms(t)
        rerank_top = rows[0]["rerank_score"]
    rows = rows[:k]
    evidence = build_evidence(rows)

    # 2. "확인 불가" 3구간
    zone, reason = is_answerable(settings, vector_top, rerank_top)
    judge_info = None
    if zone == "gray" and models.judge is not None:
        t = time.perf_counter()
        ok, conf = models.judge.can_answer(question, [e["clean_text"] for e in evidence])
        timings["judge_ms"] = _ms(t)
        judge_info = {"provider": models.judge.name, "can_answer": ok, "confidence": conf}

    result = {
        "question": question,
        "zone": zone,
        "zone_reason": reason,
        "scores": {"vector_top": _round(vector_top), "rerank_top": _round(rerank_top)},
        "judge": judge_info,
        "answer": UNANSWERABLE_TEXT,
        "explanation": "",
        "confusions": "",
        "low_confidence": False,
        "llm": None,
    }
    if zone == "reject" or (judge_info and not judge_info["can_answer"]):
        result |= {"status": "unanswerable", "confidence": "unanswerable"}
    elif models.llm is None:
        result |= {"status": "error", "confidence": None, "answer": LLM_ERROR_TEXT, "error": "llm_not_configured"}
    else:
        # 3. 답변 생성
        t = time.perf_counter()
        result |= _generate(settings, models.llm, question, evidence)
        timings["llm_ms"] = _ms(t)
        if result["status"] == "answered":
            # 판정기 없이 회색 구간이면 확신 낮음. 유효 인용이 하나도 없어도 확신 낮음.
            low = (zone == "gray" and judge_info is None) or not result["cited"]
            result |= {"low_confidence": low, "confidence": "low" if low else "high"}

    cited = set(result.get("cited") or [])
    for e in evidence:
        e["cited"] = e["n"] in cited
    result["evidence"] = [{k2: v for k2, v in e.items() if k2 != "clean_text"} for e in evidence]
    result["citations"] = [e for e in result["evidence"] if e["cited"]]
    timings["total_ms"] = _ms(t_start)
    result["timings_ms"] = timings
    result["query_log_id"] = _log(conn, settings, result)
    return result


def _generate(settings: Settings, llm: GeminiClient, question: str, evidence: list[dict]) -> dict:
    try:
        r = llm.generate_json(
            llm.models_for(settings.answer_model),
            system=load_text("answer_system.txt"),
            user=render("answer_user.txt", evidence=evidence_prompt(evidence), question=question),
            schema=load_json("answer_schema.json"),
            temperature=settings.answer_temperature,
        )
    except GeminiError as e:
        return {"status": "error", "confidence": None, "answer": LLM_ERROR_TEXT, "error": "llm_failed",
                "llm": {"failed_attempts": e.attempts}}
    data = dict(r.data)
    cited, check = validate_citations(data, len(evidence))
    llm_info = {"model": r.model, "usage": r.usage, "failed_attempts": r.attempts, "citation_check": check}
    if data.get("unanswerable") is True:
        return {"status": "unanswerable", "confidence": "unanswerable", "answer": UNANSWERABLE_TEXT,
                "explanation": str(data.get("explanation") or ""), "confusions": "", "cited": [],
                "llm_unanswerable": True, "llm": llm_info}
    return {"status": "answered", "answer": str(data.get("answer") or ""),
            "explanation": str(data.get("explanation") or ""), "confusions": str(data.get("confusions") or ""),
            "cited": cited, "llm_unanswerable": False, "llm": llm_info}


def _log(conn: psycopg.Connection, settings: Settings, r: dict) -> str | None:
    """query_logs 1행. 기록 실패는 답변을 막지 않는다(경고만)."""
    llm = r.get("llm") or {}
    answer = "\n\n".join(x for x in (r["answer"], r.get("explanation"), r.get("confusions")) if x)
    metadata = {
        "flow": "qa_v1",
        "status": r["status"],
        "zone": r["zone"],
        "zone_reason": r["zone_reason"],
        "scores": r["scores"],
        "confidence": r.get("confidence"),
        "low_confidence": r["low_confidence"],
        "llm_unanswerable": r.get("llm_unanswerable"),
        "judge": r["judge"],
        "judge_provider": settings.judge_provider,
        "timings_ms": r["timings_ms"],
        "evidence": [
            {"n": e["n"], "chunk_id": e["chunk_id"], "page": e["page"], "vector_score": e["vector_score"],
             "rerank_score": e["rerank_score"], "cited": e["cited"]}
            for e in r["evidence"]
        ],
        "cited": r.get("cited") or [],
        "citation_check": llm.get("citation_check"),
        "model": llm.get("model"),
        "failed_attempts": llm.get("failed_attempts"),
        "error": r.get("error"),
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model or None,
    }
    try:
        qid = insert_query_log(
            conn, settings,
            question_text=r["question"],
            retrieved_theory_ids=[e["chunk_id"] for e in r["evidence"]],
            answer=answer,
            latency_ms=r["timings_ms"]["total_ms"],
            token_usage=llm.get("usage"),
            metadata=metadata,
        )
        return str(qid)
    except psycopg.Error as e:
        log.warning("query_logs 기록 실패: %s", type(e).__name__)
        return None


def _ms(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


def _round(x: float | None) -> float | None:
    return None if x is None else round(float(x), 4)
