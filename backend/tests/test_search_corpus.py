"""검색 대상 전환(SEARCH_CORPUS, D-M-033). 행 모양 맞추기·mixed 합치기는 DB 없이, 실제 검색은 로컬 DB로."""

from uuid import uuid4

import pytest
from psycopg import sql

from app.retrieval import search
from app.retrieval.search import (
    block_row,
    candidate_sources,
    merge_candidates,
    search_blocks,
    search_candidates,
    search_theory,
    theory_row,
)

BOOK1, BOOK3 = uuid4(), uuid4()


def _block(block_type, **kw):
    r = {"id": uuid4(), "block_id": f"S1:{block_type.upper()}:X", "block_type": block_type, "title": "가짜 제목",
         "title_path": ["1장 가짜", "가짜 제목"], "raw_text": "이론 원문", "clean_text": "이론 본문",
         "table_data": None, "visual_data": None, "embedding_text": "임베딩", "thumbnail_s3_key": None,
         "crop_s3_key": None, "printed_page_number": 15, "book_id": BOOK1, "book_title": "가짜 책",
         "document_title": "1과목 가짜", "score": 0.5}
    r.update(kw)
    return r


def _with_template(settings, template):
    return settings.model_copy(update={"asset_url_template": template})


# ----- 행 모양 -----

def test_block_row_theory(settings):
    r = block_row(settings, _block("theory"))
    assert r["kind"] == "theory" and r["corpus"] == "common_json" and r["block_id"] == "S1:THEORY:X"
    assert r["clean_text"] == "이론 본문"  # 제목 경로 없이 본문만
    assert r["raw_text"] == "이론 원문"
    assert r["path"] == "1장 가짜 > 가짜 제목" and r["title_path"] == ["1장 가짜", "가짜 제목"]
    assert r["printed_page_number"] == "15"  # 이론 청크(pages.printed_page_number text)와 같게 문자열
    assert r["thumbnail_url"] is None and r["image_url"] is None


def test_block_row_table_and_urls(settings):
    s = _with_template(settings, "https://cdn.example/{key}")
    r = block_row(s, _block("table", raw_text=["칸1", "칸2"], clean_text=None,
                            table_data={"headers": [], "rows": [["행가", "값"]]},
                            thumbnail_s3_key="t/a.jpg", crop_s3_key="c/a.jpg"))
    assert r["kind"] == "table"
    assert r["clean_text"] == "[표] 가짜 제목\n- 행가: 값"
    assert r["raw_text"] == "칸1\n칸2"  # 원문 목록을 줄바꿈으로 잇기만
    assert r["thumbnail_url"] == "https://cdn.example/t/a.jpg" and r["image_url"] == "https://cdn.example/c/a.jpg"


def test_block_row_visual(settings):
    r = block_row(settings, _block("visual", raw_text=["가", "나"], clean_text=None,
                                   visual_data={"visual_description": "설명 문장", "visual_structure": "2칸",
                                                "related_theory_context": "넣지 않음"},
                                   thumbnail_s3_key="t/v.jpg"))
    assert r["clean_text"] == "[그림] 가짜 제목\n설명: 설명 문장\n구조: 2칸\n그림 속 글자: 가 · 나"
    assert r["thumbnail_url"] is None  # 틀이 비면 URL 없음


def test_theory_row_adds_common_fields():
    r = theory_row({"id": uuid4(), "title": "t", "book_title": "책", "title_path": None, "score": 0.4})
    assert r["kind"] == "theory" and r["corpus"] == "team_text" and r["block_id"] is None
    assert r["title_path"] == [] and r["document_title"] == "책" and r["thumbnail_url"] is None


# ----- mixed 합치기 -----

def test_merge_candidates_by_score_then_group_order():
    a = [{"corpus": "team_text", "score": 0.7, "n": 1}, {"corpus": "team_text", "score": 0.5, "n": 2}]
    b = [{"corpus": "common_json", "score": 0.6, "n": 3}, {"corpus": "common_json", "score": 0.5, "n": 4}]
    out = merge_candidates([a, b], 3)
    assert [r["n"] for r in out] == [1, 3, 2]  # 0.5 동점은 앞 그룹 먼저
    assert candidate_sources(out) == {"team_text": 2, "common_json": 1}


