"""/qa 응답 visuals: 인용된 근거 쪽 → 공통 JSON의 연결된 표·시각자료 (D-J-005). DB·모델 없이 돈다."""

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import qa as qa_api
from app.api.deps import get_conn, get_settings
from app.main import create_app
from app.visuals.common_json import build_index, find_visuals, load_index, subject_from_title, visuals_for

BOOK = "2024 ADsP 한 권으로 끝내기 이론편 - 1과목 데이터 이해"


def _image(asset: str, page: int) -> dict:
    base = "https://example.invalid/adsp/subject1"
    return {"original_url": f"{base}/crops/page_{page:04d}/{asset}.jpg",
            "thumbnail_url": f"{base}/thumbnails/page_{page:04d}/{asset}.jpg"}


BLOCKS = [
    {"block_id": "S1:THEORY:TH_62_02", "source_id": "TH_62_02", "subject": 1, "printed_page_number": 62,
     "block_type": "theory", "title": "가치 패러다임의 변화"},
    {"block_id": "S1:THEORY:TH_63_01", "source_id": "TH_63_01", "subject": 1, "printed_page_number": 63,
     "block_type": "theory", "title": "에이전시"},
    {"block_id": "S1:VISUAL:VIS_63_01", "source_id": "VIS_63_01", "subject": 1, "printed_page_number": 63,
     "block_type": "visual", "title": "Digitalization Connection Agency 도식", "concept_name": "가치 패러다임",
     "visual_description": "세 단계가 화살표로 이어진 도식", "image": _image("VIS_63_01", 63)},
    {"block_id": "S1:TABLE:TAB_62_01", "source_id": "TAB_62_01", "subject": 1, "printed_page_number": 62,
     "block_type": "table", "title": "낮은 신뢰도 표", "image": _image("TAB_62_01", 62)},
    {"block_id": "S1:VISUAL:VIS_70_01", "source_id": "VIS_70_01", "subject": 1, "printed_page_number": 70,
     "block_type": "visual", "title": "이미지 없음"},  # image 없으면 제외
]
RELATIONS = [
    {"from_block_id": "S1:THEORY:TH_62_02", "to_block_id": "S1:VISUAL:VIS_63_01", "confidence": 0.95},
    {"from_block_id": "S1:THEORY:TH_63_01", "to_block_id": "S1:VISUAL:VIS_63_01", "confidence": 1.0},
    {"from_block_id": "S1:THEORY:TH_62_02", "to_block_id": "S1:TABLE:TAB_62_01", "confidence": 0.5},
    {"from_block_id": "S1:THEORY:TH_62_02", "to_block_id": "S1:THEORY:TH_63_01", "confidence": 0.99},  # 이론끼리는 무시
]


def _ev(n: int, page, cited=True, book=BOOK) -> dict:
    return {"n": n, "book_title": book, "page": page, "cited": cited}


def test_subject_from_title():
    assert subject_from_title(BOOK) == 1
    assert subject_from_title("3과목 데이터 분석") == 3
    assert subject_from_title("과목 없음") is None and subject_from_title(None) is None


def test_find_visuals_from_cited_pages():
    idx = build_index(BLOCKS, RELATIONS)
    out = find_visuals(idx, [_ev(1, "62"), _ev(2, "63"), _ev(3, "63", cited=False)], 0.8, 3)
    assert [v["asset_id"] for v in out] == ["VIS_63_01"]  # 0.5짜리 표는 하한 미만
    v = out[0]
    assert v["kind"] == "visual" and v["page"] == 63 and v["subject"] == 1
    assert v["linked_evidence"] == [1, 2] and v["confidence"] == 1.0
    assert v["image_url"].endswith("/VIS_63_01.jpg") and v["description"] == "세 단계가 화살표로 이어진 도식"

    low = find_visuals(idx, [_ev(1, 62)], 0.4, 3)
    assert [v["asset_id"] for v in low] == ["VIS_63_01", "TAB_62_01"]  # 신뢰도 높은 순
    assert find_visuals(idx, [_ev(1, 62)], 0.4, 1)[0]["asset_id"] == "VIS_63_01"  # 최대 개수


def test_find_visuals_ignores_uncited_and_unknown():
    idx = build_index(BLOCKS, RELATIONS)
    assert find_visuals(idx, [_ev(1, 63, cited=False)], 0.8, 3) == []
    assert find_visuals(idx, [_ev(1, 63, book="과목 없는 책")], 0.8, 3) == []
    assert find_visuals(idx, [_ev(1, None)], 0.8, 3) == []
    assert find_visuals(idx, [_ev(1, 999)], 0.8, 3) == []


def _write_json(folder, blocks=BLOCKS, relations=RELATIONS):
    d = folder / "subject1"
    d.mkdir(parents=True)
    (d / "adsp_subject1_blocks.json").write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    (d / "adsp_subject1_relations.json").write_text(
        json.dumps({"block_relations": relations}, ensure_ascii=False), encoding="utf-8")
    return d


def test_load_index_reads_folder_and_reloads(tmp_path):
    folder = tmp_path / "공통 JSON"
    assert load_index(folder).assets == {}  # 폴더 없음
    d = _write_json(folder)
    assert set(load_index(folder).assets) == {"S1:VISUAL:VIS_63_01", "S1:TABLE:TAB_62_01"}
    (d / "adsp_subject1_relations.json").write_text(json.dumps({"block_relations": []}), encoding="utf-8")
    assert load_index(folder).links == {}  # 파일이 바뀌면 다시 읽는다


def test_visuals_for_never_raises(tmp_path, settings):
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "x_blocks.json").write_text("{not json", encoding="utf-8")
    s = settings.model_copy(update={"common_json_dir": folder})
    assert visuals_for(s, [_ev(1, 63)]) == []


def test_qa_api_adds_visuals(tmp_path, settings, monkeypatch):
    folder = tmp_path / "common_json"
    _write_json(folder)
    fake = {"status": "answered", "evidence": [_ev(1, "63")], "answer": "답 [1]"}
    monkeypatch.setattr(qa_api, "answer_question", lambda conn, s, models, q, k: dict(fake))

    def fake_conn():
        yield None

    for max_n, expected in ((3, ["VIS_63_01"]), (0, [])):
        app = create_app()
        app.dependency_overrides[get_conn] = fake_conn
        s = settings.model_copy(update={"common_json_dir": folder, "visuals_max": max_n})
        app.dependency_overrides[get_settings] = lambda s=s: s
        with TestClient(app) as client:
            app.state.qa_models = SimpleNamespace(llm=None, judge=None)
            r = client.post("/qa", json={"question": "가치 패러다임 순서는?"})
        assert r.status_code == 200, r.text
        assert [v["asset_id"] for v in r.json()["visuals"]] == expected
