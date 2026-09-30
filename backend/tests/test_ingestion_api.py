"""과목 생성 → 이미지 업로드 → 백그라운드 처리 → 상태 조회 (공유 DB 필요).

테스트가 만든 books/processing_runs 행은 끝날 때 지운다(pages는 books 삭제 시 CASCADE).
저장 파일은 임시 폴더에 둔다. OCR은 가짜 엔진으로 바꿔 모델 없이 돌린다.
"""

import json
from io import BytesIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from psycopg import sql
from psycopg.rows import dict_row

from app.api.deps import get_storage
from app.ingestion import ocr
from app.ingestion.ocr import OcrLine, OcrResult
from app.db.connection import create_pool
from app.ingestion.pipeline import DEFAULT_STAGES, Stage, run_pipeline
from app.ingestion.stages import NeedsReview, ocr_key
from app.main import create_app
from app.repositories import runs as runs_repo
from app.storage.local import LocalStorage

SUBJECT = "__pytest_subject__"


def _png(w: int = 40, h: int = 30) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (20, 10), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def cleanup(db_conn, settings):
    created: dict[str, list] = {"books": [], "runs": []}
    yield created
    s = sql.Identifier(settings.db_schema)
    with db_conn.transaction():
        if created["books"]:
            db_conn.execute(sql.SQL("DELETE FROM {}.books WHERE id = ANY(%s)").format(s), (created["books"],))
        if created["runs"]:
            db_conn.execute(
                sql.SQL("DELETE FROM {}.processing_runs WHERE id = ANY(%s)").format(s), (created["runs"],)
            )


def _noop(ctx):
    pass


# 모든 단계가 아무것도 하지 않고 성공하는 파이프라인(상태 흐름·API 확인용)
NOOP_STAGES = tuple(Stage(s.name, _noop, s.done_status) for s in DEFAULT_STAGES)


def _client(tmp_path, stages=NOOP_STAGES):
    app = create_app()
    storage = LocalStorage(tmp_path / "저장소")
    app.dependency_overrides[get_storage] = lambda: storage
    app.state.pipeline_stages = stages
    return TestClient(app), storage


def _create_book(client, cleanup, title="테스트 교재", material_type="textbook"):
    r = client.post("/books", json={"title": title, "subject": SUBJECT, "material_type": material_type})
    assert r.status_code == 201, r.text
    book = r.json()
    cleanup["books"].append(UUID(book["id"]))
    return book


def test_book_create_and_list(db_conn, tmp_path, cleanup):
    client, _ = _client(tmp_path)
    with client:
        book = _create_book(client, cleanup)
        assert book["subject"] == SUBJECT and book["page_count"] == 0

        assert SUBJECT in client.get("/subjects").json()
        listed = client.get("/books", params={"subject": SUBJECT}).json()
        assert [b["id"] for b in listed] == [book["id"]]
        assert listed[0]["page_count"] == 0 and listed[0]["status_counts"] == {}

        assert client.get(f"/books/{book['id']}").json()["title"] == "테스트 교재"
        assert client.get("/books/00000000-0000-0000-0000-000000000000").status_code == 404
        bad = {"title": "x", "subject": SUBJECT, "material_type": "novel"}
        assert client.post("/books", json=bad).status_code == 422


def test_upload_runs_pipeline_to_embedded(db_conn, tmp_path, cleanup):
    client, storage = _client(tmp_path)
    with client:
        book = _create_book(client, cleanup)
        files = [
            ("files", ("1장 표지.png", _png(40, 30), "image/png")),
            ("files", ("2.jpg", _jpeg(), "image/jpeg")),
        ]
        r = client.post(f"/books/{book['id']}/pages", files=files)
        assert r.status_code == 202, r.text
        body = r.json()
        cleanup["runs"].append(UUID(body["run_id"]))
        assert [p["upload_index"] for p in body["pages"]] == [0, 1]
        assert body["pages"][0]["original_filename"] == "1장 표지.png"

        # TestClient는 백그라운드 작업까지 끝난 뒤 반환한다.
        run = client.get(f"/processing-runs/{body['run_id']}").json()
        assert run["status"] == "SUCCESS"
        assert (run["page_count"], run["success_count"], run["failure_count"]) == (2, 2, 0)
        assert run["finished_at"] is not None
        pages = run["pages"]
        assert [p["processing_status"] for p in pages] == ["EMBEDDED", "EMBEDDED"]
        assert all(p["quality_passed"] and not p["review_required"] for p in pages)
        assert pages[0]["pipeline"]["stage"] == "embed"
        assert (pages[0]["source_width"], pages[0]["source_height"]) == (40, 30)
        assert "source_s3_uri" not in pages[0]

        # 원본 파일이 저장소에 그대로 저장되었는지
        uri = db_conn.execute(
            sql.SQL("SELECT source_s3_uri FROM {}.pages WHERE id = %s").format(
                sql.Identifier(client.app.state.settings.db_schema)
            ),
            (pages[0]["id"],),
        ).fetchone()[0]
        assert uri == f"local://books/{book['id']}/{pages[0]['id']}.png"
        assert storage.read(uri) == files[0][1][1]

        # 두 번째 업로드는 페이지 순서를 이어 붙인다.
        r2 = client.post(f"/books/{book['id']}/pages", files=[("files", ("3.png", _png(), "image/png"))])
        cleanup["runs"].append(UUID(r2.json()["run_id"]))
        assert r2.json()["pages"][0]["upload_index"] == 2

        b = client.get(f"/books/{book['id']}").json()
        assert b["page_count"] == 3 and b["status_counts"] == {"EMBEDDED": 3}
        assert [p["upload_index"] for p in client.get(f"/books/{book['id']}/pages").json()] == [0, 1, 2]


