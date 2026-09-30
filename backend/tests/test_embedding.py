"""embed 단계와 벡터 검색 (D-020). 기본은 가짜 임베더, 실제 모델은 `uv run pytest -m embedding_model`."""

import hashlib

import numpy as np
import pytest
from psycopg import sql

from app.ingestion import embedding
from app.ingestion.pipeline import Stage, process_page
from app.ingestion.stages import chunk_theory, embed
from app.retrieval.search import search_theory
from tests.test_chunking import _ctx, team_text_book  # noqa: F401  (fixture 재사용)


class FakeEmbedder:
    dim = 1024

    def encode(self, texts):
        out = []
        for t in texts:
            seed = int.from_bytes(hashlib.sha256(t.encode("utf-8")).digest()[:8], "little")
            v = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            out.append(v / np.linalg.norm(v))
        return np.stack(out)


@pytest.fixture
def fake_embedder(monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr(embedding, "get_embedder", lambda settings: fake)
    return fake


def test_embed_stage_saves_normalized_vectors_and_search(db_conn, settings, team_text_book, fake_embedder):
    book, page_ids, run_id, storage = team_text_book
    stage_list = (Stage("chunk_theory", chunk_theory, "VERIFIED"), Stage("embed", embed, "EMBEDDED"))
    for pid in page_ids:
        assert process_page(_ctx(db_conn, settings, book, pid, run_id, storage), stage_list) == "DONE"

    s = sql.Identifier(settings.db_schema)
    rows = db_conn.execute(
        sql.SQL(
            "SELECT t.id, t.embedding_text, t.embedding IS NOT NULL, t.embedding_enabled, t.needs_review, "
            "  vector_norm(t.embedding) FROM {s}.theory_chunks t JOIN {s}.pages p ON p.id = t.page_id "
            "WHERE p.book_id = %s"
        ).format(s=s),
        (book["id"],),
    ).fetchall()
    assert rows and all(r[2] and r[3] and not r[4] for r in rows)
    assert all(abs(r[5] - 1.0) < 1e-4 for r in rows)
    statuses = db_conn.execute(
        sql.SQL("SELECT DISTINCT processing_status FROM {s}.pages WHERE book_id = %s").format(s=s), (book["id"],)
    ).fetchall()
    assert statuses == [("EMBEDDED",)]

    # 청크 하나의 embedding_text로 질문하면 그 청크가 1등(v_searchable_theory 조건으로 검색)
    target_id, target_text = rows[0][0], rows[0][1]
    vec = embedding.to_pgvector(fake_embedder.encode([target_text])[0])
    hits = search_theory(db_conn, settings, vec, 3)
    assert hits[0]["id"] == target_id and hits[0]["score"] > 0.999


def test_needs_review_chunk_is_not_embedded(db_conn, settings, team_text_book, fake_embedder):
    book, page_ids, run_id, storage = team_text_book
    stage_list = (Stage("chunk_theory", chunk_theory, "VERIFIED"),)
    process_page(_ctx(db_conn, settings, book, page_ids[0], run_id, storage), stage_list)
    s = sql.Identifier(settings.db_schema)
    db_conn.execute(
        sql.SQL("UPDATE {s}.theory_chunks SET needs_review = true WHERE page_id = %s AND sort_order = 0").format(s=s),
        (page_ids[0],),
    )
    embed(_ctx(db_conn, settings, book, page_ids[0], run_id, storage))
    rows = db_conn.execute(
        sql.SQL("SELECT sort_order, embedding IS NOT NULL, needs_review FROM {s}.theory_chunks WHERE page_id = %s ORDER BY 1").format(s=s),
        (page_ids[0],),
    ).fetchall()
    assert rows[0] == (0, False, True)
    assert all(r[1] and not r[2] for r in rows[1:])


@pytest.mark.embedding_model
def test_real_bge_m3(settings):
    emb = embedding.get_embedder(settings)
    v = emb.encode(["데이터는 객관적 사실이다.", "DIKW 피라미드"])
    assert v.shape == (2, settings.embedding_dim)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
