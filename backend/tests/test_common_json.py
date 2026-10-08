"""공통 JSON 적재 테스트 (D-M-032). 가짜 문장으로 만든 작은 샘플 JSON만 쓴다(교재 원문 없음, DB 없음)."""

import copy
import json

import pytest

from app.ingestion.common_json import (
    EXCLUDE_DUPLICATE,
    EXCLUDE_LEARNING_OBJECTIVE,
    CommonJsonError,
    ExistingBlock,
    build_subject,
    embedding_text,
    linearize_table,
    plan_blocks,
    read_subject,
    resolve_duplicate,
    select_blocks,
)
from app.ingestion.common_json_load import main

IMAGE = {"s3_bucket": "b", "s3_region": "r", "original_s3_key": "k/crop.jpg", "thumbnail_s3_key": "k/thumb.jpg"}


def _theory(sid, page, text, **kw):
    b = {"block_id": f"S9:THEORY:{sid}", "source_id": sid, "subject": 9, "printed_page_number": page,
         "block_type": "theory", "order_in_page": 1, "title_path": ["1장 가짜 장", f"{sid} 제목"],
         "title": f"{sid} 제목", "block_role": "content", "raw_text": text + "  원문", "clean_text": text,
         "model_generated": {"keywords": ["키워드"], "exam_clues": ["단서"]}, "review": {"needs_review": False}}
    b.update(kw)
    return b


def _table(sid, page, table, **kw):
    b = {"block_id": f"S9:TABLE:{sid}", "source_id": sid, "subject": 9, "printed_page_number": page,
         "block_type": "table", "title_path": ["1장 가짜 장", "가짜 표"], "title": "가짜 표",
         "raw_text": ["원문 목록"], "clean_text": None, "table": table, "image": dict(IMAGE),
         "review": {"needs_review": False}}
    b.update(kw)
    return b


def _visual(sid, page, **kw):
    b = {"block_id": f"S9:VISUAL:{sid}", "source_id": sid, "subject": 9, "printed_page_number": page,
         "block_type": "visual", "title_path": ["1장 가짜 장", "가짜 그림"], "title": "가짜 그림",
         "raw_text": ["가", "나 다"], "clean_text": None, "visual_type": "diagram",
         "visual_description": "가가 나나를 가리킨다.", "visual_observation": "관찰 문장",
         "visual_structure": "위아래 2칸", "related_theory_context": "이론 문맥(넣지 않음)",
         "related_theory_context_source": "page_theory_context_only", "image": dict(IMAGE),
         "review": {"needs_review": False}}
    b.update(kw)
    return b


def _code(sid, page, **kw):
    b = {"block_id": f"S9:CODE:{sid}", "source_id": sid, "subject": 9, "printed_page_number": page,
         "block_type": "code", "title_path": ["1장 가짜 장", "가짜 코드"], "title": "가짜 코드",
         "raw_code": "> x <- 1\n> x\n[1] 1", "clean_code": "x <- 1\nx\n", "execution_output": "[1] 1",
         "language": "R", "raw_text": None, "clean_text": None, "image": dict(IMAGE),
         "review": {"needs_review": False}}
    b.update(kw)
    return b


def _formula(sid, page, **kw):
    b = {"block_id": f"S9:FORMULA:{sid}", "source_id": sid, "subject": 9, "printed_page_number": page,
         "block_type": "formula", "title_path": ["1장 가짜 장", "가짜 수식"], "title": "가짜 수식",
         "raw_text": r"\frac{a}{b}", "clean_text": r"\frac{a}{b}", "latex": r"\frac{a}{b}",
         "plain_text": "a / b", "image": None, "review": {"needs_review": False}}
    b.update(kw)
    return b


