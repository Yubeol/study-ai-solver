"""질의 흐름 (ARCHITECTURE "질의 흐름"): 검색 → "확인 불가" 3구간 → 답변 생성(Gemini JSON) → 인용 검증 → query_logs.

- 검색: 질문 임베딩 → 벡터 후보 N개 → 리랭커 → 상위 K개. 벡터 1위가 하한 미만이면 리랭크도 건너뛴다.
- 3구간(search.is_answerable): reject면 LLM 호출 없이 "자료에서 확인 불가".
  gray면 판정기 can_answer(질문 + 근거 K개). 확률 < JUDGE_CAN_ANSWER_MIN이면 LLM 호출 없이 확인 불가,
  그 이상이면 답변(JUDGE_CONFIDENT_MIN 미만이면 "근거 확신 낮음"). 판정기 오류나 JUDGE_PROVIDER=none이면
  판정 생략 → 답변하되 "근거 확신 낮음"(D-028).
- 객관식 일관성 검사(mcq_check): 보기별 판정과 고른 번호가 모순이면 답은 그대로 두고 "근거 확신 낮음".
- 검색 대상은 SEARCH_CORPUS(team_text / common_json / mixed, D-M-033). 근거 행은 search_candidates가 같은 모양으로 맞춘다.
- LLM 입력은 근거마다 과목(책 제목)·인쇄 쪽·제목 경로·clean_text(블록은 제목 경로를 뺀 블록 텍스트 — 표는 행,
  그림은 설명·구조·그림 속 글자). 응답의 근거 표시는 raw_text(교재 원문 그대로, 표·그림 원문 목록은 줄바꿈으로 이음).
- LLM이 unanswerable=true로 답하면 "자료에서 확인 불가"(3구간 뒤 한 겹 더).
- 인용 검증: cited와 본문의 [n] 중 넘긴 근거 번호(1..K) 밖인 것은 제거하고 metadata에 기록.
- 모델(임베딩·리랭커·LLM)은 서버 시작 시 load_qa_models로 미리 올린다(지연 로딩 안 함).
- 근거가 정해진 뒤 후처리로 이론 블록 근거에 연결된 그림·표 이미지(related_visuals)를 붙인다(D-JW-008, LLM 입력에는 안 넣음).
- 사용자 보충(D-M-035): search_candidates가 검색 대상과 상관없이 보충도 후보로 합친다. 보충 근거는 kind·corpus가
  supplement, 쪽 번호 없음(LLM 입력에는 "-"), clean_text·raw_text = 사용자가 입력한 본문.
"""

import logging
import re
import time
from dataclasses import dataclass

import psycopg

from app.core.config import Settings
from app.ingestion.common_json import CORPUS as COMMON_JSON
from app.ingestion.embedding import LocalEmbedder, get_embedder, to_pgvector
from app.judge import Judge, JudgeResult, get_judge
from app.llm.gemini import GeminiClient, GeminiError
from app.prompts import load_json, load_text, render
from app.qa.mcq_check import check_mcq
from app.qa.related_visuals import add_related_visuals
from app.repositories.query_logs import insert_query_log
from app.retrieval.rerank import LocalReranker, get_reranker, rerank
from app.retrieval.search import SUPPLEMENT, TEAM_TEXT, candidate_sources, is_answerable, search_candidates

log = logging.getLogger(__name__)

UNANSWERABLE_TEXT = "자료에서 확인 불가"
LLM_ERROR_TEXT = "답변 생성 실패(잠시 후 다시 시도)"
_INLINE_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")  # [1], [1, 2]
# 문장 경계: 마침표·물음표·느낌표 뒤 공백(바로 뒤가 인용 "[n]"이면 같은 문장으로 본다) 또는 줄바꿈
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?!\[)|\n+")
CITATION_REQUIRED_FIELDS = ("explanation", "confusions")  # 모든 문장에 [n] 인용이 있어야 하는 필드
# 객관식 풀이(프롬프트 규칙 8)에서 근거가 없는 보기 줄: "③은 근거에서 확인되지 않는다." — 인용 없는 게 맞는 문장
_UNSUPPORTED_OPTION = re.compile(
    r"^\s*(?:[①②③④]|\(?\s*[1-4]\s*\)?\s*번?)\s*(?:은|는)\s*\[?근거\]?에서\s*확인되지\s*않는다")


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
    """근거 목록. 앞의 필드는 기존 그대로, 뒤의 필드는 검색 대상 전환(D-M-033)에서 추가만 했다.

    chunk_id는 corpus가 team_text면 theory_chunks.id, common_json이면 blocks.id.
    """
    return [
        {
            "n": i,
            "chunk_id": str(r["id"]),
            "book_title": r["book_title"],
            "page": r["printed_page_number"],
            "path": r.get("path") or heading_path(r),
            "clean_text": r["clean_text"],
            "raw_text": r["raw_text"],
            "vector_score": _round(r.get("vector_score", r["score"])),
            "rerank_score": _round(r.get("rerank_score")),
            "corpus": r["corpus"],
            "kind": r["kind"],
            "block_id": r["block_id"],
            "title": r["title"],
            "title_path": r["title_path"],
            "document_title": r["document_title"],
            "thumbnail_url": r["thumbnail_url"],
            "image_url": r["image_url"],
        }
        for i, r in enumerate(rows, 1)
    ]


