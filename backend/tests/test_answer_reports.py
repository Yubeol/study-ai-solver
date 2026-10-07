"""오류 신고(/answer-reports)·보충 이론(/supplements) API.

- 요청 검증·근거 스냅샷 조립은 DB 없이 돈다(get_conn을 가짜로 바꿈).
- 저장 테스트는 공유 DB + 003 마이그레이션이 필요하다. 테이블이 없으면 건너뛴다. 만든 행·파일은 끝날 때 지운다.
"""

from io import BytesIO
from uuid import UUID, uuid4

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from psycopg import sql

from app.api.answer_reports import build_snapshot
from app.api.deps import get_conn, get_storage
from app.api.supplements import infer_kind, pdf_page_count
from app.main import create_app
from app.storage.local import LocalStorage

REPORT = {
    "question": "다음 중 빅데이터 가치 패러다임의 변화 단계별 순서로 가장 적절한 것은?",
    "type": "wrong_concept",
    "concept_details": ["관련 개념이 빠져 있어요"],
    "detail": "근거가 다른 단원이에요",
}


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (20, 10), "white").save(buf, format="PNG")
    return buf.getvalue()


def _pdf(pages: int = 2) -> bytes:
    pdf = pdfium.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(200, 200)
    buf = BytesIO()
    pdf.save(buf)
    pdf.close()
    return buf.getvalue()