def _rel(rid, a, b, link_type, source="verified_relationship_manifest"):
    return {"relationship_id": rid, "from_block_id": a, "to_block_id": b, "from_page": 1, "to_page": 2,
            "link_type": link_type, "relation_types": ["SEMANTIC_CONTINUATION"], "confidence": 0.9,
            "reason": "가짜 이유", "relation_source": source}


@pytest.fixture
def sample():
    """과목 9: 이론 2(그중 학습목표 1) + 중복 이론 1 + 표 2 + 시각자료 1, 관계 3."""
    blocks = [
        _theory("TH_1_00", 1, "학습목표 목록", block_role="learning_objective"),
        _theory("TH_1_01", 1, "가나다 설명 문장이다.", subject_name="9과목 가짜"),
        _theory("TH_2_01", 2, "표를 풀어 쓴 문장", duplicate_of_table_id="TAB_2_01"),
        _table("TAB_2_01", 2, {"headers": [], "row_headers": ["행가", "행나"],
                               "rows": [["행가\n(A)", "• 값1\n• 값2"], ["행나", "값3"]], "merged_cells": [], "units": []}),
        _table("TAB_2_02", 2, {"headers": ["구분", "", "비고"], "row_headers": [],
                               "rows": [["갑", "을", "병"], ["정", "", "무"]],
                               "merged_cells": [{"start_row": 0, "end_row": 1, "start_col": 1, "end_col": 1, "text": "을"}],
                               "units": ["%"]}, clean_correction_note="가짜 교정 메모"),
        _visual("VIS_2_01", 2),
    ]
    relations = [
        _rel("BREL_1", "S9:THEORY:TH_1_01", "S9:TABLE:TAB_2_01", "THEORY_TO_TABLE"),
        _rel("BREL_2", "S9:THEORY:TH_2_01", "S9:TABLE:TAB_2_01", "THEORY_TO_TABLE", source="duplicate_of_table_id"),
        _rel("BREL_3", "S9:VISUAL:VIS_2_01", "S9:THEORY:TH_1_01", "VISUAL_TO_THEORY"),
    ]
    pages = [{"subject": 9, "printed_page_number": 1, "block_ids_in_reading_order": ["S9:THEORY:TH_1_00"]},
             {"subject": 9, "printed_page_number": 2, "block_ids_in_reading_order": []}]
    return {
        "blocks": {"format": "adsp_common_json", "format_version": "9.9-test", "subject": 9, "pages": pages,
                   "blocks": blocks},
        "relations": {"format": "adsp_common_relations", "subject": 9, "block_relations": relations,
                      "page_relations": [{"relationship_id": "PREL_1", "from_page": 1, "to_page": 2}]},
        "manifest": {"subject": 9, "subject_name": "9과목 가짜 과목"},
        "report": {"passed": True},
    }


def _build(settings, s):
    return build_subject(settings, "subject9", 9, s["blocks"], s["relations"], s["manifest"], s["report"])


def _errors(settings, s) -> list[str]:
    with pytest.raises(CommonJsonError) as e:
        _build(settings, s)
    return e.value.errors


def _by_id(data):
    return {r.block_id: r for r in data.blocks}


# ----- 정상 적재 -----

def test_build_counts_and_search_rules(settings, sample):
    data = _build(settings, sample)
    b = _by_id(data)
    assert data.document_key == "adsp_common_json:subject9"
    assert data.title == "9과목 가짜 과목"
    assert data.format_version == "9.9-test"
    assert len(data.blocks) == 6 and len(data.relations) == 3 and len(data.page_relations) == 1
    assert b["S9:THEORY:TH_1_00"].search_excluded_reason == EXCLUDE_LEARNING_OBJECTIVE
    assert b["S9:THEORY:TH_2_01"].search_excluded_reason == EXCLUDE_DUPLICATE
    assert b["S9:THEORY:TH_2_01"].duplicate_of_block_id == "S9:TABLE:TAB_2_01"
    assert [r.block_id for r in data.blocks if r.search_enabled] == [
        "S9:THEORY:TH_1_01", "S9:TABLE:TAB_2_01", "S9:TABLE:TAB_2_02", "S9:VISUAL:VIS_2_01"]
    # 표·시각자료는 block_role이 없으면 content
    assert b["S9:TABLE:TAB_2_01"].block_role == "content"
    assert b["S9:VISUAL:VIS_2_01"].block_role == "content"


