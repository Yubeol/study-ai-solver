"""mingyu_app.documents / blocks / block_relations 접근 (공통 JSON 적재, D-M-032).

스키마는 설정값(DB_APP_SCHEMA)에서만 가져와 Identifier로 명시한다. 트랜잭션은 호출하는 쪽에서 연다.
"""

from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.ingestion.common_json import BlockPlan, ExistingBlock, RelationRecord, SubjectData


def _a(settings: Settings) -> sql.Identifier:
    return sql.Identifier(settings.db_app_schema)


def get_document_id(conn: psycopg.Connection, settings: Settings, document_key: str) -> UUID | None:
    q = sql.SQL("SELECT id FROM {a}.documents WHERE document_key = %s").format(a=_a(settings))
    row = conn.execute(q, (document_key,)).fetchone()
    return row[0] if row else None


def upsert_document(
    conn: psycopg.Connection, settings: Settings, data: SubjectData, *, corpus: str, book_id: UUID | None
) -> UUID:
    q = sql.SQL(
        "INSERT INTO {a}.documents AS d (document_key, corpus, subject, subject_no, title, source_format, "
        "format_version, book_id, manifest, pages, page_relations) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (document_key) DO UPDATE SET corpus = EXCLUDED.corpus, subject = EXCLUDED.subject, "
        "subject_no = EXCLUDED.subject_no, title = EXCLUDED.title, source_format = EXCLUDED.source_format, "
        "format_version = EXCLUDED.format_version, book_id = coalesce(EXCLUDED.book_id, d.book_id), "
        "manifest = EXCLUDED.manifest, pages = EXCLUDED.pages, page_relations = EXCLUDED.page_relations, "
        "updated_at = now() RETURNING id"
    ).format(a=_a(settings))
    params = (
        data.document_key, corpus, settings.common_json_subject, data.subject_no, data.title, data.source_format,
        data.format_version, book_id, Jsonb(data.manifest), Jsonb(data.pages), Jsonb(data.page_relations),
    )
    return conn.execute(q, params).fetchone()[0]


def existing_blocks(conn: psycopg.Connection, settings: Settings, block_ids: list[str]) -> dict[str, ExistingBlock]:
    q = sql.SQL(
        "SELECT block_id, content_hash, embedding_text_hash, embedding IS NOT NULL, embedding_model, search_enabled "
        "FROM {a}.blocks WHERE block_id = ANY(%s)"
    ).format(a=_a(settings))
    return {
        r[0]: ExistingBlock(content_hash=r[1], embedding_text_hash=r[2], has_embedding=r[3], embedding_model=r[4],
                            search_enabled=r[5])
        for r in conn.execute(q, (block_ids,)).fetchall()
    }


def document_block_ids(conn: psycopg.Connection, settings: Settings, document_id: UUID) -> set[str]:
    q = sql.SQL("SELECT block_id FROM {a}.blocks WHERE document_id = %s").format(a=_a(settings))
    return {r[0] for r in conn.execute(q, (document_id,)).fetchall()}


_UPSERT_BLOCK = """
INSERT INTO {a}.blocks AS t (
    document_id, block_id, source_id, block_type, block_role, printed_page_number, order_in_page, title,
    title_path, concept_name, raw_text, clean_text, table_data, visual_data, image, crop_s3_key, thumbnail_s3_key,
    duplicate_of_block_id, model_generated, confidence, review, needs_review, source, search_enabled,
    search_excluded_reason, embedding_text, embedding_text_hash, embedding, embedding_model, content_hash,
    processing_run_id, source_clean_text_hash)
VALUES (
    %(document_id)s, %(block_id)s, %(source_id)s, %(block_type)s, %(block_role)s, %(printed_page_number)s,
    %(order_in_page)s, %(title)s, %(title_path)s, %(concept_name)s, %(raw_text)s, %(clean_text)s, %(table_data)s,
    %(visual_data)s, %(image)s, %(crop_s3_key)s, %(thumbnail_s3_key)s, %(duplicate_of_block_id)s,
    %(model_generated)s, %(confidence)s, %(review)s, %(needs_review)s, %(source)s, %(search_enabled)s,
    %(search_excluded_reason)s, %(embedding_text)s, %(embedding_text_hash)s, %(embedding)s::public.vector,
    %(embedding_model)s, %(content_hash)s, %(processing_run_id)s, %(source_clean_text_hash)s)
ON CONFLICT (block_id) DO UPDATE SET
    document_id = EXCLUDED.document_id, source_id = EXCLUDED.source_id, block_type = EXCLUDED.block_type,
    block_role = EXCLUDED.block_role, printed_page_number = EXCLUDED.printed_page_number,
    order_in_page = EXCLUDED.order_in_page, title = EXCLUDED.title, title_path = EXCLUDED.title_path,
    concept_name = EXCLUDED.concept_name, raw_text = EXCLUDED.raw_text, clean_text = EXCLUDED.clean_text,
    table_data = EXCLUDED.table_data, visual_data = EXCLUDED.visual_data, image = EXCLUDED.image,
    crop_s3_key = EXCLUDED.crop_s3_key, thumbnail_s3_key = EXCLUDED.thumbnail_s3_key,
    duplicate_of_block_id = EXCLUDED.duplicate_of_block_id, model_generated = EXCLUDED.model_generated,
    confidence = EXCLUDED.confidence, review = EXCLUDED.review, needs_review = EXCLUDED.needs_review,
    source = EXCLUDED.source, search_enabled = EXCLUDED.search_enabled,
    search_excluded_reason = EXCLUDED.search_excluded_reason, embedding_text = EXCLUDED.embedding_text,
    embedding_text_hash = EXCLUDED.embedding_text_hash,
    embedding = CASE WHEN %(overwrite_embedding)s THEN EXCLUDED.embedding ELSE t.embedding END,
    embedding_model = CASE WHEN %(overwrite_embedding)s THEN EXCLUDED.embedding_model ELSE t.embedding_model END,
    content_hash = EXCLUDED.content_hash, processing_run_id = EXCLUDED.processing_run_id,
    source_clean_text_hash = EXCLUDED.source_clean_text_hash, updated_at = now()
"""