def evidence_prompt(evidence: list[dict]) -> str:
    return "\n".join(
        render("answer_evidence_item.txt", n=e["n"], book=e["book_title"], page=e["page"] or "-", path=e["path"] or "-",
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
        "unsupported_option_sentences": count_unsupported_options(data.get("explanation") or ""),
    }


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if re.search(r"[가-힣A-Za-z]", s)]


def count_uncited_sentences(text: str) -> int:
    """[n] 인용이 하나도 없는 문장 수. 글자가 없는 조각(목록 기호 등)과
    객관식의 "③은 근거에서 확인되지 않는다." 줄(인용이 없는 게 맞음)은 세지 않는다."""
    return sum(1 for s in _sentences(text) if not _INLINE_CITE.search(s) and not _UNSUPPORTED_OPTION.match(s))


def count_unsupported_options(text: str) -> int:
    """객관식 풀이에서 "근거에서 확인되지 않는다"고 쓴 보기 줄 수."""
    return sum(1 for s in _sentences(text) if _UNSUPPORTED_OPTION.match(s))


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
    rows = search_candidates(conn, settings, vec, n)
    timings["vector_ms"] = _ms(t)
    sources = candidate_sources(rows)  # 리랭크 전 후보 n개의 출처(mixed 확인용)
    vector_top = float(rows[0]["score"]) if rows else None
    rerank_top = None
    if models.reranker and rows and vector_top >= settings.answerable_min_vector_score:
        t = time.perf_counter()
        rows = rerank(question, rows, models.reranker, settings.reranker_input)
        timings["rerank_ms"] = _ms(t)
        rerank_top = rows[0]["rerank_score"]
    rows = rows[:k]
    evidence = build_evidence(rows)

    # 2. "확인 불가" 3구간. 회색 구간이면 판정기 can_answer(질문 + 근거 K개, D-028)
    zone, reason = is_answerable(settings, vector_top, rerank_top)
    judge_info = None
    if zone == "gray" and models.judge is not None:
        t = time.perf_counter()
        jr = models.judge.can_answer(question, evidence)
        timings["judge_ms"] = _ms(t)
        judge_info = judge_record(settings, models.judge.name, jr, timings["judge_ms"], len(evidence))

    result = {
        "question": question,
        "corpus": settings.search_corpus,
        "candidate_sources": sources,
        "zone": zone,
        "zone_reason": reason,
        "scores": {"vector_top": _round(vector_top), "rerank_top": _round(rerank_top)},
        "judge": judge_info,
        "answer": UNANSWERABLE_TEXT,
        "explanation": "",
        "confusions": "",
        "low_confidence": False,
        "low_confidence_reasons": [],
        "mcq_check": None,
        "llm": None,
    }
    if zone == "reject" or (judge_info and judge_info["can_answer"] is False):
        result |= {"status": "unanswerable", "confidence": "unanswerable"}
    elif models.llm is None:
        result |= {"status": "error", "confidence": None, "answer": LLM_ERROR_TEXT, "error": "llm_not_configured"}
    else:
        # 3. 답변 생성
        t = time.perf_counter()
        result |= _generate(settings, models.llm, question, evidence)
        timings["llm_ms"] = _ms(t)
        if result["status"] == "answered":
            result["mcq_check"] = check_mcq(question, result["answer"], result["explanation"])
            reasons = low_confidence_reasons(zone, judge_info, result["cited"], result["mcq_check"])
            low = bool(reasons)
            result |= {"low_confidence": low, "low_confidence_reasons": reasons, "confidence": "low" if low else "high"}

    cited = set(result.get("cited") or [])
    for e in evidence:
        e["cited"] = e["n"] in cited
    # 4. 연결 그림·표(D-JW-008): 근거 K개를 한 번에 조회해 후처리로만 붙인다(실패해도 답변은 그대로)
    t = time.perf_counter()
    add_related_visuals(conn, settings, evidence)
    timings["visuals_ms"] = _ms(t)
    result["evidence"] = [{k2: v for k2, v in e.items() if k2 != "clean_text"} for e in evidence]
    result["citations"] = [e for e in result["evidence"] if e["cited"]]
    timings["total_ms"] = _ms(t_start)
    result["timings_ms"] = timings
    result["query_log_id"] = _log(conn, settings, result)
    return result


