"""mingyu.books 접근. 스키마 이름은 설정값에서만 가져와 Identifier로 명시한다."""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings

_BOOK_COLUMNS = sql.SQL("b.id, b.title, b.subject, b.material_type, b.edition, b.source_name, b.created_at")


def create_book(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    title: str,
    subject: str,
    material_type: str,
    edition: str | None = None,
    source_name: str | None = None,
    book_id: UUID | None = None,
) -> dict:
    """`book_id`를 주면 그 id로 만든다(파일을 먼저 저장해야 하는 반입 스크립트용)."""
    q = sql.SQL(
        "INSERT INTO {s}.books AS b (id, title, subject, material_type, edition, source_name) "
        "VALUES (coalesce(%s, gen_random_uuid()), %s, %s, %s, %s, %s) RETURNING {cols}"
    ).format(s=sql.Identifier(settings.db_schema), cols=_BOOK_COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (book_id, title, subject, material_type, edition, source_name)).fetchone()


def find_book_ids(
    conn: psycopg.Connection, settings: Settings, *, subject: str, title: str, source_name: str
) -> list[UUID]:
    """같은 과목·제목·출처의 books id 목록(반입 재실행 시 중복 방지용)."""
    q = sql.SQL("SELECT id FROM {s}.books WHERE subject = %s AND title = %s AND source_name = %s").format(
        s=sql.Identifier(settings.db_schema)
    )
    return [r[0] for r in conn.execute(q, (subject, title, source_name)).fetchall()]


def _select_with_counts(settings: Settings, where: sql.Composable) -> sql.Composed:
    # 페이지 수와 상태별 개수를 함께 돌려준다(화면 A의 처리 상태 표시용).
    return sql.SQL(
        "SELECT {cols}, "
        "  coalesce(sum(c.n), 0)::int AS page_count, "
        "  coalesce(jsonb_object_agg(c.st, c.n) FILTER (WHERE c.st IS NOT NULL), '{{}}'::jsonb) AS status_counts "
        "FROM {s}.books b "
        "LEFT JOIN ("
        "  SELECT book_id, processing_status AS st, count(*)::int AS n FROM {s}.pages "
        "  GROUP BY book_id, processing_status"
        ") c ON c.book_id = b.id "
        "{where} GROUP BY b.id ORDER BY b.subject, b.created_at"
    ).format(cols=_BOOK_COLUMNS, s=sql.Identifier(settings.db_schema), where=where)


def list_books(conn: psycopg.Connection, settings: Settings, subject: str | None = None) -> list[dict]:
    if subject is None:
        where, params = sql.SQL(""), ()
    else:
        where, params = sql.SQL("WHERE b.subject = %s"), (subject,)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(_select_with_counts(settings, where), params).fetchall()


def get_book(conn: psycopg.Connection, settings: Settings, book_id: UUID) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(_select_with_counts(settings, sql.SQL("WHERE b.id = %s")), (book_id,)).fetchone()


def list_subjects(conn: psycopg.Connection, settings: Settings) -> list[str]:
    q = sql.SQL("SELECT DISTINCT subject FROM {s}.books WHERE subject IS NOT NULL ORDER BY subject").format(
        s=sql.Identifier(settings.db_schema)
    )
    return [r[0] for r in conn.execute(q).fetchall()]


def get_material_type(conn: psycopg.Connection, settings: Settings, book_id: UUID) -> str | None:
    q = sql.SQL("SELECT material_type FROM {s}.books WHERE id = %s").format(s=sql.Identifier(settings.db_schema))
    row = conn.execute(q, (book_id,)).fetchone()
    return row[0] if row else None