def test_optional_fields_kept_in_source_and_raw_text_untouched(settings, sample):
    b = _by_id(_build(settings, sample))
    assert b["S9:THEORY:TH_1_01"].source["subject_name"] == "9과목 가짜"
    assert b["S9:TABLE:TAB_2_02"].source["clean_correction_note"] == "가짜 교정 메모"
    assert b["S9:THEORY:TH_1_01"].raw_text == "가나다 설명 문장이다.  원문"  # 원문 그대로(공백도)
    assert b["S9:TABLE:TAB_2_01"].raw_text == ["원문 목록"]
    assert b["S9:VISUAL:VIS_2_01"].visual_data["related_theory_context"] == "이론 문맥(넣지 않음)"
    assert b["S9:VISUAL:VIS_2_01"].crop_s3_key == "k/crop.jpg"
    assert b["S9:THEORY:TH_1_01"].model_generated["keywords"] == ["키워드"]


def test_missing_optional_fields_ok(settings, sample):
    s = copy.deepcopy(sample)
    s["manifest"] = None
    s["report"] = None
    del s["blocks"]["pages"]
    for r in s["relations"]["block_relations"]:
        r.pop("relation_scope", None)
    for b in s["blocks"]["blocks"]:
        b.pop("order_in_page", None)
        b.pop("model_generated", None)
        if b["block_type"] != "theory":
            b["block_role"] = ""
    data = _build(settings, s)
    assert data.title == "9과목"
    assert all(r.block_role in ("content", "learning_objective") for r in data.blocks)


def test_settings_can_include_excluded_blocks(settings, sample):
    s2 = settings.model_copy(update={"common_json_search_learning_objective": True,
                                     "common_json_search_duplicate_theory": True})
    assert all(r.search_enabled for r in _build(s2, sample).blocks)


def test_warnings_for_learning_objective_duplicate_and_pending(settings, sample):
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][0]["duplicate_of_table_id"] = "TAB_2_01"
    s2 = settings.model_copy(update={"common_json_pending_block_ids": "S9:TABLE:TAB_2_02"})
    warnings = _build(s2, s).warnings
    assert any("S9:THEORY:TH_1_00" in w and "학습목표" in w for w in warnings)
    assert any("S9:TABLE:TAB_2_02" in w and "수정본" in w for w in warnings)


def test_stale_duplicate_relation_is_warning_not_error(settings, sample):
    """관계에는 duplicate_of_table_id가 남았는데 블록 필드가 없으면 경고만 하고, 중복 판단은 블록 필드로 한다."""
    s = copy.deepcopy(sample)
    del s["blocks"]["blocks"][2]["duplicate_of_table_id"]
    data = _build(settings, s)
    assert _by_id(data)["S9:THEORY:TH_2_01"].search_enabled
    assert [w for w in data.warnings if "BREL_2" in w and "duplicate_of_table_id" in w]
    # 필드는 있는데 관계가 없는 경우는 정상(경고 없음)
    s2 = copy.deepcopy(sample)
    s2["relations"]["block_relations"].pop(1)
    assert _build(settings, s2).warnings == []


# ----- 임베딩 텍스트 -----

def test_theory_text_is_path_plus_clean(settings, sample):
    b = sample["blocks"]["blocks"][1]
    assert embedding_text(b) == "1장 가짜 장 > TH_1_01 제목\n\n가나다 설명 문장이다."