def judge_record(settings: Settings, provider: str, jr: JudgeResult, latency_ms: int, n_evidence: int) -> dict:
    """판정 결과 기록(query_logs.metadata.judge). 확률값은 재적재 후 임계값 재조정에 쓰므로 오류가 아니면 항상 남긴다.

    can_answer: 확률 ≥ JUDGE_CAN_ANSWER_MIN이면 True, 미만이면 False, 오류면 None(none과 같은 동작).
    confident: 확률 ≥ JUDGE_CONFIDENT_MIN이면 "근거 확신 낮음" 해제.
    """
    p = jr.probability
    return {
        "provider": provider,
        "question_key": "can_answer",
        "input": {"question": True, "evidence_n": n_evidence},
        "model": jr.model,
        "probability": p,
        "can_answer": None if p is None else p >= settings.judge_can_answer_min,
        "confident": p is not None and p >= settings.judge_confident_min,
        "thresholds": {"can_answer_min": settings.judge_can_answer_min,
                       "confident_min": settings.judge_confident_min},
        "latency_ms": latency_ms,
        "usage": jr.usage,
        "attempts": jr.attempts,
        "error": jr.error,
    }


def low_confidence_reasons(zone: str, judge_info: dict | None, cited: list[int], mcq: dict | None) -> list[str]:
    """답변했지만 "근거 확신 낮음"을 붙이는 이유들(비면 확신 높음)."""
    reasons = []
    if zone == "gray":
        if judge_info is None:
            reasons.append("gray_no_judge")
        elif judge_info["error"]:
            reasons.append("gray_judge_error")
        elif not judge_info["confident"]:
            reasons.append("gray_judge_not_confident")
    if not cited:
        reasons.append("no_valid_citation")
    if mcq is not None and not mcq["consistent"]:
        reasons.append("mcq_inconsistent")
    return reasons


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
    """query_logs 1행. 기록 실패는 답변을 막지 않는다(경고만).

    retrieved_theory_ids(팀 규격 컬럼)에는 theory_chunks id만 넣는다. 블록 근거는 metadata.retrieved_block_ids와
    evidence[].block_id에(D-M-033), 사용자 보충 근거는 metadata.retrieved_supplement_ids에 둔다(D-M-035).
    """
    llm = r.get("llm") or {}
    answer = "\n\n".join(x for x in (r["answer"], r.get("explanation"), r.get("confusions")) if x)
    metadata = {
        "flow": "qa_v1",
        "corpus": r["corpus"],
        "candidate_sources": r["candidate_sources"],
        "retrieved_block_ids": [e["block_id"] for e in r["evidence"] if e["corpus"] == COMMON_JSON],
        "retrieved_supplement_ids": [e["chunk_id"] for e in r["evidence"] if e["corpus"] == SUPPLEMENT],
        "status": r["status"],
        "zone": r["zone"],
        "zone_reason": r["zone_reason"],
        "scores": r["scores"],
        "confidence": r.get("confidence"),
        "low_confidence": r["low_confidence"],
        "low_confidence_reasons": r["low_confidence_reasons"],
        "llm_unanswerable": r.get("llm_unanswerable"),
        "judge": r["judge"],
        "mcq_check": r["mcq_check"],
        "judge_provider": settings.judge_provider,
        "timings_ms": r["timings_ms"],
        "evidence": [
            {"n": e["n"], "chunk_id": e["chunk_id"], "page": e["page"], "vector_score": e["vector_score"],
             "rerank_score": e["rerank_score"], "cited": e["cited"], "corpus": e["corpus"], "kind": e["kind"],
             "block_id": e["block_id"], "title": e["title"],
             "related_visual_ids": [v["block_id"] for v in e.get("related_visuals") or []]}
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
            retrieved_theory_ids=[e["chunk_id"] for e in r["evidence"] if e["corpus"] == TEAM_TEXT],
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