def test_upload_rejects_invalid_files_without_saving(db_conn, tmp_path, cleanup):
    client, storage = _client(tmp_path)
    with client:
        book = _create_book(client, cleanup)
        files = [
            ("files", ("ok.png", _png(), "image/png")),
            ("files", ("fake.png", b"not an image", "image/png")),
        ]
        r = client.post(f"/books/{book['id']}/pages", files=files)
        assert r.status_code == 400 and "fake.png" in r.json()["detail"]
        assert client.get(f"/books/{book['id']}/pages").json() == []
        assert not storage.root.exists() or not any(storage.root.rglob("*.*"))

        missing = "00000000-0000-0000-0000-000000000000"
        assert client.post(f"/books/{missing}/pages", files=files[:1]).status_code == 404


def _fail(ctx):
    raise RuntimeError("boom")


def _review_second_page(ctx):
    # 업로드 순서 1번 페이지만 품질 미달로 만든다.
    idx = ctx.conn.execute(
        sql.SQL("SELECT (page_metadata->>'upload_index')::int FROM {}.pages WHERE id = %s").format(
            sql.Identifier(ctx.settings.db_schema)
        ),
        (ctx.page_id,),
    ).fetchone()[0]
    if idx == 1:
        raise NeedsReview("글자 인식률 낮음")


def _stages(**replace):
    return tuple(Stage(s.name, replace.get(s.name, s.func), s.done_status) for s in NOOP_STAGES)


def test_pipeline_review_and_partial(db_conn, tmp_path, cleanup):
    client, _ = _client(tmp_path, _stages(chunk_theory=_review_second_page))
    with client:
        book = _create_book(client, cleanup)
        files = [("files", (f"{i}.png", _png(), "image/png")) for i in range(2)]
        body = client.post(f"/books/{book['id']}/pages", files=files).json()
        cleanup["runs"].append(UUID(body["run_id"]))
        run = client.get(f"/processing-runs/{body['run_id']}").json()

    assert run["status"] == "PARTIAL"
    assert (run["success_count"], run["review_count"], run["failure_count"]) == (1, 1, 0)
    ok, review = run["pages"]
    assert ok["processing_status"] == "EMBEDDED"
    assert review["processing_status"] == "REVIEW_REQUIRED" and review["review_required"]
    assert not review["quality_passed"]
    assert review["pipeline"]["stage"] == "chunk_theory"
    assert review["pipeline"]["reason"] == "글자 인식률 낮음"


def test_pipeline_failure_marks_failed(db_conn, tmp_path, cleanup):
    client, _ = _client(tmp_path, _stages(detect_visuals=_fail))
    with client:
        book = _create_book(client, cleanup)
        body = client.post(f"/books/{book['id']}/pages", files=[("files", ("a.png", _png(), "image/png"))]).json()
        cleanup["runs"].append(UUID(body["run_id"]))
        run = client.get(f"/processing-runs/{body['run_id']}").json()

    assert run["status"] == "FAILED" and run["failure_count"] == 1
    page = run["pages"][0]
    # extract_text는 끝났으므로 EXTRACTED를 거쳐 FAILED가 된다.
    assert page["processing_status"] == "FAILED"
    assert page["pipeline"]["stage"] == "detect_visuals"
    assert page["pipeline"]["error"] == "RuntimeError: boom"


def test_run_not_found(db_conn, tmp_path):
    client, _ = _client(tmp_path)
    with client:
        assert client.get("/processing-runs/00000000-0000-0000-0000-000000000000").status_code == 404


class _FakeEngine:
    engine = {"name": "fake", "lang": "korean", "det_model": "d", "rec_model": "r"}

    def __init__(self):
        self.shapes = []

    def recognize(self, image):
        self.shapes.append(image.shape)
        lines = [OcrLine("데이터 분석", 0.98, (1, 2, 30, 12)), OcrLine("준전문가", 0.9, (1, 15, 25, 25))]
        return OcrResult(lines, self.engine)


