"""근거에 연결된 그림·표(related_visuals, D-JW-008). 거르기·붙이기는 DB 없이, 조회 SQL은 공유 DB(관계가 없으면 건너뜀)."""

from uuid import uuid4

import numpy as np
import psycopg
import pytest
from psycopg import sql

from app.qa import related_visuals, service
from app.qa.related_visuals import add_related_visuals, attach
from app.qa.service import QaModels, answer_question
from app.repositories import related_visuals as related_repo


@pytest.fixture
def rv_settings(settings):
    return settings.model_copy(update={"asset_url_template": "https://cdn.test/{key}",
                                       "related_visual_min_confidence": 0.7, "related_visual_max": 2})


def _rel(src, bid, conf, kind="visual", thumb=True, crop=True):
    return {"source_block_id": src, "block_id": bid, "block_type": kind, "title": f"{bid} 제목", "confidence": conf,
            "thumbnail_s3_key": f"t/{bid}.jpg" if thumb else None, "crop_s3_key": f"c/{bid}.jpg" if crop else None}


def _ev(n, kind="theory", block_id=None):
    return {"n": n, "kind": kind, "block_id": block_id}


def test_attach_filters_and_orders(rv_settings):
    ev = [_ev(1, block_id="S1:THEORY:A"), _ev(2, block_id="S1:THEORY:B"), _ev(3, "visual", "S1:VISUAL:IN"), _ev(4)]
    rows = [
        _rel("S1:THEORY:A", "S1:VISUAL:LOW", 0.69),               # 신뢰도 미만
        _rel("S1:THEORY:A", "S1:VISUAL:IN", 0.99),                # 이미 근거에 있음
        _rel("S1:THEORY:A", "S1:TABLE:T1", 0.8, kind="table"),
        _rel("S1:THEORY:A", "S1:VISUAL:V1", 0.95),
        _rel("S1:THEORY:A", "S1:VISUAL:V1", 0.75),                # 양방향 중복
        _rel("S1:THEORY:A", "S1:VISUAL:V2", 0.8),                 # 최대 2개라 잘림(같은 신뢰도면 block_id 순)
        _rel("S1:THEORY:B", "S1:VISUAL:NOKEY", 0.9, thumb=False, crop=False),  # 이미지 키 없음
        _rel("S1:THEORY:B", "S1:VISUAL:THUMB", 0.9, crop=False),  # 원본 없으면 썸네일로
        _rel("S1:THEORY:B", "S1:VISUAL:ONLYCONF", None),
    ]
    attach(ev, rows, rv_settings)
    assert [v["block_id"] for v in ev[0]["related_visuals"]] == ["S1:VISUAL:V1", "S1:TABLE:T1"]
    assert ev[0]["related_visuals"][0] == {"block_id": "S1:VISUAL:V1", "kind": "visual", "title": "S1:VISUAL:V1 제목",
                                          "thumbnail_url": "https://cdn.test/t/S1:VISUAL:V1.jpg",
                                          "image_url": "https://cdn.test/c/S1:VISUAL:V1.jpg"}
    assert ev[1]["related_visuals"] == [{"block_id": "S1:VISUAL:THUMB", "kind": "visual", "title": "S1:VISUAL:THUMB 제목",
                                         "thumbnail_url": "https://cdn.test/t/S1:VISUAL:THUMB.jpg",
                                         "image_url": "https://cdn.test/t/S1:VISUAL:THUMB.jpg"}]
    assert ev[2]["related_visuals"] == [] and ev[3]["related_visuals"] == []  # 그림 근거·team_text 근거는 []


def test_attach_without_asset_template_is_empty(rv_settings):
    ev = [_ev(1, block_id="S1:THEORY:A")]
    attach(ev, [_rel("S1:THEORY:A", "S1:VISUAL:V1", 0.9)], rv_settings.model_copy(update={"asset_url_template": ""}))
    assert ev[0]["related_visuals"] == []


