"""mingyu.processing_runs 접근. 업로드 1회 = 실행 1건."""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings

_RUN_COLUMNS = sql.SQL(
    "id, pipeline_version, paddle_model, gemini_model, embedding_model, started_at, finished_at, status, "
    "page_count, success_count, review_count, failure_count, cost_usd"
)


def create_run(conn: psycopg.Connection, settings: Settings, *, pipeline_version: str, page_count: int) -> UUID:
    q = sql.SQL(
        "INSERT INTO {s}.processing_runs (pipeline_version, gemini_model, embedding_model, page_count) "
        "VALUES (%s, %s, %s, %s) RETURNING id"
    ).format(s=sql.Identifier(settings.db_schema))
    params = (
        pipeline_version,
        settings.gemini_model_lite or None,
        settings.embedding_model or None,
        page_count,
    )
    return conn.execute(q, params).fetchone()[0]


def finish_run(
    conn: psycopg.Connection,
    settings: Settings,
    run_id: UUID,
    *,
    success: int,
    review: int,
    failure: int,
    incomplete: int = 0,
    interrupted: bool = False,
) -> str:
    """집계를 기록하고 최종 상태를 돌려준다.

    전부 성공 → SUCCESS, 전부 실패 → FAILED, 그 외(검토 필요, 미구현 단계에서 멈춤 포함) → PARTIAL.
    중간에 끊긴 실행(Ctrl+C 등, interrupted=True) → 개수와 상관없이 FAILED.
    미구현 단계에서 멈춘 페이지·끊겨서 못 돈 페이지는 어느 개수 컬럼에도 넣지 않는다(page_count - 합계 = 미완료).
    """
    total = success + review + failure + incomplete
    if interrupted or (total and failure == total):
        status = "FAILED"
    elif success == total:
        status = "SUCCESS"
    else:
        status = "PARTIAL"
    q = sql.SQL(
        "UPDATE {s}.processing_runs SET status = %s, finished_at = greatest(now(), started_at), "
        "success_count = %s, review_count = %s, failure_count = %s WHERE id = %s"
    ).format(s=sql.Identifier(settings.db_schema))
    conn.execute(q, (status, success, review, failure, run_id))
    return status


def get_run(conn: psycopg.Connection, settings: Settings, run_id: UUID) -> dict | None:
    q = sql.SQL("SELECT {cols} FROM {s}.processing_runs WHERE id = %s").format(
        cols=_RUN_COLUMNS, s=sql.Identifier(settings.db_schema)
    )
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (run_id,)).fetchone()
