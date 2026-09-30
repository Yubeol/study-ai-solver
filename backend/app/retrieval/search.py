"""이론 청크 벡터 검색 (D-020). 검색 대상은 v_searchable_theory(needs_review=false, 임베딩 있음, embedding_enabled).

    cd backend
    uv run python -m app.retrieval.search "DIKW 피라미드의 구성요소는?"
    uv run python -m app.retrieval.search "질문" --k 10
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
        "SELECT t.id, t.title, t.clean_text, t.exam_clues, p.printed_page_number, b.title AS book_title, "
        "  1 - (t.embedding <=> %s::public.vector) AS score "
        "FROM {s}.v_searchable_theory t "
        "JOIN {s}.pages p ON p.id = t.page_id JOIN {s}.books b ON b.id = p.book_id "
        "ORDER BY t.embedding <=> %s::public.vector LIMIT %s"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (query_vec, query_vec, k)).fetchall()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="이론 청크 벡터 검색 확인")
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=None, help="가져올 개수(기본 SEARCH_TOP_K)")
    args = ap.parse_args(argv)

    from app.db.connection import connect

    settings = get_settings()
    vec = to_pgvector(get_embedder(settings).encode([args.query])[0])
    with connect(settings) as conn:
        rows = search_theory(conn, settings, vec, args.k or settings.search_top_k)
    print(f"질문: {args.query}")
    for i, r in enumerate(rows, 1):
        body = " ".join(r["clean_text"].split())[:120]
        print(f"{i}. [{r['score']:.3f}] {r['book_title']} {r['printed_page_number']}쪽 · {r['title']}\n   {body}")
    if not rows:
        print("검색 결과 없음(임베딩된 청크가 없거나 모두 검수 대기)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
