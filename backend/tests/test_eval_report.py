"""검색 평가 HTML 보고서 렌더링·썸네일. DB·모델 없이 돈다."""

import cv2
import numpy as np

from app.retrieval.eval_report import make_thumbnail, render_html


def _top(rank, subject, page, gold, **extra):
    return {
        "rank": rank, "score": 0.61 - rank / 100, "subject": subject, "page": page, "title": "제목<b>",
        "chunk_id": f"c{rank}", "text": "본문 <script>x</script>", "missing_chunk": False, "gold": gold,
        "thumb": f"thumbs/p{page}.jpg", **extra,
    }


def _data():
    return {
        "config": {"k": 2},
        "questions": [
            {"id": "q1", "question": "A와 B 차이?", "subject": "subject1", "pages": ["18"], "note": "draft 비교",
             "rank": 2, "top_score": 0.6, "gold_pages": [{"page": "18", "thumb": "thumbs/g.jpg", "full": "../../storage/x.jpg"}],
             "top": [_top(1, "subject3", "200", False), _top(2, "subject1", "18", True)]},
            {"id": "q2", "question": "틀린 질문", "subject": "subject2", "pages": ["90"], "note": "",
             "rank": None, "top_score": 0.5, "gold_pages": [{"page": "90", "thumb_error": "FileNotFoundError: x"}],
             "top": [_top(1, "subject2", "91", False, missing_chunk=True)]},
            {"id": "n1", "question": "자료에 없는 질문", "subject": "", "pages": [], "note": "boundary",
             "rank": None, "top_score": 0.45, "gold_pages": [], "top": [_top(1, "subject3", "300", False)]},
        ],
    }


def test_render_html_marks_kinds_gold_rows_and_escapes():
    html = render_html(_data(), "요약 <텍스트>", "검색 평가 t")
    assert html.count('class=q data-kind="hit"') == 1
    assert html.count('class=q data-kind="miss"') == 1
    assert html.count('class=q data-kind="none"') == 1
    assert "정답 2위" in html and "순위 깊이 안에 없음" in html and "자료에 없음 · 1위 0.450" in html
    assert html.count("<tr class=g>") == 1  # 정답 쪽 청크 행만 강조
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert "요약 &lt;텍스트&gt;" in html
    assert 'href="../../storage/x.jpg"' in html  # 원본 링크
    assert "FileNotFoundError" in html and "청크 없음" in html
    assert "K 밖(틀림) 1" in html and "전체 3" in html


def test_make_thumbnail_resizes_to_width_keeping_ratio():
    img = np.full((400, 800, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    thumb = cv2.imdecode(np.frombuffer(make_thumbnail(buf.tobytes(), 200), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert thumb.shape[:2] == (100, 200)
    small = cv2.imdecode(np.frombuffer(make_thumbnail(buf.tobytes(), 1000), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert small.shape[:2] == (400, 800)  # 작으면 키우지 않음


def test_render_html_shows_block_label():
    data = _data()
    data["questions"][0]["top"][0] |= {"corpus": "common_json", "kind": "table", "block_id": "S1:TABLE:T<1>"}
    html = render_html(data, "", "t")
    assert "[table] S1:TABLE:T&lt;1&gt;" in html