def test_table_without_headers_uses_first_cell_as_row_name():
    t = {"headers": [], "row_headers": ["무시"], "rows": [["행가\n(A)", "• 값1\n• 값2", ""], ["행나", "값3", "값4"]]}
    assert linearize_table(t) == "- 행가 (A): • 값1 • 값2\n- 행나: 값3 / 값4"


def test_table_with_headers_fills_merged_and_units():
    t = {"headers": ["구분", "", "비고"], "rows": [["갑", "을", "병"], ["정", "", "무"]],
         "merged_cells": [{"start_row": 0, "end_row": 1, "start_col": 1, "end_col": 1, "text": "을"}],
         "units": ["%", ""]}
    assert linearize_table(t) == "- 구분: 갑 | 을 | 비고: 병\n- 구분: 정 | 을 | 비고: 무\n단위: %"
    assert t["rows"][1][1] == ""  # 원본 rows는 바꾸지 않음


def test_table_text_uses_rows_not_raw_text(settings, sample):
    text = embedding_text(sample["blocks"]["blocks"][3])
    assert text.startswith("1장 가짜 장 > 가짜 표\n[표] 가짜 표\n- 행가 (A)")
    assert "원문 목록" not in text


def test_visual_text_excludes_related_theory_context(sample):
    text = embedding_text(sample["blocks"]["blocks"][5])
    assert text == ("1장 가짜 장 > 가짜 그림\n[그림] 가짜 그림\n설명: 가가 나나를 가리킨다.\n구조: 위아래 2칸\n"
                    "그림 속 글자: 가 · 나 다")
    assert "이론 문맥" not in text and "관찰" not in text


def test_table_text_fixed_output(sample):
    # 기본 출력은 DB에 저장된 임베딩 텍스트와 같아야 한다(바뀌면 재임베딩) — 이론·시각자료는 위 두 테스트가 고정
    assert embedding_text(sample["blocks"]["blocks"][3]) == (
        "1장 가짜 장 > 가짜 표\n[표] 가짜 표\n- 행가 (A): • 값1 • 값2\n- 행나: 값3")


def test_without_path_drops_only_title_path(sample):
    blocks = sample["blocks"]["blocks"]
    assert embedding_text(blocks[1], with_path=False) == "가나다 설명 문장이다."
    for b in (blocks[3], blocks[4], blocks[5]):
        full = embedding_text(b)
        assert full == f"{' > '.join(b['title_path'])}\n{embedding_text(b, with_path=False)}"


def test_block_from_row_rebuilds_same_text(settings, sample):
    """DB 행(컬럼)만으로 원본 블록과 같은 텍스트가 나온다(검색 때 LLM용 텍스트를 다시 만들 때 사용)."""
    from dataclasses import asdict

    from app.ingestion.common_json import block_from_row

    for rec in _build(settings, sample).blocks:
        row = asdict(rec)
        assert embedding_text(block_from_row(row)) == rec.embedding_text


def test_model_generated_not_in_embedding_text(settings, sample):
    rec = _by_id(_build(settings, sample))["S9:THEORY:TH_1_01"]
    assert "키워드" not in rec.embedding_text and "단서" not in rec.embedding_text


def test_resolve_duplicate():
    assert resolve_duplicate("TAB_104_01", 2) == "S2:TABLE:TAB_104_01"
    assert resolve_duplicate("S2:TABLE:TAB_104_01", 2) == "S2:TABLE:TAB_104_01"


# ----- 검증 실패 -----

def test_duplicate_block_id(settings, sample):
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"].append(copy.deepcopy(s["blocks"]["blocks"][1]))
    assert any("block_id 중복" in e for e in _errors(settings, s))


def test_missing_relation_endpoint_and_link_type(settings, sample):
    s = copy.deepcopy(sample)
    s["relations"]["block_relations"].append(_rel("BREL_4", "S9:THEORY:TH_1_01", "S9:TABLE:TAB_9_99", "THEORY_TO_TABLE"))
    s["relations"]["block_relations"][0]["link_type"] = "THEORY_TO_VISUAL"
    errors = _errors(settings, s)
    assert any("BREL_4" in e and "끝점" in e for e in errors)
    assert any("BREL_1" in e and "link_type" in e for e in errors)


