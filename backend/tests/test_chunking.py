"""이론 청킹 규칙(D-019)과 chunk_theory 단계.

교재 원문은 커밋하지 않으므로 교재 형식만 흉내 낸 가짜 문장을 쓴다.
"""

import json
import uuid

import pytest
from psycopg import sql

from app.ingestion import chunking
from app.ingestion.chunking import ChunkParams, ChunkState, chunk_page, frequency_items, is_page_furniture
from app.ingestion.pipeline import Stage, process_page
from app.ingestion.stages import PageContext, chunk_theory, text_key
from app.repositories import books as books_repo
from app.repositories import pages as pages_repo
from app.storage.local import LocalStorage

PARAMS = ChunkParams(max_chars=200, overlap_chars=60, min_chars=20, heading_max_chars=60)

PAGE_A = """1장

가짜 개론

01 첫째 절

학습목표

첫째 절의 개념을 알아본다.

5년간 출제 횟수 중요도 ① 개념 가★③ 개념 다★

② 개념 나★④ 개념 라★★

1. 개념 가의 정의 (★기출)

개념 가는 설명을 위한 가짜 문장이다. 두 번째 문장도 가짜다.

기출유형 개념잡기

1 다음 중 개념 가에 대한 설명으로 옳지 않은 것은? [99회 출제]

① 보기 하나 ② 보기 둘

정답 ② 해설 가짜 해설이다.

2. 개념 나 (★★기출)

개념 나는 (기출) 표시가 붙은 가짜 문장이다.

1과목 가짜 과목

|

14"""

PAGE_B = """2024 ADSP 한 권으로 끝내기 이론편

앞 페이지에서 이어지는 개념 나의 본문이다.

1) 세부 항목•제목 뒤에 본문이 붙은 줄이다.

1장 가짜 개론 |

15"""


def test_page_furniture():
    assert is_page_furniture("2024 ADsP 한 권으로 끝내기 이론편", "20")
    assert is_page_furniture("117m 2024 ADSP 한 권으로 끝내기 이론편", "20")
    assert is_page_furniture("|", "20")
    assert is_page_furniture("| 15", "15")
    assert is_page_furniture("127", "27")  # "|27"의 |가 1로 읽힌 쪽번호(D-018)
    assert is_page_furniture("3과목 데이터 분석", "226")
    assert is_page_furniture("7장 통계분석 |", "217")
    assert not is_page_furniture("128", "27")
    assert not is_page_furniture("데이터는 사실이다.", "27")


def test_frequency_items():
    items = frequency_items("5년간 출제 횟수 중요도 ① 데이터의 정의★③ DIKW 정의 및 사례★★")
    assert items == [{"topic": "데이터의 정의", "stars": 1}, {"topic": "DIKW 정의 및 사례", "stars": 2}]


def test_chunk_page_texts_clues_and_exam_block():
    r = chunk_page(PAGE_A.splitlines(), "14", ChunkState(), PARAMS)

    assert [c.title for c in r.chunks] == ["1. 개념 가의 정의", "2. 개념 나"]
    first, second = r.chunks
    assert first.path == ["1장 가짜 개론", "01 첫째 절", "1. 개념 가의 정의"]
    # raw_text는 원문 그대로(기출 표시·학습목표 포함), 머리말/쪽번호 줄은 없음
    assert "1. 개념 가의 정의 (★기출)" in first.raw_text
    assert "학습목표" in first.raw_text
    # clean_text는 기출 표시·학습목표·출제 횟수를 뺀다
    assert "★" not in first.clean_text and "학습목표" not in first.clean_text
    assert "5년간" not in first.clean_text
    assert first.embedding_text.startswith("1장 가짜 개론 > 01 첫째 절 > 1. 개념 가의 정의\n\n")
    types = [c["type"] for c in first.exam_clues]
    assert types.count("frequency") == 2 and "learning_goal" in types and "heading_mark" in types
    # 기출 문제 블록은 청크에 들어가지 않고 제외 구간으로
    assert all("보기" not in c.raw_text for c in r.chunks)
    assert len(r.excluded) == 1
    assert r.excluded[0].title == "기출유형 개념잡기 [99회 출제]"
    assert not r.excluded[0].continued
    # "(기출)"만 있는 줄도 표시(별 0개)로 잡고 clean_text에서 뺀다
    assert "(기출)" not in second.clean_text
    assert {"type": "heading_mark", "heading": "2. 개념 나", "stars": 2} in second.exam_clues
    assert any(c["type"] == "exam_mark" and c["stars"] == 0 for c in second.exam_clues)
    assert r.end_state.path["item"] == "2. 개념 나" and not r.end_state.in_exam


