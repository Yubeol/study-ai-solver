"""DB_APP_SCHEMA.answer_reports 접근(답변 오류 신고, 003, D-JW-004). 스키마 이름은 설정값에서만 가져온다."""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.ingestion.common_json import TITLE_PATH_SEP, raw_text_display

_COLUMNS = sql.SQL(
    "id, query_log_id, question_text, answer_text, report_type, concept_details, detail, "
    "evidence_snapshot, status, created_at, resolved_at, resolution, resolution_note, linked_block_ids, reviewed_by"
)


def get_query_log(conn: psycopg.Connection, settings: Settings, query_log_id: UUID) -> dict | None:
    """신고 스냅샷에 쓸 질문 기록: question_text, answer, evidence(metadata.evidence 목록)."""
    q = sql.SQL(
        "SELECT question_text, answer, coalesce(metadata->'evidence', '[]'::jsonb) AS evidence "
        "FROM {s}.query_logs WHERE id = %s"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (query_log_id,)).fetchone()


def get_chunks(conn: psycopg.Connection, settings: Settings, chunk_ids: list[str]) -> dict[str, dict]:
    """청크 id → 근거 표시용 정보(책 제목, 인쇄 쪽, 제목, 원문). 재적재로 없어진 id는 빠진다."""
    ids = []
    for cid in chunk_ids:
        try:
            ids.append(UUID(str(cid)))
        except ValueError:
            continue
    if not ids:
        return {}
    q = sql.SQL(
        "SELECT t.id, t.title, t.raw_text, t.clean_text, t.embedding_text, p.printed_page_number, b.title AS book_title "
        "FROM {s}.theory_chunks t JOIN {s}.pages p ON p.id = t.page_id JOIN {s}.books b ON b.id = p.book_id "
        "WHERE t.id = ANY(%s)"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return {str(r["id"]): r for r in cur.execute(q, (ids,)).fetchall()}


def get_blocks(conn: psycopg.Connection, settings: Settings, ids: list[str]) -> dict[str, dict]:
    """공통 JSON 블록 id(blocks.id) → get_chunks와 같은 모양(책 제목, 인쇄 쪽, 제목, 원문 문자열) + path.

    근거의 chunk_id가 corpus=common_json이면 blocks.id다(D-M-033). 다시 적재해 없어진 id는 빠진다.
    """
    uuids = []
    for i in ids:
        try:
            uuids.append(UUID(str(i)))
        except ValueError:
            continue
    if not uuids:
        return {}
    q = sql.SQL(
        "SELECT b.id, b.title, b.title_path, b.raw_text, b.printed_page_number, "
        "  coalesce(bk.title, d.title) AS book_title "
        "FROM {a}.blocks b JOIN {a}.documents d ON d.id = b.document_id LEFT JOIN {s}.books bk ON bk.id = d.book_id "
        "WHERE b.id = ANY(%s)"
    ).format(a=sql.Identifier(settings.db_app_schema), s=sql.Identifier(settings.db_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(q, (uuids,)).fetchall()
    return {
        str(r["id"]): {
            "title": r["title"],
            "book_title": r["book_title"],
            "printed_page_number": str(r["printed_page_number"]),
            "raw_text": raw_text_display(r["raw_text"]),
            "path": TITLE_PATH_SEP.join(r["title_path"] or []) or r["title"],
        }
        for r in rows
    }


def insert_report(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    query_log_id: UUID | None,
    question_text: str,
    answer_text: str | None,
    report_type: str,
    concept_details: list[str],
    detail: str,
    evidence_snapshot: list[dict],
) -> dict:
    q = sql.SQL(
        "INSERT INTO {a}.answer_reports "
        "(query_log_id, question_text, answer_text, report_type, concept_details, detail, evidence_snapshot) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {cols}"
    ).format(a=sql.Identifier(settings.db_app_schema), cols=_COLUMNS)
    params = (query_log_id, question_text, answer_text, report_type, Jsonb(concept_details), detail,
              Jsonb(evidence_snapshot))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, params).fetchone()


def list_reports(
    conn: psycopg.Connection, settings: Settings, *, status: str | None = None, limit: int = 50
) -> list[dict]:
    """최신순. status를 주면 그 상태만."""
    where, params = (sql.SQL(""), ()) if status is None else (sql.SQL("WHERE status = %s"), (status,))
    q = sql.SQL("SELECT {cols} FROM {a}.answer_reports {where} ORDER BY created_at DESC LIMIT %s").format(
        cols=_COLUMNS, a=sql.Identifier(settings.db_app_schema), where=where
    )
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (*params, limit)).fetchall()


def set_status(conn: psycopg.Connection, settings: Settings, report_id: UUID, status: str) -> dict | None:
    """신고 하나의 상태만 바꾼다. resolved면 resolved_at = now(), open이면 NULL."""
    q = sql.SQL(
        "UPDATE {a}.answer_reports SET status = %s, "
        "resolved_at = CASE WHEN %s = 'resolved' THEN coalesce(resolved_at, now()) ELSE NULL END "
        "WHERE id = %s RETURNING {cols}"
    ).format(a=sql.Identifier(settings.db_app_schema), cols=_COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (status, status, report_id)).fetchone()


def update_review(
    conn: psycopg.Connection,
    settings: Settings,
    report_id: UUID,
    *,
    status: str | None,
    resolution: str | None,
    resolution_note: str | None,
    linked_block_ids: list[str] | None,
    reviewed_by: str | None,
) -> dict | None:
    """처리 결과 갱신(005, D-JW-007). None인 값은 그대로 둔다. resolved면 resolved_at = now(), open이면 NULL.
    resolved인데 resolution이 없으면 DB CHECK(answer_reports_resolution_required)에 걸린다."""
    q = sql.SQL(
        "UPDATE {a}.answer_reports SET "
        "status = coalesce(%(status)s::text, status), "
        "resolved_at = CASE WHEN coalesce(%(status)s::text, status) = 'resolved' THEN coalesce(resolved_at, now()) "
        "  ELSE NULL END, "
        "resolution = coalesce(%(resolution)s::text, resolution), "
        "resolution_note = coalesce(%(resolution_note)s::text, resolution_note), "
        "linked_block_ids = coalesce(%(linked)s::jsonb, linked_block_ids), "
        "reviewed_by = coalesce(%(reviewed_by)s::text, reviewed_by) "
        "WHERE id = %(id)s RETURNING {cols}"
    ).format(a=sql.Identifier(settings.db_app_schema), cols=_COLUMNS)
    params = {"status": status, "resolution": resolution, "resolution_note": resolution_note,
              "linked": Jsonb(linked_block_ids) if linked_block_ids is not None else None,
              "reviewed_by": reviewed_by, "id": report_id}
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, params).fetchone()


def report_exists(conn: psycopg.Connection, settings: Settings, report_id: UUID) -> bool:
    q = sql.SQL("SELECT 1 FROM {a}.answer_reports WHERE id = %s").format(a=sql.Identifier(settings.db_app_schema))
    return conn.execute(q, (report_id,)).fetchone() is not None
