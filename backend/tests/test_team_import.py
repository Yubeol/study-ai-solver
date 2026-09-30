"""팀 교재 반입 계획(build_plan) 테스트. 실제 PDF·DB 없이 계획 로직만 확인한다."""

import unicodedata

from app.ingestion.team_import import build_plan, footer_numbers, footer_matches


def _cfg(**kw):
    base = {
        "key": "t",
        "pdf": "pdf/t.pdf",
        "text_dir": "team_text/t",
        "subject": "ADsP",
        "title": "테스트",
        "source_name": "team_import:t.pdf",
        "segments": [{"pdf_from": 1, "pdf_to": 3, "offset": 9}],
    }
    base.update(kw)
    return base


def test_constant_offset():
    texts = {f"과1-{p}p.txt": f"본문\n\n{p}" for p in (10, 11, 12)}
    plan = build_plan(_cfg(), 3, texts)
    assert plan.errors == []
    assert [(p.pdf_index, p.printed, p.status) for p in plan.pages] == [
        (1, 10, "EXTRACTED"),
        (2, 11, "EXTRACTED"),
        (3, 12, "EXTRACTED"),
    ]
    assert all(p.footer_check == "match" for p in plan.pages)


def test_missing_text_is_review_required():
    texts = {"과1-10p.txt": "a", "과1-12p.txt": "c"}
    plan = build_plan(_cfg(), 3, texts)
    p11 = plan.pages[1]
    assert (p11.printed, p11.status, p11.reason) == (11, "REVIEW_REQUIRED", "team_text 없음")
    assert p11.text_file is None


def test_merged_text_file_goes_to_first_page():
    cfg = _cfg(text_files={"과1-10-11p.txt": {"pages": [10, 11]}})
    texts = {"과1-10-11p.txt": "ab", "과1-12p.txt": "c"}
    plan = build_plan(cfg, 3, texts)
    assert plan.errors == []
    assert plan.pages[0].text_file == "과1-10-11p.txt" and plan.pages[0].covers_pages == [10, 11]
    assert plan.pages[1].status == "REVIEW_REQUIRED" and "합쳐져" in plan.pages[1].reason


def test_multi_page_name_without_override_is_error():
    plan = build_plan(_cfg(), 3, {"과1-10-11p.txt": "ab", "과1-12p.txt": "c"})
    assert any("text_files" in e for e in plan.errors)


def test_skip_and_offset_change():
    # 4장: 1~2장 +9, 3장 중복 건너뜀, 4장 +8 → 10, 11, 12
    cfg = _cfg(
        segments=[{"pdf_from": 1, "pdf_to": 2, "offset": 9}, {"pdf_from": 4, "pdf_to": 4, "offset": 8}],
        skip_pdf=[{"pdf": 3, "reason": "중복"}],
    )
    texts = {f"과1-{p}p.txt": "x" for p in (10, 11, 12)}
    plan = build_plan(cfg, 4, texts)
    assert plan.errors == []
    assert [(p.pdf_index, p.printed) for p in plan.pages] == [(1, 10), (2, 11), (4, 12)]


def test_unmapped_pdf_page_and_duplicate_printed_are_errors():
    cfg = _cfg(segments=[{"pdf_from": 1, "pdf_to": 2, "offset": 9}, {"pdf_from": 3, "pdf_to": 3, "offset": 8}])
    plan = build_plan(cfg, 4, {})
    assert any("매핑 없는 PDF 장" in e for e in plan.errors)
    assert any("중복" in e for e in plan.errors)


def test_unused_text_is_error():
    texts = {f"과1-{p}p.txt": "x" for p in (10, 11, 12, 99)}
    plan = build_plan(_cfg(), 3, texts)
    assert any("연결되지 않은 텍스트" in e for e in plan.errors)


def test_nfd_filenames_are_normalized():
    name = unicodedata.normalize("NFD", "과1-10p.txt")
    plan = build_plan(_cfg(segments=[{"pdf_from": 1, "pdf_to": 1, "offset": 9}]), 1, {name: "x"})
    assert plan.errors == [] and plan.pages[0].text_file == "과1-10p.txt"


def test_text_is_not_modified_by_footer_check():
    text = "본문\n\n3장 가치창조 |\n\n57"
    assert footer_numbers(text) == [57]
    assert footer_matches(127, [27]) and footer_matches(661, [66]) and not footer_matches(5, [27])
