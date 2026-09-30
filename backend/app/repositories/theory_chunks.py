"""mingyu.theory_chunks / excluded_sections 접근 (청킹 결과 저장, D-019).

재실행 시 페이지 단위 트랜잭션으로 그 페이지의 청크와 청킹이 만든 제외 구간을 지우고 다시 넣는다.
청크를 다시 만들면 임베딩도 사라지므로 embed 단계를 다시 돌려야 한다.
"""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.ingestion.chunking import Chunk, ExcludedBlock

# 청킹 단계가 만드는 excluded_sections.section_type (다른 단계가 만든 제외 구간은 건드리지 않는다)
CHUNKER_SECTION_TYPES = ("exam_question",)


def replace_page_chunks(
    conn: psycopg.Connection,
    settings: Settings,
    page_id: UUID,
    run_id: UUID | None,
    chunks: list[Chunk],
    excluded: list[ExcludedBlock],
    metadata: dict,
    text_uri: str,
) -> None:
    """한 페이지의 청크·제외 구간·page_metadata.chunking을 한 트랜잭션으로 바꾼다.

    제외 구간의 원문 위치는 source_region_ids에 [{"type": "page_text_lines", "text_uri", "line_range"}]로 남긴다
    (팀 규격 주석 없음, D-019). text_uri의 추출 결과를 line_range로 잘라 기출 텍스트를 복원할 수 있다.
    """
    s = sql.Identifier(settings.db_schema)
    with conn.transaction():
        conn.execute(sql.SQL("DELETE FROM {s}.theory_chunks WHERE page_id = %s").format(s=s), (page_id,))
        conn.execute(
            sql.SQL("DELETE FROM {s}.excluded_sections WHERE page_id = %s AND section_type = ANY(%s)").format(s=s),
            (page_id, list(CHUNKER_SECTION_TYPES)),
        )
        with conn.cursor() as cur:
            if chunks:
                cur.executemany(
                    sql.SQL(
                        "INSERT INTO {s}.theory_chunks (page_id, title, raw_text, clean_text, exam_clues, "
                        "embedding_text, sort_order, processing_run_id, source_alignment, needs_review, review_reasons) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    ).format(s=s),
                    [
                        (
                            page_id,
                            c.title,
                            c.raw_text,
                            c.clean_text,
                            Jsonb(c.exam_clues),
                            c.embedding_text,
                            c.sort_order,
                            run_id,
                            Jsonb({"method": "page_text_lines", "path": c.path, "line_range": c.line_range}),
                            c.needs_review,
                            Jsonb(c.review_reasons),
                        )
                        for c in chunks
                    ],
                )
            if excluded:
                cur.executemany(
                    sql.SQL(
                        "INSERT INTO {s}.excluded_sections (page_id, section_type, title, reason, source_region_ids) "
                        "VALUES (%s, %s, %s, %s, %s)"
                    ).format(s=s),
                    [
                        (
                            page_id,
                            e.section_type,
                            e.title,
                            e.reason,
                            Jsonb([{"type": "page_text_lines", "text_uri": text_uri, "line_range": e.line_range}]),
                        )
                        for e in excluded
                    ],
                )
        conn.execute(
            sql.SQL("UPDATE {s}.pages SET page_metadata = page_metadata || %s::jsonb WHERE id = %s").format(s=s),
            (Jsonb({"chunking": metadata}), page_id),
        )


def count_by_page(conn: psycopg.Connection, settings: Settings, page_id: UUID) -> int:
    q = sql.SQL("SELECT count(*) FROM {s}.theory_chunks WHERE page_id = %s").format(s=sql.Identifier(settings.db_schema))
    return conn.execute(q, (page_id,)).fetchone()[0]


def list_for_embedding(conn: psycopg.Connection, settings: Settings, page_id: UUID) -> list[tuple[UUID, str]]:
    """임베딩할 청크(id, embedding_text). needs_review=true인 조각은 검색에서 빠지므로 임베딩하지 않는다."""
    q = sql.SQL(
        "SELECT id, embedding_text FROM {s}.theory_chunks WHERE page_id = %s AND NOT needs_review ORDER BY sort_order"
    ).format(s=sql.Identifier(settings.db_schema))
    return conn.execute(q, (page_id,)).fetchall()


def save_embeddings(conn: psycopg.Connection, settings: Settings, rows: list[tuple[UUID, str]]) -> None:
    """(chunk_id, pgvector 텍스트) 목록을 저장하고 embedding_enabled=true, needs_review=false로 둔다."""
    q = sql.SQL(
        "UPDATE {s}.theory_chunks SET embedding = %s::public.vector, embedding_enabled = true, needs_review = false "
        "WHERE id = %s"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(q, [(vec, chunk_id) for chunk_id, vec in rows])