@pytest.fixture
def fake_ocr(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(ocr, "get_engine", lambda settings: engine)
    return engine


def test_default_pipeline_stops_at_extracted(db_conn, tmp_path, cleanup, fake_ocr):
    """실제 extract_text + 미구현 단계: EMBEDDED로 넘어가지 않고 EXTRACTED에서 멈춘다."""
    client, storage = _client(tmp_path, DEFAULT_STAGES)
    with client:
        book = _create_book(client, cleanup)
        body = client.post(f"/books/{book['id']}/pages", files=[("files", ("a.png", _png(40, 30), "image/png"))]).json()
        cleanup["runs"].append(UUID(body["run_id"]))
        run = client.get(f"/processing-runs/{body['run_id']}").json()

    assert fake_ocr.shapes == [(30, 40, 3)]  # 저장된 원본을 OpenCV로 디코딩해서 넘김
    assert run["status"] == "PARTIAL"
    assert (run["success_count"], run["review_count"], run["failure_count"]) == (0, 0, 0)
    page = run["pages"][0]
    assert page["processing_status"] == "EXTRACTED" and not page["review_required"]
    assert page["pipeline"]["stage"] == "detect_visuals"
    assert page["pipeline"]["stopped"] == "not_implemented"

    meta = db_conn.execute(
        sql.SQL("SELECT page_metadata->'ocr' FROM {}.pages WHERE id = %s").format(
            sql.Identifier(client.app.state.settings.db_schema)
        ),
        (page["id"],),
    ).fetchone()[0]
    uri = f"local://{ocr_key(book['id'], page['id'])}"
    assert meta == {"uri": uri, "line_count": 2, "mean_confidence": 0.94, **_FakeEngine.engine}
    saved = json.loads(storage.read(uri).decode("utf-8"))
    assert [line["text"] for line in saved["lines"]] == ["데이터 분석", "준전문가"]
    assert saved["lines"][0]["bbox"] == [1, 2, 30, 12]


def test_personal_note_needs_review(db_conn, tmp_path, cleanup, fake_ocr):
    client, _ = _client(tmp_path, DEFAULT_STAGES)
    with client:
        book = _create_book(client, cleanup, material_type="personal_note")
        body = client.post(f"/books/{book['id']}/pages", files=[("files", ("n.png", _png(), "image/png"))]).json()
        cleanup["runs"].append(UUID(body["run_id"]))
        run = client.get(f"/processing-runs/{body['run_id']}").json()

    assert fake_ocr.shapes == []  # 손필기는 PaddleOCR로 보내지 않는다
    assert run["status"] == "PARTIAL" and run["review_count"] == 1
    page = run["pages"][0]
    assert page["processing_status"] == "REVIEW_REQUIRED" and page["review_required"]
    assert page["pipeline"] == {**page["pipeline"], "stage": "extract_text", "reason": "손필기 추출 미구현"}


def _interrupt_second_page(ctx):
    # 업로드 순서 1번 페이지 처리 중에 Ctrl+C가 들어온 것처럼 만든다.
    idx = ctx.conn.execute(
        sql.SQL("SELECT (page_metadata->>'upload_index')::int FROM {}.pages WHERE id = %s").format(
            sql.Identifier(ctx.settings.db_schema)
        ),
        (ctx.page_id,),
    ).fetchone()[0]
    if idx == 1:
        raise KeyboardInterrupt


def test_interrupted_run_closes_as_failed(db_conn, settings, tmp_path, cleanup):
    """중간에 끊긴 실행은 RUNNING으로 남지 않고 FAILED로 닫히며, 끊긴 페이지 상태는 그대로다."""
    client, storage = _client(tmp_path)
    with client:
        book = _create_book(client, cleanup)
        files = [("files", (f"{i}.png", _png(), "image/png")) for i in range(3)]
        body = client.post(f"/books/{book['id']}/pages", files=files).json()
        cleanup["runs"].append(UUID(body["run_id"]))
        page_ids = [UUID(p["id"]) for p in client.get(f"/processing-runs/{body['run_id']}").json()["pages"]]

    run_id = runs_repo.create_run(db_conn, settings, pipeline_version="test", page_count=len(page_ids))
    cleanup["runs"].append(run_id)
    pool = create_pool(settings)
    pool.open()
    try:
        with pytest.raises(KeyboardInterrupt):
            run_pipeline(pool, settings, storage, run_id, page_ids, stage_list=_stages(embed=_interrupt_second_page))
    finally:
        pool.close()

    run = runs_repo.get_run(db_conn, settings, run_id)
    assert run["status"] == "FAILED" and run["finished_at"] is not None
    assert (run["success_count"], run["review_count"], run["failure_count"]) == (1, 0, 0)
    statuses = {r["id"]: r["processing_status"] for r in _page_statuses(db_conn, settings, page_ids)}
    assert statuses[page_ids[0]] == "EMBEDDED"
    assert statuses[page_ids[1]] == "VERIFIED"  # embed 도중 끊김 → 마지막으로 끝난 상태 유지
    assert statuses[page_ids[2]] == "EMBEDDED"  # 첫 실행 결과 그대로(두 번째 실행은 도달 못 함)


def _page_statuses(db_conn, settings, page_ids):
    q = sql.SQL("SELECT id, processing_status FROM {}.pages WHERE id = ANY(%s)").format(
        sql.Identifier(settings.db_schema)
    )
    with db_conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (page_ids,)).fetchall()