def _no_db_client(tmp_path=None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: None
    if tmp_path is not None:
        storage = LocalStorage(tmp_path / "저장소")
        app.dependency_overrides[get_storage] = lambda: storage
    return TestClient(app)


# ---- DB 없이 ----

@pytest.mark.parametrize(
    "patch",
    [
        {"type": "nope"},
        {"question": ""},
        {"detail": "가" * 501},
        {"concept_details": ["x"] * 11},
        {"query_log_id": "not-a-uuid"},
    ],
)
def test_report_validation(patch):
    with _no_db_client() as client:
        assert client.post("/answer-reports", json=REPORT | patch).status_code == 422


def test_report_accepts_frontend_field_name():
    """프론트는 type 대신 report_type으로 보낸다. 값 검증은 같다."""
    body = {k: v for k, v in REPORT.items() if k != "type"}
    with _no_db_client() as client:
        assert client.post("/answer-reports", json=body | {"report_type": "nope"}).status_code == 422
        assert client.post("/answer-reports", json=body).status_code == 422  # 둘 다 없음


def test_infer_kind():
    assert infer_kind(None, "자료.pdf", b"anything") == "pdf"
    assert infer_kind(None, "scan", b"%PDF-1.7 ...") == "pdf"
    assert infer_kind(None, "a.png", b"\x89PNG") == "image"
    assert infer_kind("내용", None, b"") == "text"


def test_report_list_and_patch_validation():
    with _no_db_client() as client:
        assert client.get("/answer-reports", params={"status": "nope"}).status_code == 422
        assert client.get("/answer-reports", params={"limit": 0}).status_code == 422
        assert client.patch(f"/answer-reports/{uuid4()}", json={"status": "done"}).status_code == 422


def test_build_snapshot_prefers_db_then_client():
    logged = [
        {"n": 1, "chunk_id": "a", "page": "62", "vector_score": 0.7, "rerank_score": 0.9, "cited": True},
        {"n": 2, "chunk_id": "b", "page": "63", "vector_score": 0.6, "rerank_score": 0.5, "cited": False},
        {"n": 3, "chunk_id": "c", "page": None, "vector_score": 0.5, "rerank_score": 0.1, "cited": False},
    ]
    chunks = {"a": {"book_title": "책", "raw_text": "원문 A", "printed_page_number": "62", "title": "제목A",
                    "embedding_text": "1과목 > 2절\n\n정리 A", "clean_text": "정리 A"}}
    client = [{"n": 2, "chunk_id": "b", "book_title": "책", "path": "경로B", "raw_text": "원문 B"}]
    snap = build_snapshot(logged, chunks, client)
    assert [s["source"] for s in snap] == ["db", "client", "missing"]
    assert snap[0]["path"] == "1과목 > 2절" and snap[0]["raw_text"] == "원문 A" and snap[0]["book_title"] == "책"
    assert snap[0]["cited"] is True and snap[0]["rerank_score"] == 0.9
    assert snap[1]["raw_text"] == "원문 B" and snap[1]["page"] == "63"
    assert snap[2]["raw_text"] is None


def test_build_snapshot_without_log_uses_client():
    snap = build_snapshot([], {}, [{"n": 1, "chunk_id": "x", "raw_text": "r"}])
    assert snap == [{"n": 1, "chunk_id": "x", "book_title": None, "page": None, "path": None, "raw_text": "r",
                     "vector_score": None, "rerank_score": None, "cited": None, "source": "client"}]


def test_pdf_page_count():
    assert pdf_page_count(_pdf(3)) == 3
    with pytest.raises(ValueError):
        pdf_page_count(b"not a pdf")


@pytest.mark.parametrize(
    "form, files, code",
    [
        ({"source": "report", "kind": "text", "content": "  "}, None, 400),  # 빈 텍스트
        ({"source": "report", "kind": "image"}, None, 400),  # 파일 없음
        ({"source": "report", "kind": "image"}, {"file": ("a.txt", b"hello", "text/plain")}, 400),
        ({"source": "report", "kind": "pdf"}, {"file": ("a.pdf", b"not pdf", "application/pdf")}, 400),
        ({"source": "elsewhere", "kind": "text", "content": "x"}, None, 422),
        ({"source": "report", "kind": "video", "content": "x"}, None, 422),
        ({"source": "report"}, None, 400),  # kind 생략 + 내용·파일 없음
        ({"source": "report", "text": "  "}, None, 400),  # 프론트 이름(text), 빈 내용
        ({"source": "report"}, {"file": ("a.txt", b"hello", "text/plain")}, 400),  # kind 생략 → image로 보고 검증 실패
        ({"source": "report"}, {"file": ("a.pdf", b"not pdf", "application/pdf")}, 400),  # kind 생략 → pdf
    ],
)
def test_supplement_validation(tmp_path, form, files, code):
    with _no_db_client(tmp_path) as client:
        r = client.post("/supplements", data=form, files=files)
    assert r.status_code == code, r.text
    assert not (tmp_path / "저장소").exists()  # 검증 실패면 파일을 저장하지 않는다


def test_supplement_pdf_page_limit(tmp_path, settings):
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: None
    storage = LocalStorage(tmp_path / "저장소")
    app.dependency_overrides[get_storage] = lambda: storage
    from app.api.deps import get_settings

    s = settings.model_copy(update={"supplement_max_pdf_pages": 2})
    app.dependency_overrides[get_settings] = lambda: s
    with TestClient(app) as client:
        r = client.post("/supplements", data={"source": "unanswerable", "kind": "pdf"},
                        files={"file": ("긴 자료.pdf", _pdf(3), "application/pdf")})
    assert r.status_code == 400 and "2쪽 이하" in r.json()["detail"]


# ---- 공유 DB + 003 필요 ----

@pytest.fixture
def tables(db_conn, settings):
    for t in ("answer_reports", "supplements"):
        if db_conn.execute("SELECT to_regclass(%s)", (f"{settings.db_app_schema}.{t}",)).fetchone()[0] is None:
            pytest.skip(f"{t} 테이블 없음(003 마이그레이션 미적용)")
    created: dict[str, list[UUID]] = {"reports": [], "supplements": []}
    yield created
    a = sql.Identifier(settings.db_app_schema)
    with db_conn.transaction():
        if created["supplements"]:
            db_conn.execute(sql.SQL("DELETE FROM {}.supplements WHERE id = ANY(%s)").format(a), (created["supplements"],))
        if created["reports"]:
            db_conn.execute(sql.SQL("DELETE FROM {}.answer_reports WHERE id = ANY(%s)").format(a), (created["reports"],))


def _client(tmp_path):
    app = create_app()
    storage = LocalStorage(tmp_path / "저장소")
    app.dependency_overrides[get_storage] = lambda: storage
    return TestClient(app), storage


def test_report_create_list_resolve(tables, tmp_path):
    client, _ = _client(tmp_path)
    with client:
        # 화면 payload 그대로(query_log_id 없음) → 화면이 보낸 근거로 스냅샷
        body = REPORT | {"evidence": [{"n": 1, "chunk_id": "x", "book_title": "책", "page": "62", "raw_text": "원문"}]}
        r = client.post("/answer-reports", json=body)
        assert r.status_code == 201, r.text
        first = r.json()
        tables["reports"].append(UUID(first["id"]))
        assert first["status"] == "open" and first["resolved_at"] is None
        assert first["evidence_snapshot"][0]["source"] == "client"

        front = {k: v for k, v in REPORT.items() if k != "type"} | {"report_type": "missing_concept", "explanation": "무시됨"}
        r = client.post("/answer-reports", json=front)  # 프론트 payload 이름
        assert r.status_code == 201 and r.json()["report_type"] == "missing_concept"
        second = r.json()
        tables["reports"].append(UUID(second["id"]))

        ids = [x["id"] for x in client.get("/answer-reports", params={"status": "open", "limit": 200}).json()]
        assert ids.index(second["id"]) < ids.index(first["id"])  # 최신순, 같은 답변이어도 행이 따로 쌓임

        r = client.patch(f"/answer-reports/{first['id']}", json={"status": "resolved"})
        assert r.json()["status"] == "resolved" and r.json()["resolved_at"] is not None
        open_ids = [x["id"] for x in client.get("/answer-reports", params={"status": "open", "limit": 200}).json()]
        assert first["id"] not in open_ids  # 처리 완료한 신고만 목록에서 빠짐
        assert client.patch(f"/answer-reports/{first['id']}", json={"status": "open"}).json()["resolved_at"] is None
        assert client.patch(f"/answer-reports/{uuid4()}", json={"status": "resolved"}).status_code == 404

        r = client.post("/answer-reports", json=REPORT | {"query_log_id": str(uuid4())})
        assert r.status_code == 422 and "query_log_id" in r.json()["detail"]


def test_supplements_saved_as_pending(tables, tmp_path):
    client, storage = _client(tmp_path)
    with client:
        report = client.post("/answer-reports", json=REPORT).json()
        tables["reports"].append(UUID(report["id"]))

        r = client.post("/supplements", data={"source": "report", "kind": "text", "title": "가치 패러다임",
                                              "content": "디지털화 → 연결 → 에이전시", "report_id": report["id"],
                                              "question": REPORT["question"]})
        assert r.status_code == 201, r.text
        text = r.json()
        tables["supplements"].append(UUID(text["id"]))
        assert text["status"] == "pending_review" and text["kind"] == "text" and text["report_id"] == report["id"]
        assert "file_uri" not in text

        r = client.post("/supplements", data={"source": "unanswerable", "kind": "image"},
                        files={"file": ("메모.png", _png(), "image/png")})
        image = r.json()
        tables["supplements"].append(UUID(image["id"]))
        assert image["mime_type"] == "image/png" and image["original_filename"] == "메모.png"
        assert storage.read(f"local://supplements/{image['id']}.png") == _png()

        r = client.post("/supplements", data={"source": "unanswerable"},  # 프론트처럼 kind 생략
                        files={"file": ("자료.pdf", _pdf(2), "application/pdf")})
        pdf = r.json()
        tables["supplements"].append(UUID(pdf["id"]))
        assert pdf["kind"] == "pdf" and pdf["page_count"] == 2 and pdf["mime_type"] == "application/pdf"

        r = client.post("/supplements", data={"source": "unanswerable", "text": "프론트 이름으로 보낸 본문"})
        front_text = r.json()
        tables["supplements"].append(UUID(front_text["id"]))
        assert front_text["kind"] == "text" and front_text["content_text"] == "프론트 이름으로 보낸 본문"

        pending = [x["id"] for x in client.get("/supplements", params={"status": "pending_review", "limit": 200}).json()]
        assert {text["id"], image["id"], pdf["id"]} <= set(pending)

        r = client.post("/supplements", data={"source": "report", "kind": "text", "content": "x", "report_id": str(uuid4())})
        assert r.status_code == 422

        r = client.post("/supplements", data={"source": "report", "kind": "image", "query_log_id": str(uuid4())},
                        files={"file": ("a.png", _png(), "image/png")})
        assert r.status_code == 422
    assert sorted(p.name for p in (tmp_path / "저장소" / "supplements").iterdir()) == sorted(
        [f"{image['id']}.png", f"{pdf['id']}.pdf"]
    )  # 실패한 등록의 파일은 지운다