def test_heading_path_carries_to_next_page():
    a = chunk_page(PAGE_A.splitlines(), "14", ChunkState(), PARAMS)
    state = ChunkState.from_json(json.loads(json.dumps(a.end_state.to_json())))  # DB 저장 왕복
    b = chunk_page(PAGE_B.splitlines(), "15", state, PARAMS)

    assert b.chunks[0].path == ["1장 가짜 개론", "01 첫째 절", "2. 개념 나"]
    # 이어받은 제목의 기출 표시는 inherited로 붙는다
    assert b.chunks[0].exam_clues[0] == {"type": "heading_mark", "heading": "2. 개념 나", "stars": 2, "inherited": True}
    # "제목•본문" 줄은 제목과 본문으로 나뉘고, raw_text에는 원문 줄 한 번만
    last = b.chunks[-1]
    assert last.title == "1) 세부 항목"
    assert last.clean_text == "1) 세부 항목\n•제목 뒤에 본문이 붙은 줄이다."
    assert last.raw_text == "1) 세부 항목•제목 뒤에 본문이 붙은 줄이다."
    assert all("이론편" not in c.raw_text and "|" not in c.raw_text for c in b.chunks)


def test_exam_block_continues_only_when_next_page_looks_like_exam():
    ends_in_exam = "1. 가\n\n본문 문장이다.\n\n기출유형 개념잡기\n\n3 다음 중 옳은 것은?"
    a = chunk_page(ends_in_exam.splitlines(), None, ChunkState(), PARAMS)
    assert a.end_state.in_exam

    cont = chunk_page("[98회 출제]\n정답 ①\n2. 나\n나의 본문이다.".splitlines(), None, a.end_state, PARAMS)
    assert cont.excluded[0].continued and cont.excluded[0].line_range == [0, 1]
    assert [c.title for c in cont.chunks] == ["2. 나"]

    theory = chunk_page("앞 절에 이어지는 이론 본문이다.".splitlines(), None, a.end_state, PARAMS)
    assert not theory.excluded
    assert theory.chunks[0].clean_text == "앞 절에 이어지는 이론 본문이다."


def test_long_section_splits_with_overlap_inside_page():
    body = [f"{i}번째 문단은 청크 나누기를 확인하기 위한 가짜 문장이다." for i in range(12)]
    r = chunk_page(["1. 긴 절", *body], None, ChunkState(), PARAMS)

    assert len(r.chunks) > 1
    assert all(len(c.clean_text) <= PARAMS.max_chars + 40 for c in r.chunks)
    assert all(c.title == "1. 긴 절" for c in r.chunks)
    assert [c.sort_order for c in r.chunks] == list(range(len(r.chunks)))
    # 겹침: 다음 조각은 앞 조각의 마지막 문단으로 시작한다
    first_last = r.chunks[0].clean_text.splitlines()[-1]
    assert r.chunks[1].clean_text.splitlines()[0] == first_last


def test_decimal_numbers_are_not_headings():
    assert chunking.parse_heading("3.5", 60) is None
    assert chunking.parse_heading("1. 개별 데이터 자체로는 의미가 중요하지 않은 객관적인 사실이다.", 60) is None
    assert chunking.parse_heading("03빅데이터 그리고 미래", 60)[0] == "section"


# ---------- chunk_theory 단계 (공유 DB 필요) ----------


@pytest.fixture
def team_text_book(db_conn, settings, tmp_path):
    """팀 텍스트로 반입된 것과 같은 모양의 book 1개 + 페이지 2장(EXTRACTED)."""
    storage = LocalStorage(tmp_path / "저장소")
    book = books_repo.create_book(
        db_conn, settings, title="청킹 테스트", subject="__pytest_subject__", material_type="textbook"
    )
    pages = []
    for idx, (text, printed) in enumerate([(PAGE_A, "14"), (PAGE_B, "15")]):
        page_id = uuid.uuid4()
        data = json.dumps({"engine": "team_text", "text": text}, ensure_ascii=False).encode("utf-8")
        uri = storage.save(text_key(book["id"], page_id), data)
        pages.append(
            pages_repo.NewPage(
                id=page_id,
                source_uri=f"local://books/{book['id']}/{page_id}.jpg",
                width=10,
                height=10,
                upload_index=idx,
                original_filename=f"p{printed}",
                printed_page_number=printed,
                extra_metadata={"text": {"uri": uri, "engine": "team_text"}},
            )
        )
    s = sql.Identifier(settings.db_schema)
    run_id = db_conn.execute(
        sql.SQL("INSERT INTO {}.processing_runs (pipeline_version, page_count) VALUES ('pytest', 2) RETURNING id").format(s)
    ).fetchone()[0]
    pages_repo.insert_pages(db_conn, settings, book["id"], run_id, pages)
    db_conn.execute(
        sql.SQL("UPDATE {}.pages SET processing_status = 'EXTRACTED' WHERE book_id = %s").format(s), (book["id"],)
    )
    yield book, [p.id for p in pages], run_id, storage
    with db_conn.transaction():
        db_conn.execute(sql.SQL("DELETE FROM {}.books WHERE id = %s").format(s), (book["id"],))
        db_conn.execute(sql.SQL("DELETE FROM {}.processing_runs WHERE id = %s").format(s), (run_id,))


