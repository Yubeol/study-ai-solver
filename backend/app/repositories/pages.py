"""mingyu.pages 접근.

팀 규격에는 페이지 순서 컬럼이 없으므로 업로드 순서는 `page_metadata.upload_index`에,
파이프라인 세부 단계·오류는 `page_metadata.pipeline`에 둔다(DDL 변경 없음).
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import Settings

_PAGE_COLUMNS = sql.SQL(
    "id, book_id, processing_run_id, source_s3_uri, source_width, source_height, processing_status, "
    "quality_passed, review_required, "
    "(page_metadata->>'upload_index')::int AS upload_index, "
    "page_metadata->>'original_filename' AS original_filename, "
    "page_metadata->'pipeline' AS pipeline, created_at"
)
_ORDER = sql.SQL("ORDER BY (page_metadata->>'upload_index')::int NULLS LAST, created_at")


@dataclass(frozen=True)
class NewPage:
    id: UUID
    source_uri: str
    width: int
    height: int
    upload_index: int
    original_filename: str


def next_upload_index(conn: psycopg.Connection, settings: Settings, book_id: UUID) -> int:
    q = sql.SQL(
        "SELECT coalesce(max((page_metadata->>'upload_index')::int) + 1, 0) FROM {s}.pages WHERE book_id = %s"
    ).format(s=sql.Identifier(settings.db_schema))
    return conn.execute(q, (book_id,)).fetchone()[0]


def insert_pages(
    conn: psycopg.Connection, settings: Settings, book_id: UUID, run_id: UUID, pages: list[NewPage]
) -> None:
    q = sql.SQL(
        "INSERT INTO {s}.pages (id, book_id, source_s3_uri, source_width, source_height, "
        "processing_run_id, page_metadata) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.cursor() as cur:
        cur.executemany(
            q,
            [
                (
                    p.id,
                    book_id,
                    p.source_uri,
                    p.width,
                    p.height,
                    run_id,
                    Jsonb({"upload_index": p.upload_index, "original_filename": p.original_filename}),
                )
                for p in pages
            ],
        )


def list_pages_by_book(conn: psycopg.Connection, settings: Settings, book_id: UUID) -> list[dict]:
    q = sql.SQL("SELECT {cols} FROM {s}.pages WHERE book_id = %s {order}").format(
        cols=_PAGE_COLUMNS, s=sql.Identifier(settings.db_schema), order=_ORDER
    )
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (book_id,)).fetchall()


def list_pages_by_run(conn: psycopg.Connection, settings: Settings, run_id: UUID) -> list[dict]:
    q = sql.SQL("SELECT {cols} FROM {s}.pages WHERE processing_run_id = %s {order}").format(
        cols=_PAGE_COLUMNS, s=sql.Identifier(settings.db_schema), order=_ORDER
    )
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (run_id,)).fetchall()


def get_page(conn: psycopg.Connection, settings: Settings, page_id: UUID) -> dict | None:
    q = sql.SQL("SELECT {cols} FROM {s}.pages WHERE id = %s").format(
        cols=_PAGE_COLUMNS, s=sql.Identifier(settings.db_schema)
    )
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (page_id,)).fetchone()


def set_pipeline_info(conn: psycopg.Connection, settings: Settings, page_id: UUID, info: dict) -> None:
    """상태는 그대로 두고 `page_metadata.pipeline`만 바꾼다(현재 단계 표시용)."""
    q = sql.SQL(
        "UPDATE {s}.pages SET page_metadata = page_metadata || jsonb_build_object('pipeline', %s::jsonb) "
        "WHERE id = %s"
    ).format(s=sql.Identifier(settings.db_schema))
    conn.execute(q, (Jsonb(info), page_id))


def set_status(
    conn: psycopg.Connection, settings: Settings, page_id: UUID, status: str, info: dict
) -> None:
    """processing_status와 `page_metadata.pipeline`을 함께 바꾼다.

    VERIFIED 이후(EMBEDDED 포함)는 품질 통과, REVIEW_REQUIRED는 검토 필요로 표시한다.
    """
    q = sql.SQL(
        "UPDATE {s}.pages SET processing_status = %s, "
        "  quality_passed = CASE WHEN %s IN ('VERIFIED', 'EMBEDDED') THEN true "
        "                        WHEN %s IN ('REVIEW_REQUIRED', 'FAILED') THEN false ELSE quality_passed END, "
        "  review_required = (%s = 'REVIEW_REQUIRED'), "
        "  page_metadata = page_metadata || jsonb_build_object('pipeline', %s::jsonb) "
        "WHERE id = %s"
    ).format(s=sql.Identifier(settings.db_schema))
    conn.execute(q, (status, status, status, status, Jsonb(info), page_id))
