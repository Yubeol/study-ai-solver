"""근거 이론 블록과 연결된 그림·표 블록 조회(mingyu_app.block_relations, D-JW-008).

근거 K개의 block_id를 한 번에 넘겨 쿼리 1번으로 가져온다. 방향은 양쪽 다 본다
(이론이 from이든 to든). 걸러내기(신뢰도·개수·중복)는 호출하는 쪽(app/qa/related_visuals.py)에서 한다.
"""

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings

LINK_TYPES = ["THEORY_TO_VISUAL", "THEORY_TO_TABLE", "VISUAL_TO_THEORY", "TABLE_TO_THEORY"]


def fetch(conn: psycopg.Connection, settings: Settings, block_ids: list[str]) -> list[dict]:
    """[{source_block_id, block_id, block_type, title, thumbnail_s3_key, crop_s3_key, confidence}] — 그림·표 블록만."""
    if not block_ids:
        return []
    q = sql.SQL(
        "SELECT l.source_block_id, b.block_id, b.block_type, b.title, b.thumbnail_s3_key, b.crop_s3_key, l.confidence "
        "FROM ("
        "  SELECT from_block_id AS source_block_id, to_block_id AS other_block_id, confidence "
        "  FROM {a}.block_relations WHERE from_block_id = ANY(%(ids)s) AND link_type = ANY(%(types)s) "
        "  UNION ALL "
        "  SELECT to_block_id, from_block_id, confidence "
        "  FROM {a}.block_relations WHERE to_block_id = ANY(%(ids)s) AND link_type = ANY(%(types)s)"
        ") l JOIN {a}.blocks b ON b.block_id = l.other_block_id "
        "WHERE b.block_type IN ('visual', 'table')"
    ).format(a=sql.Identifier(settings.db_app_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, {"ids": list(block_ids), "types": LINK_TYPES}).fetchall()
