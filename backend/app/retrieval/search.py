"""이론 청크 검색 (D-020). 검색 대상은 v_searchable_theory(needs_review=false, 임베딩 있음, embedding_enabled).

벡터 후보 → (RERANKER_MODEL이 있으면) 리랭커 → 상위 K개. "확인 불가" 2단계 판단은 is_answerable.

    cd backend
    uv run python -m app.retrieval.search "DIKW 피라미드의 구성요소는?"
    uv run python -m app.retrieval.search "질문" --k 10
    uv run python -m app.retrieval.search "질문" --no-rerank
"""

import argparse
import sys

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


def is_answerable(settings: Settings, vector_top: float | None, rerank_top: float | None) -> tuple[bool, str]:
    """"확인 불가" 2단계 판단(ARCHITECTURE). (답변 시도 여부, 이유)."""
    if vector_top is None:
        return False, "no_result"
    if vector_top < settings.answerable_min_vector_score:
        return False, "vector_below_floor"
    if rerank_top is not None and rerank_top < settings.answerable_min_rerank_score:
        return False, "rerank_below_threshold"
    return True, "ok"


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
    ok, reason = is_answerable(settings, vector_top, rerank_top)
    print(f"질문: {args.query}")
    print(f"리랭커: {settings.reranker_model if use_rerank else '없음'} / 판단: {'답변 시도' if ok else '확인 불가'}({reason})")
    for i, r in enumerate(rows, 1):
        body = " ".join(r["clean_text"].split())[:120]
        extra = f" (벡터 {r['vector_rank']}위 {r['vector_score']:.3f})" if "vector_rank" in r else ""
        print(f"{i}. [{r['score']:.3f}]{extra} {r['book_title']} {r['printed_page_number']}쪽 · {r['title']}\n   {body}")
    if not rows:
        print("검색 결과 없음(임베딩된 청크가 없거나 모두 검수 대기)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
