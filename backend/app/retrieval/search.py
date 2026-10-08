"""근거 검색. 검색 대상(SEARCH_CORPUS, D-M-033):
- team_text: 이론 청크(v_searchable_theory, D-020)
- common_json: 공통 JSON 블록(mingyu_app.v_searchable_blocks, D-M-032)
- mixed: documents(corpus='common_json')에 연결된 book은 블록, 나머지 book은 이론 청크. 각각 후보 N개를 가져와
  cosine 점수(같은 bge-m3 정규화 벡터)로 합친 뒤 상위 N개. 과목 목록은 설정에 없다(공통 JSON을 적재하면 자동 전환).
- 사용자 보충(D-M-035): 검색 대상과 상관없이 mingyu_app.supplements(rejected 제외, 벡터 있는 텍스트 보충)에서도 N개를
  가져와 같은 cosine 점수로 합친다. book 범위(book_ids)를 주면 보충은 어느 book에도 속하지 않으므로 넣지 않는다.

벡터 후보 → (RERANKER_MODEL이 있으면) 리랭커 → 상위 K개. "확인 불가" 판단(벡터 하한 + 리랭커 3구간)은 is_answerable.
search_candidates는 두 대상의 행을 같은 모양(kind·corpus·block_id·path·raw_text 문자열 등)으로 맞춰 돌려준다.

    cd backend
    uv run python -m app.retrieval.search "DIKW 피라미드의 구성요소는?"
    uv run python -m app.retrieval.search "질문" --k 10 --corpus mixed
    uv run python -m app.retrieval.search "질문" --no-rerank
"""

import argparse
import sys
from collections import Counter
from collections.abc import Collection
from typing import Literal
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.ingestion.common_json import CORPUS as COMMON_JSON
from app.ingestion.common_json import TITLE_PATH_SEP, block_display_text, block_from_row, embedding_text
from app.ingestion.embedding import get_embedder, to_pgvector

TEAM_TEXT = "team_text"
SUPPLEMENT = "supplement"
SUPPLEMENT_LABEL = "사용자 보충"  # 보충 근거의 책 제목·문서 제목 표시
Corpus = Literal["team_text", "common_json", "mixed"]
CORPORA = ("team_text", "common_json", "mixed")


def search_theory(conn: psycopg.Connection, settings: Settings, query_vec: str, k: int, *,
                  book_ids: Collection[UUID] | None = None,
                  exclude_book_ids: Collection[UUID] | None = None) -> list[dict]:
    """이론 청크를 cosine 거리(<=>) 순으로 k개. query_vec은 pgvector 텍스트(정규화된 질문 벡터).

    book_ids를 주면 그 book만, exclude_book_ids를 주면 그 book을 뺀다(mixed).
    """
    conds, params = _book_conds("p.book_id", book_ids, exclude_book_ids)
    where = sql.SQL("WHERE ") + sql.SQL(" AND ").join(conds) if conds else sql.SQL("")
    q = sql.SQL(
        "SELECT t.id, t.title, t.raw_text, t.clean_text, t.embedding_text, t.exam_clues, "
        "  t.source_alignment->'path' AS title_path, p.printed_page_number, p.book_id, b.title AS book_title, "
        "  1 - (t.embedding <=> %s::public.vector) AS score "
        "FROM {s}.v_searchable_theory t "
        "JOIN {s}.pages p ON p.id = t.page_id JOIN {s}.books b ON b.id = p.book_id {where} "
        "ORDER BY t.embedding <=> %s::public.vector LIMIT %s"
    ).format(s=sql.Identifier(settings.db_schema), where=where)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (query_vec, *params, query_vec, k)).fetchall()


def search_blocks(conn: psycopg.Connection, settings: Settings, query_vec: str, k: int, *,
                  book_ids: Collection[UUID] | None = None) -> list[dict]:
    """공통 JSON 블록(v_searchable_blocks)을 cosine 거리 순으로 k개(DB 행 그대로, block_row로 변환).

    book_ids를 주면 그 book에 연결된 문서의 블록만.
    """
    conds, params = _book_conds("d.book_id", book_ids, None)
    where = sql.SQL("").join(sql.SQL(" AND ") + c for c in conds)
    q = sql.SQL(
        "SELECT b.id, b.block_id, b.block_type, b.title, b.title_path, b.raw_text, b.clean_text, b.table_data, "
        "  b.visual_data, b.source, b.embedding_text, b.thumbnail_s3_key, b.crop_s3_key, b.printed_page_number, d.book_id, "
        "  coalesce(bk.title, d.title) AS book_title, d.title AS document_title, "
        "  1 - (b.embedding <=> %s::public.vector) AS score "
        "FROM {a}.v_searchable_blocks b JOIN {a}.documents d ON d.id = b.document_id "
        "LEFT JOIN {s}.books bk ON bk.id = d.book_id "
        "WHERE d.corpus = %s {where} "
        "ORDER BY b.embedding <=> %s::public.vector LIMIT %s"
    ).format(a=sql.Identifier(settings.db_app_schema), s=sql.Identifier(settings.db_schema), where=where)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (query_vec, COMMON_JSON, *params, query_vec, k)).fetchall()


