"""팀 규격 query_logs 기록(질문 1건 = 1행). 3구간 판정·단계별 시간·인용 검증 결과는 metadata(JSONB)에 둔다."""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.core.config import Settings


def insert_query_log(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    question_text: str,
    retrieved_theory_ids: list[str],
    answer: str | None,
    latency_ms: int,
    token_usage: dict | None,
    metadata: dict,
) -> UUID:
    q = sql.SQL(
        "INSERT INTO {s}.query_logs (question_text, retrieved_theory_ids, answer, latency_ms, token_usage, metadata) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
    ).format(s=sql.Identifier(settings.db_schema))
    row = conn.execute(
        q,
        (
            question_text,
            Jsonb(retrieved_theory_ids),
            answer,
            latency_ms,
            Jsonb(token_usage) if token_usage else None,
            Jsonb(metadata),
        ),
    ).fetchone()
    return row[0]
