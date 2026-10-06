"""DB_APP_SCHEMA.supplements 접근(보충 이론 검토 대기, 003, D-J-004). 스키마 이름은 설정값에서만 가져온다."""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings

# file_uri(저장소 내부 위치)는 응답에서 뺀다.
_COLUMNS = sql.SQL(
    "id, report_id, query_log_id, source, kind, title, subject, question_text, content_text, "
    "original_filename, mime_type, byte_size, page_count, status, review_note, created_at, reviewed_at"
)


def insert_supplement(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    supplement_id: UUID,
    report_id: UUID | None,
    query_log_id: UUID | None,
    source: str,
    kind: str,
    title: str,
    subject: str | None,
    question_text: str | None,
    content_text: str | None,
    file_uri: str | None,
    original_filename: str | None,
    mime_type: str | None,
    byte_size: int | None,
    page_count: int | None,
) -> dict:
    """`supplement_id`는 파일을 먼저 저장하므로 호출하는 쪽에서 정한다."""
    q = sql.SQL(
        "INSERT INTO {a}.supplements (id, report_id, query_log_id, source, kind, title, subject, question_text, "
        "content_text, file_uri, original_filename, mime_type, byte_size, page_count) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {cols}"
    ).format(a=sql.Identifier(settings.db_app_schema), cols=_COLUMNS)
    params = (supplement_id, report_id, query_log_id, source, kind, title, subject, question_text, content_text,
              file_uri, original_filename, mime_type, byte_size, page_count)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, params).fetchone()


def list_supplements(
    conn: psycopg.Connection, settings: Settings, *, status: str | None = None, limit: int = 50
) -> list[dict]:
    """최신순. status를 주면 그 상태만(검토 대기 목록은 pending_review)."""
    where, params = (sql.SQL(""), ()) if status is None else (sql.SQL("WHERE status = %s"), (status,))
    q = sql.SQL("SELECT {cols} FROM {a}.supplements {where} ORDER BY created_at DESC LIMIT %s").format(
        cols=_COLUMNS, a=sql.Identifier(settings.db_app_schema), where=where
    )
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (*params, limit)).fetchall()