def test_duplicate_relation_id_and_pair(settings, sample):
    s = copy.deepcopy(sample)
    s["relations"]["block_relations"].append(copy.deepcopy(s["relations"]["block_relations"][0]))
    errors = _errors(settings, s)
    assert any("relationship_id 중복" in e for e in errors)
    assert any("관계 중복" in e for e in errors)


def test_bad_duplicate_target(settings, sample):
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][2]["duplicate_of_table_id"] = "TAB_9_99"
    assert any("duplicate_of_table_id" in e for e in _errors(settings, s))


@pytest.mark.parametrize(
    "index, change, expected",
    [
        (1, {"block_type": "chart"}, "적재 규칙이 없는 block_type"),
        (1, {"title_path": ["한 단계"]}, "title_path"),
        (1, {"clean_text": ""}, "clean_text"),
        (1, {"block_role": "summary"}, "block_role"),
        (1, {"subject": 8}, "subject"),
        (1, {"source_id": "TH_X"}, "source_id"),
        (1, {"printed_page_number": "1"}, "printed_page_number"),
        (3, {"image": {"s3_bucket": "b"}}, "image"),
        (5, {"visual_description": "", "visual_structure": None, "raw_text": []}, "시각자료"),
    ],
)
def test_required_fields(settings, sample, index, change, expected):
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][index].update(change)
    assert any(expected in e for e in _errors(settings, s))


def test_table_shape_errors(settings, sample):
    s = copy.deepcopy(sample)
    t = s["blocks"]["blocks"][4]["table"]
    t["rows"][1] = ["정", "무"]  # headers 3칸과 다름
    t["merged_cells"].append({"start_row": 5, "end_row": 6, "start_col": 0, "end_col": 0, "text": "x"})
    errors = _errors(settings, s)
    assert any("headers" in e for e in errors)
    assert any("merged_cells" in e for e in errors)


def test_file_level_checks(settings, sample):
    s = copy.deepcopy(sample)
    s["report"] = {"passed": False, "errors": ["x"]}
    s["relations"]["format"] = "other"
    s["blocks"]["pages"][0]["block_ids_in_reading_order"] = ["S9:THEORY:TH_7_07"]
    errors = _errors(settings, s)
    assert any("passed=false" in e for e in errors)
    assert any("format" in e for e in errors)
    assert any("reading_order" in e for e in errors)


# ----- 적재 계획(바뀐 블록만 임베딩) -----

def _existing(rec, **kw):
    base = dict(content_hash=rec.content_hash, embedding_text_hash=rec.embedding_text_hash,
                has_embedding=rec.search_enabled, embedding_model="m", search_enabled=rec.search_enabled)
    base.update(kw)
    return ExistingBlock(**base)


def test_plan_new_blocks_embed_only_searchable(settings, sample):
    data = _build(settings, sample)
    plans = {p.record.block_id: p for p in plan_blocks(data.blocks, {}, "m")}
    assert all(p.status == "new" for p in plans.values())
    assert sum(p.embed for p in plans.values()) == 4
    assert not plans["S9:THEORY:TH_1_00"].embed and not plans["S9:THEORY:TH_1_00"].clear_embedding


def test_plan_rerun_is_noop(settings, sample):
    data = _build(settings, sample)
    existing = {r.block_id: _existing(r) for r in data.blocks}
    plans = plan_blocks(data.blocks, existing, "m")
    assert {p.status for p in plans} == {"unchanged"}
    assert not any(p.embed or p.clear_embedding for p in plans)


