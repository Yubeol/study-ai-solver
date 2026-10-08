"""이론 블록 수정 API (/block-corrections, /blocks/{block_id}, D-JW-007).

- 요청 검증은 DB 없이 돈다.
- 흐름 테스트는 공유 DB + 005가 필요하다. 테스트 전용 문서·블록(검색 제외)을 만들고 끝나면 지운다.
  임베딩은 가짜(1024차원 고정 벡터)라 모델 없이 돈다.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from app.api.deps import get_conn
from app.core.text_hash import clean_text_hash
from app.main import create_app


class _FakeEmbedder:
    def __init__(self):
        self.texts = []

    def encode(self, texts):
        self.texts.extend(texts)
        return np.full((len(texts), 1024), 1 / 32, dtype=np.float32)


# ---- DB 없이 ----

@pytest.mark.parametrize("body", [
    {"block_id": "S1:THEORY:X", "new_clean_text": "가" * 2001},
    {"new_clean_text": "내용"},
    {"block_id": "S1:THEORY:X", "new_clean_text": "내용", "reason": "가" * 501},
])
def test_correction_validation(body):
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: None
    with TestClient(app) as client:
        assert client.post("/block-corrections", json=body).status_code == 422
        assert client.get("/block-corrections", params={"status": "nope"}).status_code == 422


@pytest.mark.parametrize("text", ["", "   ", " \t\n \r\n"])
def test_blank_correction_is_400(text):
    """공백·탭·줄바꿈뿐이면 DB를 보기 전에 400(민규 요청)."""
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: None
    with TestClient(app) as client:
        assert client.post("/block-corrections", json={"block_id": "S1:THEORY:X", "new_clean_text": text}).status_code == 400


def test_approve_without_embedder_is_503():
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: None
    with TestClient(app) as client:
        assert client.post(f"/block-corrections/{uuid4()}/approve", json={}).status_code == 503


# ---- 공유 DB + 005 ----

@pytest.fixture
def test_blocks(db_conn, settings):
    """검색 제외(search_enabled=false)인 테스트 문서 1개 + 이론·표 블록. 끝나면 수정안·신고·문서(블록 CASCADE)를 지운다."""
    if db_conn.execute("SELECT to_regclass(%s)", (f"{settings.db_app_schema}.block_corrections",)).fetchone()[0] is None:
        pytest.skip("block_corrections 테이블 없음(005 마이그레이션 미적용)")
    a = sql.Identifier(settings.db_app_schema)
    tag = uuid4().hex[:8]
    theory_id, table_id = f"PYTEST{tag}:THEORY:TH_1_01", f"PYTEST{tag}:TABLE:TAB_1_01"
    original = "지니 지수는 1에서 각 범주 비율의 제곱합을 뺀 값이다."
    with db_conn.transaction():
        doc_id = db_conn.execute(sql.SQL(
            "INSERT INTO {}.documents (document_key, corpus, subject, title) VALUES (%s, 'pytest', 'ADsP', %s) "
            "RETURNING id").format(a), (f"pytest:{tag}", f"pytest 문서 {tag}")).fetchone()[0]
        ins = sql.SQL(
            "INSERT INTO {}.blocks (document_id, block_id, source_id, block_type, printed_page_number, title, title_path, "
            "raw_text, clean_text, content_hash, search_enabled, search_excluded_reason, source_clean_text_hash) "
            "VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, 'pytest', false, 'pytest', %s)").format(a)
        db_conn.execute(ins, (doc_id, theory_id, "TH_1_01", "theory", "지니 지수", Jsonb(["3장", "지니 지수"]),
                              Jsonb(original), original, clean_text_hash(original)))
        db_conn.execute(ins, (doc_id, table_id, "TAB_1_01", "table", "표", Jsonb(["3장", "표"]), Jsonb(["a"]), None, None))
    created_reports: list[UUID] = []
    yield SimpleNamespace(theory=theory_id, table=table_id, original=original, reports=created_reports, a=a)
    with db_conn.transaction():
        db_conn.execute(sql.SQL("DELETE FROM {}.block_corrections WHERE block_id = ANY(%s)").format(a),
                        ([theory_id, table_id],))
        if created_reports:
            db_conn.execute(sql.SQL("DELETE FROM {}.answer_reports WHERE id = ANY(%s)").format(a), (created_reports,))
        db_conn.execute(sql.SQL("DELETE FROM {}.documents WHERE id = %s").format(a), (doc_id,))


def _block(db_conn, t, block_id):
    return db_conn.execute(sql.SQL(
        "SELECT clean_text, embedding_text, embedding_text_hash, embedding IS NOT NULL, embedding_model, "
        "source_clean_text_hash FROM {}.blocks WHERE block_id = %s").format(t.a), (block_id,)).fetchone()


def test_correction_flow(test_blocks, db_conn, settings):
    t = test_blocks
    embedder = _FakeEmbedder()
    app = create_app()
    with TestClient(app) as client:
        app.state.qa_models = SimpleNamespace(embedder=embedder, llm=None, judge=None)

        view = client.get(f"/blocks/{t.theory}").json()
        assert view["editable"] is True and view["clean_text"] == t.original and view["path"] == "3장 > 지니 지수"
        assert client.get(f"/blocks/{t.table}").json()["editable"] is False
        assert client.get("/blocks/NOPE:THEORY:X").status_code == 404

        # 표·없는 블록·같은 내용은 거절
        assert client.post("/block-corrections", json={"block_id": t.table, "new_clean_text": "x"}).status_code == 400
        assert client.post("/block-corrections", json={"block_id": "NOPE:THEORY:X", "new_clean_text": "x"}).status_code == 404
        assert client.post("/block-corrections", json={"block_id": t.theory, "new_clean_text": f" {t.original} "}).status_code == 400

        # 신고에서 나온 수정안 → 승인하면 블록 수정 + 재임베딩 + 신고 resolved
        rep = client.post("/answer-reports", json={"question": "pytest 수정 신고", "type": "wrong_concept"}).json()
        t.reports.append(UUID(rep["id"]))
        fixed = "지니 지수는 1에서 각 범주 비율의 제곱합을 뺀 값이다. 값이 클수록 불순도가 높다."
        r = client.post("/block-corrections", json={"block_id": t.theory, "new_clean_text": f"  {fixed}\n",
                                                    "reason": "설명 보충", "report_id": rep["id"]})
        assert r.status_code == 201, r.text
        c1 = r.json()
        assert (c1["status"], c1["base_clean_text"], c1["new_clean_text"]) == ("proposed", t.original, fixed)
        assert c1["base_clean_text_hash"] == clean_text_hash(t.original)
        assert _block(db_conn, t, t.theory)[0] == t.original  # 등록만으로는 안 바뀜
        assert [x["id"] for x in client.get("/block-corrections", params={"block_id": t.theory}).json()] == [c1["id"]]

        r = client.post(f"/block-corrections/{c1['id']}/approve", json={"reviewed_by": "pytest", "review_note": "확인"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "applied" and r.json()["applied_at"] is not None
        clean, emb_text, emb_hash, has_emb, model, src_hash = _block(db_conn, t, t.theory)
        assert clean == fixed and emb_text == f"3장 > 지니 지수\n\n{fixed}" and embedder.texts == [emb_text]
        assert has_emb and model == settings.embedding_model and len(emb_hash) == 64
        assert src_hash == clean_text_hash(t.original)  # JSON 원문 해시는 그대로
        report = next(x for x in client.get("/answer-reports", params={"limit": 200}).json() if x["id"] == rep["id"])
        assert (report["status"], report["resolution"], report["reviewed_by"]) == ("resolved", "block_corrected", "pytest")
        assert client.post(f"/block-corrections/{c1['id']}/approve", json={}).status_code == 409  # 이미 처리됨
        assert client.get(f"/blocks/{t.theory}").json()["active_correction_id"] == c1["id"]

        # 새 수정 승인 → 이전 applied는 superseded (base는 지금 DB 값, 해시는 원문 그대로)
        c2 = client.post("/block-corrections", json={"block_id": t.theory, "new_clean_text": fixed + " (2차)"}).json()
        assert c2["base_clean_text"] == fixed and c2["base_clean_text_hash"] == clean_text_hash(t.original)
        assert client.post(f"/block-corrections/{c2['id']}/approve", json={}).json()["status"] == "applied"
        statuses = {x["id"]: x["status"] for x in client.get("/block-corrections", params={"block_id": t.theory}).json()}
        assert statuses == {c1["id"]: "superseded", c2["id"]: "applied"}

        # 반려·철회는 proposed만, 블록은 그대로
        c3 = client.post("/block-corrections", json={"block_id": t.theory, "new_clean_text": "반려될 내용"}).json()
        assert client.post(f"/block-corrections/{c3['id']}/reject", json={"review_note": "근거 없음"}).json()["status"] == "rejected"
        assert client.post(f"/block-corrections/{c3['id']}/withdraw", json={}).status_code == 409
        c4 = client.post("/block-corrections", json={"block_id": t.theory, "new_clean_text": "철회될 내용"}).json()
        assert client.post(f"/block-corrections/{c4['id']}/withdraw", json={}).json()["status"] == "withdrawn"
        assert _block(db_conn, t, t.theory)[0] == fixed + " (2차)"

        # 원문이 바뀌었으면(재적재) 승인 시 stale + 409, 블록은 그대로
        c5 = client.post("/block-corrections", json={"block_id": t.theory, "new_clean_text": "낡은 수정"}).json()
        db_conn.execute(sql.SQL("UPDATE {}.blocks SET source_clean_text_hash = 'changed' WHERE block_id = %s").format(t.a),
                        (t.theory,))
        assert client.post(f"/block-corrections/{c5['id']}/approve", json={}).status_code == 409
        assert client.get("/block-corrections", params={"status": "stale", "block_id": t.theory}).json()[0]["id"] == c5["id"]
        assert _block(db_conn, t, t.theory)[0] == fixed + " (2차)"
        assert client.post(f"/block-corrections/{uuid4()}/reject", json={}).status_code == 404
