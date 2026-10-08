"""DB_APP_SCHEMA.block_corrections 접근 + 이론 블록 수정 적용(005, D-JW-007).

트랜잭션은 호출하는 쪽에서 연다(승인은 이전 수정 superseded → 블록 수정 → 이 수정 applied를 한 트랜잭션으로).
blocks에서 바꾸는 칸: clean_text, embedding_text, embedding_text_hash, embedding, embedding_model, updated_at.
source_clean_text_hash·content_hash·raw_text는 JSON 원문 기준이라 건드리지 않는다(재적재 비교용).
"""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings

_COLUMNS = sql.SQL(
    "id, block_id, report_id, base_clean_text, base_clean_text_hash, new_clean_text, reason, status, "
    "review_note, reviewed_by, applied_note, created_at, reviewed_at, applied_at"
)


def _a(settings: Settings) -> sql.Identifier:
    return sql.Identifier(settings.db_app_schema)


def get_block(conn: psycopg.Connection, settings: Settings, block_id: str, *, for_update: bool = False) -> dict | None:
    """수정 화면·적용에 쓰는 블록 정보."""
    q = sql.SQL(
        "SELECT b.id, b.block_id, b.block_type, b.title, b.title_path, b.printed_page_number, b.clean_text, "
        "  b.raw_text, b.table_data, b.visual_data, "
        "  b.source_clean_text_hash, b.embedding_model, b.updated_at, d.title AS document_title "
        "FROM {a}.blocks b JOIN {a}.documents d ON d.id = b.document_id WHERE b.block_id = %s"
        + (" FOR UPDATE OF b" if for_update else "")
    ).format(a=_a(settings))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (block_id,)).fetchone()


def get(conn: psycopg.Connection, settings: Settings, correction_id: UUID, *, for_update: bool = False) -> dict | None:
    q = sql.SQL("SELECT {c} FROM {a}.block_corrections WHERE id = %s" + (" FOR UPDATE" if for_update else "")).format(
        c=_COLUMNS, a=_a(settings))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (correction_id,)).fetchone()


def insert(conn: psycopg.Connection, settings: Settings, *, block_id: str, report_id: UUID | None,
           base_clean_text: str, base_clean_text_hash: str, new_clean_text: str, reason: str) -> dict:
    q = sql.SQL(
        "INSERT INTO {a}.block_corrections "
        "(block_id, report_id, base_clean_text, base_clean_text_hash, new_clean_text, reason) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING {c}"
    ).format(a=_a(settings), c=_COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (block_id, report_id, base_clean_text, base_clean_text_hash, new_clean_text,
                               reason)).fetchone()


def list_(conn: psycopg.Connection, settings: Settings, *, status: str | None, block_id: str | None,
          report_id: UUID | None, limit: int) -> list[dict]:
    conds, params = [], []
    for col, val in (("status", status), ("block_id", block_id), ("report_id", report_id)):
        if val is not None:
            conds.append(sql.SQL("{} = %s").format(sql.Identifier(col)))
            params.append(val)
    where = sql.SQL("WHERE ") + sql.SQL(" AND ").join(conds) if conds else sql.SQL("")
    q = sql.SQL("SELECT {c} FROM {a}.block_corrections {w} ORDER BY created_at DESC LIMIT %s").format(
        c=_COLUMNS, a=_a(settings), w=where)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (*params, limit)).fetchall()


def active_for_block(conn: psycopg.Connection, settings: Settings, block_id: str) -> dict | None:
    """지금 적용 중(applied)인 수정."""
    q = sql.SQL("SELECT {c} FROM {a}.block_corrections WHERE block_id = %s AND status IN ('approved', 'applied') "
                "ORDER BY created_at DESC LIMIT 1").format(c=_COLUMNS, a=_a(settings))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (block_id,)).fetchone()


def set_status(conn: psycopg.Connection, settings: Settings, correction_id: UUID, status: str, *,
               review_note: str, reviewed_by: str | None, applied_note: str | None = None) -> dict:
    """proposed → applied / rejected / withdrawn. applied면 applied_at도 채운다."""
    q = sql.SQL(
        "UPDATE {a}.block_corrections SET status = %s::text, review_note = %s::text, reviewed_by = %s::text, reviewed_at = now(), "
        "applied_note = coalesce(%s::text, applied_note), "
        "applied_at = CASE WHEN %s::text = 'applied' THEN now() ELSE applied_at END "
        "WHERE id = %s RETURNING {c}"
    ).format(a=_a(settings), c=_COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (status, review_note, reviewed_by, applied_note, status, correction_id)).fetchone()


def supersede_active(conn: psycopg.Connection, settings: Settings, block_id: str, by_id: UUID) -> int:
    """같은 블록의 이전 approved/applied → superseded(부분 유니크 때문에 새 수정 적용 전에 먼저)."""
    q = sql.SQL(
        "UPDATE {a}.block_corrections SET status = 'superseded', "
        "applied_note = concat_ws(' / ', applied_note, %s::text) "
        "WHERE block_id = %s AND status IN ('approved', 'applied') AND id <> %s"
    ).format(a=_a(settings))
    return conn.execute(q, (f"superseded by {by_id}", block_id, by_id)).rowcount


def apply_to_block(conn: psycopg.Connection, settings: Settings, block_id: str, *, clean_text: str,
                   embedding_text: str, embedding_text_hash: str, embedding: str, embedding_model: str) -> int:
    q = sql.SQL(
        "UPDATE {a}.blocks SET clean_text = %s, embedding_text = %s, embedding_text_hash = %s, "
        "embedding = %s::public.vector, embedding_model = %s, updated_at = now() WHERE block_id = %s"
    ).format(a=_a(settings))
    return conn.execute(q, (clean_text, embedding_text, embedding_text_hash, embedding, embedding_model,
                            block_id)).rowcount