def test_search_candidates_routing(settings, monkeypatch):
    calls = {}

    def fake_theory(conn, s, vec, n, *, book_ids=None, exclude_book_ids=None):
        calls["theory"] = (n, book_ids, exclude_book_ids)
        return [{"id": uuid4(), "title": "청크", "book_title": "책3", "book_id": BOOK3, "title_path": [],
                 "score": 0.6}]

    def fake_blocks(conn, s, vec, n, *, book_ids=None):
        calls["blocks"] = (n, book_ids)
        return [_block("theory", score=0.7), _block("theory", score=0.4)]

    monkeypatch.setattr(search, "search_theory", fake_theory)
    monkeypatch.setattr(search, "search_blocks", fake_blocks)
    monkeypatch.setattr(search, "common_json_book_ids", lambda conn, s: {BOOK1})

    rows = search_candidates(None, settings, "[0]", 2, "mixed")
    assert calls["theory"] == (2, None, {BOOK1})  # 공통 JSON이 있는 book은 이론 청크에서 뺀다
    assert calls["blocks"] == (2, None)
    assert [r["corpus"] for r in rows] == ["common_json", "team_text"]

    calls.clear()
    assert [r["corpus"] for r in search_candidates(None, settings, "[0]", 2, "team_text", book_ids=[BOOK3])] == [
        "team_text"]
    assert calls == {"theory": (2, [BOOK3], None)}

    calls.clear()
    assert len(search_candidates(None, settings, "[0]", 2, "common_json")) == 2
    assert calls == {"blocks": (2, None)}

    with pytest.raises(ValueError):
        search_candidates(None, settings, "[0]", 2, "blocks")


def test_search_candidates_uses_setting_by_default(settings, monkeypatch):
    monkeypatch.setattr(search, "search_theory", lambda *a, **k: [])
    monkeypatch.setattr(search, "search_blocks", lambda *a, **k: pytest.fail("블록 검색 안 함"))
    s = settings.model_copy(update={"search_corpus": "team_text"})
    assert search_candidates(None, s, "[0]", 3) == []


# ----- 로컬 DB (CI에서는 건너뜀) -----

def _stored_vector(conn, settings, table_sql: str):
    return conn.execute(sql.SQL(table_sql).format(a=sql.Identifier(settings.db_app_schema),
                                                  s=sql.Identifier(settings.db_schema))).fetchone()


def test_db_search_blocks_finds_itself(db_conn, settings):
    row = _stored_vector(db_conn, settings, "SELECT block_id, embedding::text FROM {a}.v_searchable_blocks "
                                            "ORDER BY block_id LIMIT 1")
    if row is None:
        pytest.skip("검색 대상 블록 없음")
    rows = [block_row(settings, r) for r in search_blocks(db_conn, settings, row[1], 3)]
    assert rows[0]["block_id"] == row[0] and rows[0]["score"] == pytest.approx(1, abs=1e-4)
    assert all(isinstance(r["raw_text"], str) and isinstance(r["printed_page_number"], str) for r in rows)
    assert all(r["clean_text"] for r in rows)  # 표·그림도 LLM용 본문이 비지 않음


def test_db_mixed_excludes_theory_of_common_json_books(db_conn, settings):
    covered = search.common_json_book_ids(db_conn, settings)
    if not covered:
        pytest.skip("공통 JSON 문서 없음")
    # 공통 JSON이 있는 book의 이론 청크 벡터로 검색해도 그 book의 이론 청크는 후보에 없어야 한다
    vec = db_conn.execute(sql.SQL(
        "SELECT t.embedding::text FROM {s}.v_searchable_theory t JOIN {s}.pages p ON p.id = t.page_id "
        "WHERE p.book_id = ANY(%s) LIMIT 1").format(s=sql.Identifier(settings.db_schema)),
        (list(covered),)).fetchone()[0]
    rows = search_candidates(db_conn, settings, vec, 10, "mixed")
    assert len(rows) == 10
    assert not [r for r in rows if r["corpus"] == "team_text" and r["book_id"] in covered]
    assert search_theory(db_conn, settings, vec, 1, book_ids=list(covered))[0]["score"] == pytest.approx(1, abs=1e-4)


def test_db_book_scope_limits_results(db_conn, settings):
    covered = sorted(search.common_json_book_ids(db_conn, settings))
    if not covered:
        pytest.skip("공통 JSON 문서 없음")
    vec = _stored_vector(db_conn, settings, "SELECT embedding::text FROM {a}.v_searchable_blocks LIMIT 1")[0]
    one = covered[:1]
    for corpus in ("team_text", "common_json", "mixed"):
        rows = search_candidates(db_conn, settings, vec, 10, corpus, book_ids=one)
        assert rows and {r["book_id"] for r in rows} == set(one)


def test_db_block_text_rebuilds_stored_embedding_text(db_conn, settings):
    """저장된 블록 전부: 컬럼만으로 만든 embedding_text(with_path=True)가 적재 때 저장한 값과 같다."""
    from psycopg.rows import dict_row

    from app.ingestion.common_json import block_from_row, embedding_text

    with db_conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql.SQL(
            "SELECT block_id, block_type, title, title_path, clean_text, raw_text, table_data, visual_data, source, "
            "embedding_text FROM {a}.blocks").format(a=sql.Identifier(settings.db_app_schema))).fetchall()
    if not rows:
        pytest.skip("블록 없음")
    assert [r["block_id"] for r in rows if embedding_text(block_from_row(r)) != r["embedding_text"]] == []
