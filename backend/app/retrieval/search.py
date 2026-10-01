"""이론 청크 검색 (D-020). 검색 대상은 v_searchable_theory(needs_review=false, 임베딩 있음, embedding_enabled).

벡터 후보 → (RERANKER_MODEL이 있으면) 리랭커 → 상위 K개. "확인 불가" 판단(벡터 하한 + 리랭커 3구간)은 is_answerable.

    cd backend
    uv run python -m app.retrieval.search "DIKW 피라미드의 구성요소는?"
    uv run python -m app.retrieval.search "질문" --k 10
    uv run python -m app.retrieval.search "질문" --no-rerank
"""

import argparse
import sys
from typing import Literal

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.ingestion.embedding import get_embedder, to_pgvector


def search_theory(conn: psycopg.Connection, settings: Settings, query_vec: str, k: int) -> list[dict]:
    """cosine 거리(<=>) 순으로 k개. query_vec은 pgvector 텍스트(정규화된 질문 벡터)."""
    q = sql.SQL(
        "SELECT t.id, t.title, t.clean_text, t.embedding_text, t.exam_clues, p.printed_page_number, p.book_id, b.title AS book_title, "
        "  1 - (t.embedding <=> %s::public.vector) AS score "
        "FROM {s}.v_searchable_theory t "
        "JOIN {s}.pages p ON p.id = t.page_id JOIN {s}.books b ON b.id = p.book_id "
        "ORDER BY t.embedding <=> %s::public.vector LIMIT %s"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (query_vec, query_vec, k)).fetchall()


Zone = Literal["reject", "gray", "answer"]
ZONE_LABELS = {"reject": "확인 불가", "gray": "회색 구간(근거 확신 낮음)", "answer": "답변"}


def is_answerable(settings: Settings, vector_top: float | None, rerank_top: float | None) -> tuple[Zone, str]:
    """"확인 불가" 판단(ARCHITECTURE "확인 불가" 3구간). (구간, 이유).

    - reject: 바로 "자료에서 확인 불가"(LLM 호출 없음). 이유 no_result / vector_below_floor / rerank_below_floor
    - gray: 리랭커 1위가 하한~상한. 판정기 can_answer로 판단, 판정기가 없으면 답변 + "근거 확신 낮음". 이유 rerank_gray
    - answer: 그대로 답변. 이유 ok(리랭커 상한 이상) / no_reranker(리랭커 없이 1단계만 통과)
    """
    if vector_top is None:
        return "reject", "no_result"
    if vector_top < settings.answerable_min_vector_score:
        return "reject", "vector_below_floor"
    if rerank_top is None:
        return "answer", "no_reranker"
    if rerank_top < settings.answerable_min_rerank_score:
        return "reject", "rerank_below_floor"
    if rerank_top < settings.answerable_confident_rerank_score:
        return "gray", "rerank_gray"
    return "answer", "ok"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="이론 청크 검색 확인")
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=None, help="보여줄 개수(기본 SEARCH_TOP_K)")
    ap.add_argument("--no-rerank", action="store_true", help="RERANKER_MODEL이 있어도 벡터 순위만")
    args = ap.parse_args(argv)

    from app.db.connection import connect

    settings = get_settings()
    k = args.k or settings.search_top_k
    use_rerank = bool(settings.reranker_model) and not args.no_rerank
    vec = to_pgvector(get_embedder(settings).encode([args.query])[0])
    with connect(settings) as conn:
        rows = search_theory(conn, settings, vec, max(k, settings.search_candidates_n) if use_rerank else k)
    vector_top = float(rows[0]["score"]) if rows else None
    rerank_top = None
    if use_rerank and rows:
        from app.retrieval.rerank import get_reranker, rerank

        rows = rerank(args.query, rows, get_reranker(settings), settings.reranker_input)
        rerank_top = rows[0]["rerank_score"]
    rows = rows[:k]
    zone, reason = is_answerable(settings, vector_top, rerank_top)
    print(f"질문: {args.query}")
    print(f"리랭커: {settings.reranker_model if use_rerank else '없음'} / 판단: {ZONE_LABELS[zone]}({reason})")
    for i, r in enumerate(rows, 1):
        body = " ".join(r["clean_text"].split())[:120]
        extra = f" (벡터 {r['vector_rank']}위 {r['vector_score']:.3f})" if "vector_rank" in r else ""
        print(f"{i}. [{r['score']:.3f}]{extra} {r['book_title']} {r['printed_page_number']}쪽 · {r['title']}\n   {body}")
    if not rows:
        print("검색 결과 없음(임베딩된 청크가 없거나 모두 검수 대기)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