def upsert_blocks(
    conn: psycopg.Connection,
    settings: Settings,
    document_id: UUID,
    run_id: UUID | None,
    plans: list[BlockPlan],
    vectors: dict[str, str],
    model: str,
) -> int:
    """바뀐 블록(new/changed)만 upsert한다. vectors는 block_id → pgvector 텍스트(이번에 계산한 것만).

    임베딩은 계산했으면 덮어쓰고, 검색 제외면 지우고, 그 밖에는 기존 값을 둔다.
    """
    params = []
    for p in plans:
        if p.status == "unchanged":
            continue
        r = p.record
        vec = vectors.get(r.block_id) if p.embed else None
        if p.embed and vec is None:
            raise ValueError(f"{r.block_id}: 임베딩이 계산되지 않음")
        params.append({
            "document_id": document_id, "block_id": r.block_id, "source_id": r.source_id,
            "block_type": r.block_type, "block_role": r.block_role, "printed_page_number": r.printed_page_number,
            "order_in_page": r.order_in_page, "title": r.title, "title_path": Jsonb(r.title_path),
            "concept_name": r.concept_name, "raw_text": Jsonb(r.raw_text), "clean_text": r.clean_text,
            "table_data": Jsonb(r.table_data) if r.table_data is not None else None,
            "visual_data": Jsonb(r.visual_data) if r.visual_data is not None else None,
            "image": Jsonb(r.image) if r.image is not None else None,
            "crop_s3_key": r.crop_s3_key, "thumbnail_s3_key": r.thumbnail_s3_key,
            "duplicate_of_block_id": r.duplicate_of_block_id, "model_generated": Jsonb(r.model_generated),
            "confidence": r.confidence, "review": Jsonb(r.review), "needs_review": r.needs_review,
            "source": Jsonb(r.source), "search_enabled": r.search_enabled,
            "search_excluded_reason": r.search_excluded_reason, "embedding_text": r.embedding_text,
            "embedding_text_hash": r.embedding_text_hash, "embedding": vec,
            "embedding_model": model if p.embed else None, "content_hash": r.content_hash,
            "processing_run_id": run_id, "source_clean_text_hash": r.source_clean_text_hash,
            "overwrite_embedding": p.embed or p.clear_embedding,
        })
    if params:
        with conn.cursor() as cur:
            cur.executemany(sql.SQL(_UPSERT_BLOCK).format(a=_a(settings)), params)
    return len(params)


def replace_relations(
    conn: psycopg.Connection, settings: Settings, document_id: UUID, relations: list[RelationRecord]
) -> int:
    """문서의 관계를 파일과 똑같이 맞춘다(전부 지우고 다시 넣음)."""
    conn.execute(sql.SQL("DELETE FROM {a}.block_relations WHERE document_id = %s").format(a=_a(settings)),
                 (document_id,))
    if relations:
        q = sql.SQL(
            "INSERT INTO {a}.block_relations (document_id, relationship_id, from_block_id, to_block_id, from_page, "
            "to_page, link_type, relation_types, relation_source, relation_scope, confidence, reason) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        ).format(a=_a(settings))
        with conn.cursor() as cur:
            cur.executemany(q, [
                (document_id, r.relationship_id, r.from_block_id, r.to_block_id, r.from_page, r.to_page,
                 r.link_type, Jsonb(r.relation_types), r.relation_source, r.relation_scope, r.confidence, r.reason)
                for r in relations
            ])
    return len(relations)


def delete_blocks(conn: psycopg.Connection, settings: Settings, document_id: UUID, block_ids: list[str]) -> int:
    """파일에서 빠진 블록 삭제(--prune). 그 블록의 관계도 FK CASCADE로 지워진다."""
    if not block_ids:
        return 0
    q = sql.SQL("DELETE FROM {a}.blocks WHERE document_id = %s AND block_id = ANY(%s)").format(a=_a(settings))
    return conn.execute(q, (document_id, block_ids)).rowcount


def count_document(conn: psycopg.Connection, settings: Settings, document_id: UUID) -> dict:
    q = sql.SQL(
        "SELECT (SELECT count(*) FROM {a}.blocks WHERE document_id = %s), "
        "(SELECT count(*) FROM {a}.blocks WHERE document_id = %s AND embedding IS NOT NULL), "
        "(SELECT count(*) FROM {a}.block_relations WHERE document_id = %s)"
    ).format(a=_a(settings))
    blocks, embedded, relations = conn.execute(q, (document_id, document_id, document_id)).fetchone()
    return {"blocks": blocks, "embedded": embedded, "relations": relations}


def delete_document(conn: psycopg.Connection, settings: Settings, document_id: UUID) -> int:
    """문서 삭제. 블록·관계는 CASCADE로 함께 지워진다."""
    q = sql.SQL("DELETE FROM {a}.documents WHERE id = %s").format(a=_a(settings))
    return conn.execute(q, (document_id,)).rowcount