def test_add_related_visuals_one_query_and_failures(rv_settings, monkeypatch):
    calls = []
    monkeypatch.setattr(related_repo, "fetch", lambda conn, s, ids: calls.append(ids) or [_rel(ids[0], "S1:VISUAL:V", 0.9)])
    ev = [_ev(1, block_id="S1:THEORY:B"), _ev(2, block_id="S1:THEORY:A"), _ev(3, block_id="S1:THEORY:A"), _ev(4)]
    add_related_visuals(object(), rv_settings, ev)
    assert calls == [["S1:THEORY:A", "S1:THEORY:B"]]  # 근거 K개를 한 번에(중복 제거)
    assert ev[1]["related_visuals"][0]["block_id"] == "S1:VISUAL:V" and ev[3]["related_visuals"] == []

    ev = [_ev(1)]  # 이론 블록 근거가 없으면 조회하지 않음
    add_related_visuals(object(), rv_settings, ev)
    assert len(calls) == 1 and ev[0]["related_visuals"] == []

    def boom(conn, s, ids):
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(related_repo, "fetch", boom)
    ev = [_ev(1, block_id="S1:THEORY:A")]
    add_related_visuals(object(), rv_settings, ev)  # 실패해도 예외 없이 []
    assert ev[0]["related_visuals"] == []
    ev = [_ev(1, block_id="S1:THEORY:A")]
    add_related_visuals(object(), rv_settings.model_copy(update={"related_visual_max": 0}), ev)  # 0이면 끔
    assert ev[0]["related_visuals"] == []


class _Embedder:
    def encode(self, texts):
        return np.zeros((len(texts), 4), dtype=np.float32)


def _block_row(i, block_id):
    return {"id": uuid4(), "book_title": "1과목", "printed_page_number": str(60 + i), "path": "장 > 절",
            "clean_text": f"본문{i}", "raw_text": f"원문{i}", "score": 0.9 - i * 0.01, "corpus": "common_json",
            "kind": "theory", "block_id": block_id, "title": f"제목{i}", "title_path": ["장", "절"],
            "document_title": "1과목", "thumbnail_url": None, "image_url": None}


def test_qa_response_and_log_have_related_visuals(rv_settings, monkeypatch):
    rows = [_block_row(1, "S1:THEORY:A"), _block_row(2, "S1:THEORY:B")]
    monkeypatch.setattr(service, "search_candidates", lambda conn, s, vec, n, corpus=None, **kw: rows[:n])
    monkeypatch.setattr(related_repo, "fetch", lambda conn, s, ids: [_rel("S1:THEORY:A", "S1:TABLE:T", 0.9, "table")])
    logged = []
    monkeypatch.setattr(service, "insert_query_log", lambda conn, settings, **kw: logged.append(kw) or uuid4())
    s = rv_settings.model_copy(update={"search_top_k": 2, "judge_provider": "none"})
    r = answer_question(object(), s, QaModels(_Embedder(), None, None, None), "질문")
    assert [len(e["related_visuals"]) for e in r["evidence"]] == [1, 0]
    assert r["evidence"][0]["related_visuals"][0]["image_url"] == "https://cdn.test/c/S1:TABLE:T.jpg"
    assert "visuals_ms" in r["timings_ms"]
    assert [e["related_visual_ids"] for e in logged[-1]["metadata"]["evidence"]] == [["S1:TABLE:T"], []]


def test_fetch_from_db(db_conn, settings):
    """공유 DB의 실제 관계 1개로 SQL 확인(양방향 중 이론 쪽 block_id로 조회)."""
    a = sql.Identifier(settings.db_app_schema)
    try:
        row = db_conn.execute(sql.SQL(
            "SELECT r.from_block_id, r.to_block_id, f.block_type, t.block_type FROM {a}.block_relations r "
            "JOIN {a}.blocks f ON f.block_id = r.from_block_id JOIN {a}.blocks t ON t.block_id = r.to_block_id "
            "WHERE r.link_type = ANY(%s) ORDER BY r.relationship_id LIMIT 1").format(a=a),
            (related_repo.LINK_TYPES,)).fetchone()
    except psycopg.errors.UndefinedTable:
        pytest.skip("block_relations 없음")
    if row is None:
        pytest.skip("이론↔그림·표 관계 없음(공통 JSON 미적재)")
    frm, to, ftype, ttype = row
    theory, other = (frm, to) if ftype == "theory" else (to, frm)
    got = related_repo.fetch(db_conn, settings, [theory])
    assert any(g["block_id"] == other and g["source_block_id"] == theory for g in got)
    assert all(g["block_type"] in ("visual", "table") for g in got)
