"""검색 대상 전환(SEARCH_CORPUS, D-M-033)과 사용자 보충 합치기(D-M-035).
행 모양 맞추기·합치기는 DB 없이, 실제 검색은 로컬 DB로."""

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
    search_supplements,
    search_theory,
    supplement_embedding_text,
    supplement_row,
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
    r = block_row(_with_template(settings, ""), _block("visual", raw_text=["가", "나"], clean_text=None,
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
    monkeypatch.setattr(search, "search_supplements", lambda *a, **k: [])

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
    monkeypatch.setattr(search, "search_supplements", lambda *a, **k: [])
    s = settings.model_copy(update={"search_corpus": "team_text"})
    assert search_candidates(None, s, "[0]", 3) == []


# ----- 사용자 보충(D-M-035) -----

def _supp(score, **kw):
    r = {"id": uuid4(), "title": "보충 제목", "subject": None, "content_text": "보충 본문",
         "embedding_text": "보충 제목\n\n보충 본문", "score": score}
    r.update(kw)
    return r


def test_supplement_row_and_embedding_text():
    r = supplement_row(_supp(0.5))
    assert (r["kind"], r["corpus"], r["block_id"], r["book_id"]) == ("supplement", "supplement", None, None)
    assert r["raw_text"] == r["clean_text"] == "보충 본문"
    assert (r["path"], r["title_path"], r["printed_page_number"]) == ("보충 제목", ["보충 제목"], None)
    assert r["book_title"] == r["document_title"] == "사용자 보충"
    assert supplement_row(_supp(0.5, title=""))["title_path"] == []
    assert supplement_embedding_text("제목", "본문") == "제목\n\n본문"
    assert supplement_embedding_text("", "본문") == "본문"


@pytest.mark.parametrize("corpus", ["team_text", "common_json", "mixed"])
def test_search_candidates_merges_supplements(settings, monkeypatch, corpus):
    """검색 대상과 상관없이 보충 n개를 합쳐 cosine 점수 상위 n개(같은 점수는 교재 먼저)."""
    calls = {}
    monkeypatch.setattr(search, "search_theory", lambda *a, **k: [
        {"id": uuid4(), "title": "청크", "book_title": "책3", "book_id": BOOK3, "title_path": [], "score": 0.6}])
    monkeypatch.setattr(search, "search_blocks", lambda *a, **k: [_block("theory", score=0.5)])
    monkeypatch.setattr(search, "common_json_book_ids", lambda conn, s: {BOOK1})

    def fake_supp(conn, s, vec, n):
        calls["supp"] = n
        return [_supp(0.7), _supp(0.5)]

    monkeypatch.setattr(search, "search_supplements", fake_supp)
    rows = search_candidates(None, settings, "[0]", 3, corpus)
    assert calls["supp"] == 3
    assert rows[0]["corpus"] == "supplement" and len(rows) == 3
    assert candidate_sources(rows)["supplement"] >= 1
    if corpus == "common_json":  # 0.5 동점: 교재 블록이 보충보다 먼저
        assert [r["corpus"] for r in rows] == ["supplement", "common_json", "supplement"]


def test_search_candidates_book_scope_skips_supplements(settings, monkeypatch):
    """book 범위(평가 --subjects)를 주면 보충은 어느 book에도 속하지 않으므로 넣지 않는다."""
    monkeypatch.setattr(search, "search_theory", lambda *a, **k: [])
    monkeypatch.setattr(search, "search_supplements", lambda *a, **k: pytest.fail("보충 검색 안 함"))
    assert search_candidates(None, settings, "[0]", 3, "team_text", book_ids=[BOOK3]) == []


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


def _unit_vector(dim: int, i: int) -> str:
    return "[" + ",".join("1" if j == i else "0" for j in range(dim)) + "]"


def test_db_search_supplements_status_filter(db_conn, settings):
    """보충 검색: rejected와 벡터 없는 행(파일 보충)은 빠진다. 테스트 행은 끝나면 지운다."""
    if db_conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = 'supplements' "
                       "AND column_name = 'embedding'", (settings.db_app_schema,)).fetchone() is None:
        pytest.skip("supplements.embedding 없음(006 미적용)")
    a = sql.Identifier(settings.db_app_schema)
    vec = _unit_vector(settings.embedding_dim, 7)
    ok, rejected, no_vec = uuid4(), uuid4(), uuid4()
    try:
        with db_conn.transaction():
            for sid, st, v in ((ok, "pending_review", vec), (rejected, "rejected", vec), (no_vec, "pending_review", None)):
                db_conn.execute(sql.SQL(
                    "INSERT INTO {}.supplements (id, source, kind, title, content_text, status, embedding_text, embedding) "
                    "VALUES (%s, 'unanswerable', 'text', 'pytest 보충', 'pytest 본문', %s, 'pytest', %s::public.vector)"
                ).format(a), (sid, st, v))
        ids = [r["id"] for r in search_supplements(db_conn, settings, vec, 50)]
        assert ok in ids and rejected not in ids and no_vec not in ids
        top = supplement_row(search_supplements(db_conn, settings, vec, 1)[0])
        assert top["id"] == ok and top["score"] == pytest.approx(1, abs=1e-4)
    finally:
        with db_conn.transaction():
            db_conn.execute(sql.SQL("DELETE FROM {}.supplements WHERE id = ANY(%s)").format(a), ([ok, rejected, no_vec],))


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