def _ctx(db_conn, settings, book, page_id, run_id, storage):
    return PageContext(
        page_id=page_id,
        book_id=book["id"],
        run_id=run_id,
        source_uri="",
        conn=db_conn,
        settings=settings,
        storage=storage,
    )


def _rows(db_conn, settings, table, page_id, cols):
    q = sql.SQL("SELECT {cols} FROM {s}.{t} WHERE page_id = %s ORDER BY 1").format(
        cols=sql.SQL(cols), s=sql.Identifier(settings.db_schema), t=sql.Identifier(table)
    )
    return db_conn.execute(q, (page_id,)).fetchall()


def test_chunk_theory_stage_saves_and_replaces(db_conn, settings, team_text_book):
    book, (pa, pb), run_id, storage = team_text_book
    stage = (Stage("chunk_theory", chunk_theory, "VERIFIED"),)
    extra = {"skipped": ["detect_visuals"]}

    for pid in (pa, pb):
        assert process_page(_ctx(db_conn, settings, book, pid, run_id, storage), stage, extra) == "DONE"

    rows = _rows(db_conn, settings, "theory_chunks", pa, "sort_order, title, embedding_text, needs_review, processing_run_id")
    assert [r[1] for r in rows] == ["1. 개념 가의 정의", "2. 개념 나"]
    assert all(r[3] is False and r[4] == run_id for r in rows)
    [(stype, title, regions)] = _rows(db_conn, settings, "excluded_sections", pa, "section_type, title, source_region_ids")
    assert (stype, title) == ("exam_question", "기출유형 개념잡기 [99회 출제]")
    # 원문 위치로 기출 텍스트를 복원할 수 있다
    [region] = regions
    text = json.loads(storage.read(region["text_uri"]).decode("utf-8"))["text"].splitlines()
    a, b = region["line_range"]
    assert text[a].startswith("기출유형 개념잡기") and text[b].startswith("정답")
    # 둘째 페이지는 DB에 저장된 첫 페이지 end_state에서 제목 경로를 이어받는다
    b_rows = _rows(db_conn, settings, "theory_chunks", pb, "sort_order, embedding_text")
    assert b_rows[0][1].startswith("1장 가짜 개론 > 01 첫째 절 > 2. 개념 나\n\n")

    q = sql.SQL("SELECT processing_status, page_metadata FROM {}.pages WHERE id = %s").format(
        sql.Identifier(settings.db_schema)
    )
    status, meta = db_conn.execute(q, (pb,)).fetchone()
    assert status == "VERIFIED"
    assert meta["pipeline"]["skipped"] == ["detect_visuals"]
    assert meta["chunking"]["prev_state"] == "previous"
    assert meta["chunking"]["chunk_count"] == len(b_rows)

    # 재실행: 지우고 다시 넣으므로 개수가 그대로
    assert process_page(_ctx(db_conn, settings, book, pa, run_id, storage), stage, extra) == "DONE"
    assert len(_rows(db_conn, settings, "theory_chunks", pa, "id")) == 2
    assert len(_rows(db_conn, settings, "excluded_sections", pa, "id")) == 1


def test_inherited_heading_mark_stops_when_heading_changes():
    page1 = "1. 가 (★★기출)\n가의 본문이다.".splitlines()
    a = chunk_page(page1, None, ChunkState(), PARAMS)
    # 같은 제목이 이어지는 다음 페이지에는 inherited로 붙는다
    b = chunk_page("가의 본문이 이어진다.".splitlines(), None, a.end_state, PARAMS)
    assert b.chunks[0].exam_clues == [{"type": "heading_mark", "heading": "1. 가", "stars": 2, "inherited": True}]
    # 같은 수준의 제목이 바뀌면 끊긴다(같은 페이지, 다음 페이지 모두)
    c = chunk_page("2. 나\n나의 본문이다.".splitlines(), None, b.end_state, PARAMS)
    assert c.chunks[0].exam_clues == []
    assert "item" not in c.end_state.marks
    d = chunk_page("나의 본문이 이어진다.".splitlines(), None, c.end_state, PARAMS)
    assert d.chunks[0].exam_clues == []
    # 하위 제목이 바뀌어도 상위 제목 표시는 남는다
    e = chunk_page("1) 세부 하나\n본문이다.\n2) 세부 둘\n본문이다.".splitlines(), None, a.end_state, PARAMS)
    assert all(c["heading"] == "1. 가" for ch in e.chunks for c in ch.exam_clues)


def test_short_low_hangul_chunk_needs_review():
    params = ChunkParams(max_chars=200, overlap_chars=60, min_chars=0, heading_max_chars=60,
                         review_max_chars=80, review_min_hangul_ratio=0.3)
    r = chunk_page("1) R의 기초\n>x=1\n> x+y\n[1] 3\n2) 설명\n짧아도 한글 본문이면 검색에 남긴다.".splitlines(), None, ChunkState(), params)
    assert [(c.title, c.needs_review, c.review_reasons) for c in r.chunks] == [
        ("1) R의 기초", True, ["short_low_hangul"]),  # 제목 한글은 비율 계산에서 뺀다
        ("2) 설명", False, []),
    ]