def search_supplements(conn: psycopg.Connection, settings: Settings, query_vec: str, k: int) -> list[dict]:
    """사용자 보충(rejected 제외, 벡터 있는 행 = 텍스트 보충)을 cosine 거리 순으로 k개(D-M-035)."""
    q = sql.SQL(
        "SELECT id, title, subject, content_text, embedding_text, 1 - (embedding <=> %s::public.vector) AS score "
        "FROM {a}.supplements WHERE status <> 'rejected' AND embedding IS NOT NULL "
        "ORDER BY embedding <=> %s::public.vector LIMIT %s"
    ).format(a=sql.Identifier(settings.db_app_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (query_vec, query_vec, k)).fetchall()


def common_json_book_ids(conn: psycopg.Connection, settings: Settings) -> set[UUID]:
    """공통 JSON 문서가 연결된 book(mixed에서 블록으로 검색할 book)."""
    q = sql.SQL("SELECT DISTINCT book_id FROM {a}.documents WHERE corpus = %s AND book_id IS NOT NULL").format(
        a=sql.Identifier(settings.db_app_schema))
    return {r[0] for r in conn.execute(q, (COMMON_JSON,)).fetchall()}


def _book_conds(column: str, include, exclude) -> tuple[list[sql.Composable], list]:
    """book 범위 조건 목록과 파라미터. include는 그 book만(빈 목록이면 결과 없음), exclude는 그 book 빼기."""
    conds, params = [], []
    if include is not None:
        conds.append(sql.SQL(column + " = ANY(%s)"))
        params.append(list(include))
    if exclude:
        conds.append(sql.SQL(column + " <> ALL(%s)"))
        params.append(list(exclude))
    return conds, params


# ---------- 행 모양 맞추기 ----------


def theory_row(r: dict) -> dict:
    """이론 청크 행 + 공통 필드. path는 질의 흐름에서 embedding_text로 구한다(heading_path)."""
    return {
        **r,
        "kind": "theory",
        "corpus": TEAM_TEXT,
        "block_id": None,
        "title_path": r.get("title_path") or [],
        "document_title": r["book_title"],
        "thumbnail_url": None,
        "image_url": None,
    }


def block_row(settings: Settings, r: dict) -> dict:
    """블록 DB 행 → 이론 청크와 같은 모양.

    - clean_text: LLM·판정기에 넘기는 본문 = embedding_text(with_path=False). 이론은 clean_text,
      표는 [표] 제목 + 행, 그림은 [그림] 제목 + 설명 + 구조 + 그림 속 글자(제목 경로는 path로 따로)
    - raw_text: 화면 표시용 문자열. 이론은 원문 그대로, 표·그림(원문 목록)은 줄바꿈으로 잇기만 한다.
      원문이 비면 코드는 clean_code, 수식은 plain_text(D-M-034)
    - printed_page_number: 이론 청크(pages.printed_page_number, text)와 같게 문자열
    """
    return {
        "id": r["id"],
        "kind": r["block_type"],
        "corpus": COMMON_JSON,
        "block_id": r["block_id"],
        "title": r["title"],
        "title_path": list(r["title_path"] or []),
        "path": TITLE_PATH_SEP.join(r["title_path"] or []) or (r["title"] or ""),
        "raw_text": block_display_text(r),
        "clean_text": embedding_text(block_from_row(r), with_path=False),
        "embedding_text": r["embedding_text"],
        "exam_clues": None,
        "printed_page_number": str(r["printed_page_number"]),
        "book_id": r["book_id"],
        "book_title": r["book_title"],
        "document_title": r["document_title"],
        "thumbnail_url": settings.asset_url(r.get("thumbnail_s3_key")),
        "image_url": settings.asset_url(r.get("crop_s3_key")),
        "score": r["score"],
    }


def supplement_row(r: dict) -> dict:
    """보충 행 → 이론 청크와 같은 모양. 본문을 그대로 raw_text(표시)·clean_text(LLM·판정기 입력)로 쓴다.

    쪽 번호·book은 없다(None). 제목 경로 자리에는 사용자가 붙인 제목을 둔다.
    """
    title = r["title"] or ""
    return {
        "id": r["id"],
        "kind": SUPPLEMENT,
        "corpus": SUPPLEMENT,
        "block_id": None,
        "title": title,
        "title_path": [title] if title else [],
        "path": title,
        "raw_text": r["content_text"],
        "clean_text": r["content_text"],
        "embedding_text": r["embedding_text"],
        "exam_clues": None,
        "printed_page_number": None,
        "book_id": None,
        "book_title": SUPPLEMENT_LABEL,
        "document_title": SUPPLEMENT_LABEL,
        "thumbnail_url": None,
        "image_url": None,
        "score": r["score"],
    }


def supplement_embedding_text(title: str, content: str) -> str:
    """보충 임베딩 입력 = "제목\\n\\n본문"(이론 청크의 "제목 경로\\n\\nclean_text"와 같은 모양). 제목이 없으면 본문만."""
    return f"{title}\n\n{content}" if title else content


def merge_candidates(groups: list[list[dict]], n: int) -> list[dict]:
    """여러 대상의 후보를 벡터 점수 내림차순으로 합쳐 n개. 같은 점수는 groups 순서(안정 정렬)."""
    merged = [r for g in groups for r in g]
    merged.sort(key=lambda r: -float(r["score"]))
    return merged[:n]


def candidate_sources(rows: list[dict]) -> dict[str, int]:
    """후보가 어느 대상에서 왔는지 개수(query_logs.metadata.candidate_sources)."""
    return dict(Counter(r["corpus"] for r in rows))


def search_candidates(conn: psycopg.Connection, settings: Settings, query_vec: str, n: int,
                      corpus: Corpus | None = None, *, book_ids: Collection[UUID] | None = None) -> list[dict]:
    """검색 대상에 맞춰 벡터 후보 n개(점수 내림차순, 같은 모양의 행).

    book_ids를 주면 그 book 범위만 검색한다(평가 --subjects). mixed는 각 대상에서 n개씩 가져와 합친다.
    book_ids가 없으면 사용자 보충 n개도 가져와 합친다(D-M-035, 같은 점수면 교재 먼저).
    """
    rows = _corpus_candidates(conn, settings, query_vec, n, corpus or settings.search_corpus, book_ids)
    if book_ids is not None:
        return rows
    supplements = [supplement_row(r) for r in search_supplements(conn, settings, query_vec, n)]
    return merge_candidates([rows, supplements], n) if supplements else rows


def _corpus_candidates(conn: psycopg.Connection, settings: Settings, query_vec: str, n: int, corpus: str,
                       book_ids: Collection[UUID] | None) -> list[dict]:
    if corpus == TEAM_TEXT:
        return [theory_row(r) for r in search_theory(conn, settings, query_vec, n, book_ids=book_ids)]
    if corpus == COMMON_JSON:
        return [block_row(settings, r) for r in search_blocks(conn, settings, query_vec, n, book_ids=book_ids)]
    if corpus != "mixed":
        raise ValueError(f"알 수 없는 검색 대상: {corpus!r}")
    covered = common_json_book_ids(conn, settings)
    theory = [theory_row(r) for r in search_theory(conn, settings, query_vec, n, book_ids=book_ids,
                                                   exclude_book_ids=covered)]
    blocks = [block_row(settings, r) for r in search_blocks(conn, settings, query_vec, n, book_ids=book_ids)]
    return merge_candidates([theory, blocks], n)


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
    settings = get_settings()
    ap = argparse.ArgumentParser(description="근거 검색 확인")
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=None, help="보여줄 개수(기본 SEARCH_TOP_K)")
    ap.add_argument("--no-rerank", action="store_true", help="RERANKER_MODEL이 있어도 벡터 순위만")
    ap.add_argument("--corpus", choices=CORPORA, default=settings.search_corpus,
                    help="검색 대상(기본 SEARCH_CORPUS)")
    args = ap.parse_args(argv)

    from app.db.connection import connect

    k = args.k or settings.search_top_k
    use_rerank = bool(settings.reranker_model) and not args.no_rerank
    vec = to_pgvector(get_embedder(settings).encode([args.query])[0])
    with connect(settings) as conn:
        n = max(k, settings.search_candidates_n) if use_rerank else k
        rows = search_candidates(conn, settings, vec, n, args.corpus)
    sources = candidate_sources(rows)
    vector_top = float(rows[0]["score"]) if rows else None
    rerank_top = None
    if use_rerank and rows:
        from app.retrieval.rerank import get_reranker, rerank

        rows = rerank(args.query, rows, get_reranker(settings), settings.reranker_input)
        rerank_top = rows[0]["rerank_score"]
    rows = rows[:k]
    zone, reason = is_answerable(settings, vector_top, rerank_top)
    print(f"질문: {args.query}")
    print(f"검색 대상: {args.corpus} (후보 {sources}) / 리랭커: {settings.reranker_model if use_rerank else '없음'} "
          f"/ 판단: {ZONE_LABELS[zone]}({reason})")
    for i, r in enumerate(rows, 1):
        body = " ".join(r["clean_text"].split())[:120]
        extra = f" (벡터 {r['vector_rank']}위 {r['vector_score']:.3f})" if "vector_rank" in r else ""
        print(f"{i}. [{r['score']:.3f}]{extra} {r['kind']} {r['block_id'] or r['id']} · {r['book_title']} "
              f"{r['printed_page_number']}쪽 · {r['title']}\n   {body}")
    if not rows:
        print("검색 결과 없음(임베딩된 청크·블록이 없거나 모두 검수 대기)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