def test_plan_changed_text_model_and_exclusion(settings, sample):
    data = _build(settings, sample)
    existing = {r.block_id: _existing(r) for r in data.blocks}
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][4]["table"]["rows"][0][2] = "바뀐 값"  # 표 수정본
    changed = _build(settings, s)
    plans = {p.record.block_id: p for p in plan_blocks(changed.blocks, existing, "m")}
    assert plans["S9:TABLE:TAB_2_02"].status == "changed" and plans["S9:TABLE:TAB_2_02"].embed
    assert sum(p.embed for p in plans.values()) == 1

    # 임베딩 모델이 바뀌면 검색 대상 전부 다시
    assert sum(p.embed for p in plan_blocks(data.blocks, existing, "m2")) == 4

    # 검색 대상이던 블록이 제외되면 임베딩을 지운다
    existing["S9:THEORY:TH_1_00"] = _existing(data.blocks[0], has_embedding=True, search_enabled=True)
    p0 = plan_blocks(data.blocks, existing, "m")[0]
    assert p0.status == "changed" and p0.clear_embedding and not p0.embed


def test_raw_text_only_change_updates_row_without_reembedding(settings, sample):
    data = _build(settings, sample)
    existing = {r.block_id: _existing(r) for r in data.blocks}
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][1]["raw_text"] = "원문만 바뀜"
    p = plan_blocks(_build(settings, s).blocks, existing, "m")[1]
    assert p.status == "changed" and not p.embed


def test_select_blocks(settings, sample):
    data = _build(settings, sample)
    assert [r.block_id for r in select_blocks(data, ["S9:TABLE:TAB_2_02"])] == ["S9:TABLE:TAB_2_02"]
    with pytest.raises(CommonJsonError):
        select_blocks(data, ["S9:TABLE:TAB_9_99"])


# ----- 파일 읽기·CLI(DB 없음) -----

def _write_subject(root, s):
    folder = root / "subject9"
    folder.mkdir(parents=True)
    for name, key in (("blocks", "blocks"), ("relations", "relations"), ("manifest", "manifest"),
                      ("validation_report", "report")):
        (folder / f"t_subject9_{name}.json").write_text(json.dumps(s[key], ensure_ascii=False), encoding="utf-8")
    return folder


def test_read_subject_from_files(settings, sample, tmp_path):
    _write_subject(tmp_path, sample)
    data = read_subject(settings, tmp_path, "subject9")
    assert len(data.blocks) == 6
    assert data.files["blocks"] == "t_subject9_blocks.json"


def test_read_subject_missing_relations_file(settings, sample, tmp_path):
    folder = _write_subject(tmp_path, sample)
    (folder / "t_subject9_relations.json").unlink()
    with pytest.raises(CommonJsonError, match="_relations.json"):
        read_subject(settings, tmp_path, "subject9")


def test_cli_dry_run_no_db_writes_report(settings, sample, tmp_path, capsys):
    _write_subject(tmp_path / "cj", sample)
    s2 = settings.model_copy(update={"reports_dir": tmp_path / "reports"})
    assert main(["--subject", "all", "--no-db", "--dir", str(tmp_path / "cj"), "--show", "S9:TABLE:TAB_2_01"], s2) == 0
    out = capsys.readouterr().out
    assert "검색 대상 4" in out and "[표] 가짜 표" in out
    reports = list((tmp_path / "reports" / "common_json").glob("*_dry-run-no-db.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["subjects"]["subject9"]["plan"]["embed"] == 4


def test_cli_validation_failure_returns_1(settings, sample, tmp_path, capsys):
    s = copy.deepcopy(sample)
    s["relations"]["block_relations"][0]["to_block_id"] = "S9:TABLE:TAB_9_99"
    _write_subject(tmp_path, s)
    s2 = settings.model_copy(update={"reports_dir": tmp_path / "reports"})
    assert main(["--subject", "subject9", "--no-db", "--dir", str(tmp_path)], s2) == 1
    assert "검증 실패" in capsys.readouterr().out
    assert not (tmp_path / "reports").exists()


def test_cli_block_id_of_other_subject(settings, sample, tmp_path, capsys):
    _write_subject(tmp_path, sample)
    s2 = settings.model_copy(update={"reports_dir": tmp_path / "reports"})
    assert main(["--subject", "subject9", "--no-db", "--dir", str(tmp_path), "--block-id", "S1:TABLE:TAB_1_01"], s2) == 1


@pytest.mark.parametrize("argv", [["--apply", "--no-db"], ["--delete", "--prune"], ["--prune", "--block-id", "x"]])
def test_cli_rejects_bad_option_combinations(argv):
    with pytest.raises(SystemExit):
        main(["--subject", "subject9", *argv])


# ----- 코드·수식, 이미지 키, 원문 해시 (D-M-034) -----

def _with(sample, *blocks):
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"] += list(blocks)
    return s


def test_code_text_fixed_output():
    assert embedding_text(_code("CODE_2_01", 2)) == (
        "1장 가짜 장 > 가짜 코드\n[코드] 가짜 코드\nx <- 1\nx\n실행 결과:\n[1] 1")
    assert embedding_text(_code("CODE_2_01", 2), with_path=False) == "[코드] 가짜 코드\nx <- 1\nx\n실행 결과:\n[1] 1"
    # 실행 결과 없음 / 코드 없음(실행 결과만)
    assert embedding_text(_code("CODE_2_02", 2, execution_output="")) == (
        "1장 가짜 장 > 가짜 코드\n[코드] 가짜 코드\nx <- 1\nx")
    assert embedding_text(_code("CODE_2_03", 2, clean_code="")) == (
        "1장 가짜 장 > 가짜 코드\n[코드] 가짜 코드\n실행 결과:\n[1] 1")


def test_formula_text_fixed_output():
    assert embedding_text(_formula("FORM_2_01", 2)) == "1장 가짜 장 > 가짜 수식\n[수식] 가짜 수식\na / b"
    # plain_text가 없으면 latex 그대로
    assert embedding_text(_formula("FORM_2_02", 2, plain_text=None), with_path=False) == (
        "[수식] 가짜 수식\n" + r"\frac{a}{b}")


def test_code_formula_build_and_rebuild_from_row(settings, sample):
    from dataclasses import asdict

    from app.ingestion.common_json import block_display_text, block_from_row

    s = _with(sample, _code("CODE_2_01", 2), _code("CODE_2_02", 2, clean_code="", raw_code=""),
              _formula("FORM_2_01", 2))
    s["relations"]["block_relations"].append(
        _rel("BREL_9", "S9:THEORY:TH_1_01", "S9:CODE:CODE_2_01", "THEORY_TO_CODE"))
    data = _build(settings, s)
    b = _by_id(data)
    assert len(data.relations) == 4
    assert b["S9:CODE:CODE_2_01"].search_enabled and b["S9:FORMULA:FORM_2_01"].search_enabled
    assert b["S9:CODE:CODE_2_01"].block_role == "content"
    assert b["S9:CODE:CODE_2_01"].source["clean_code"] == "x <- 1\nx\n"  # 원본 필드는 source 칸에
    assert b["S9:FORMULA:FORM_2_01"].image is None and b["S9:FORMULA:FORM_2_01"].crop_s3_key is None
    for rec in data.blocks:  # DB 행(source 포함)만으로 같은 텍스트
        assert embedding_text(block_from_row(asdict(rec))) == rec.embedding_text
    # 근거 표시: raw_text가 비면 코드는 clean_code, 수식은 plain_text
    assert block_display_text(asdict(b["S9:CODE:CODE_2_01"])) == "x <- 1\nx\n"
    assert block_display_text(asdict(b["S9:FORMULA:FORM_2_01"])) == r"\frac{a}{b}"  # 원문이 있으면 원문
    assert block_display_text({"block_type": "formula", "raw_text": None, "source": {"plain_text": "a / b"}}) == "a / b"
    assert block_display_text(asdict(b["S9:TABLE:TAB_2_01"])) == "원문 목록"


def test_code_formula_required_fields(settings, sample):
    errors = _errors(settings, _with(sample, _code("CODE_2_01", 2, clean_code="", execution_output=" "),
                                     _formula("FORM_2_01", 2, plain_text="", latex=None),
                                     _code("CODE_2_02", 2, image=None)))
    assert any("CODE_2_01" in e and "clean_code" in e for e in errors)
    assert any("FORM_2_01" in e and "plain_text" in e for e in errors)
    assert any("CODE_2_02" in e and "image" in e for e in errors)


def test_crop_key_falls_back_between_names(settings, sample):
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][3]["image"] = {"s3_bucket": "b", "s3_region": "r", "crop_s3_key": "k/c2.jpg",
                                         "thumbnail_s3_key": "k/t.jpg"}
    s["blocks"]["blocks"][4]["image"] = dict(IMAGE, crop_s3_key="k/c3.jpg")
    b = _by_id(_build(settings, s))
    assert b["S9:TABLE:TAB_2_01"].crop_s3_key == "k/c2.jpg"  # crop_s3_key 이름
    assert b["S9:TABLE:TAB_2_02"].crop_s3_key == "k/c3.jpg"  # 둘 다 있으면 crop_s3_key 우선
    assert b["S9:VISUAL:VIS_2_01"].crop_s3_key == "k/crop.jpg"  # original_s3_key만(1~3과목 파일)
    s["blocks"]["blocks"][3]["image"] = {"s3_bucket": "b", "s3_region": "r", "thumbnail_s3_key": "k/t.jpg"}
    assert any("TAB_2_01" in e and "image" in e for e in _errors(settings, s))


def test_table_dict_rows_and_col_index_merged_cells(settings, sample):
    """3과목 표 형태: rows가 {머리: 값} 목록 / merged_cells가 col_index. 저장은 원본 그대로."""
    dict_rows = {"headers": [], "row_headers": [], "merged_cells": [], "units": [],
                 "rows": [{"구분": "장점", "설명": "가"}, {"구분": "단점", "설명": "나"}]}
    assert linearize_table(dict_rows) == "- 구분: 장점 | 설명: 가\n- 구분: 단점 | 설명: 나"
    col_index = {"headers": ["구분", "값"], "rows": [["갑", "1"], ["", "2"]],
                 "merged_cells": [{"start_row": 0, "end_row": 1, "col_index": 0, "text": "갑"}]}
    assert linearize_table(col_index) == "- 구분: 갑 | 값: 1\n- 구분: 갑 | 값: 2"
    s = copy.deepcopy(sample)
    s["blocks"]["blocks"][3]["table"] = dict_rows
    s["blocks"]["blocks"][4]["table"] = col_index
    b = _by_id(_build(settings, s))
    assert b["S9:TABLE:TAB_2_01"].table_data == dict_rows
    assert b["S9:TABLE:TAB_2_02"].embedding_text.endswith("- 구분: 갑 | 값: 1\n- 구분: 갑 | 값: 2")


def test_source_clean_text_hash_filled(settings, sample):
    from app.core.text_hash import clean_text_hash

    b = _by_id(_build(settings, _with(sample, _code("CODE_2_01", 2), _formula("FORM_2_01", 2))))
    assert b["S9:THEORY:TH_1_01"].source_clean_text_hash == clean_text_hash("가나다 설명 문장이다.")
    assert b["S9:FORMULA:FORM_2_01"].source_clean_text_hash == clean_text_hash(r"\frac{a}{b}")
    assert b["S9:TABLE:TAB_2_01"].source_clean_text_hash is None  # clean_text 없음(005 백필과 같은 규칙)
    assert b["S9:CODE:CODE_2_01"].source_clean_text_hash is None
