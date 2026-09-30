"""검색 평가 HTML 보고서: 질문마다 정답 쪽, 상위 K개 청크(점수·쪽·텍스트 앞부분), 페이지 썸네일을 나란히 본다.

    cd backend
    uv run python -m app.retrieval.eval_report                      # data/reports/eval/ 의 가장 최근 json
    uv run python -m app.retrieval.eval_report ../data/reports/eval/20260930-190852.json

- 입력은 evaluate.py가 만든 json(평가 실행 시 자동으로 이 보고서도 만든다). DB는 읽기만 한다.
- 청크 텍스트·페이지 이미지는 DB/저장소에서 다시 읽는다. 평가 후 재청킹했으면 청크 id가 바뀌어 텍스트가 비어 보인다.
- 썸네일은 {REPORTS_DIR}/eval/thumbs/{page_id}.jpg(이미 있으면 재사용). 교재 이미지이므로 data/ 밖에 두지 않는다.
- 조정 값: EVAL_REPORT_THUMB_WIDTH(썸네일 가로 픽셀), EVAL_REPORT_TEXT_CHARS(청크 텍스트 앞부분 글자 수).
"""

import argparse
import json
import os
import sys
from html import escape
from pathlib import Path
from uuid import UUID

from app.core.config import Settings, get_settings

THUMB_DIR = "thumbs"


# ---------- DB·저장소에서 보고서 재료 모으기 ----------


def collect(conn, settings: Settings, report: dict, out_dir: Path) -> dict:
    """평가 json에 청크 텍스트·페이지 썸네일 경로를 붙인 보고서 데이터를 만든다."""
    from psycopg import sql
    from psycopg.rows import dict_row

    from app.retrieval.evaluate import _subject_book_ids

    k = report["config"]["k"]
    questions = report["questions"]
    book_ids = _subject_book_ids(conn, settings)
    s = sql.Identifier(settings.db_schema)

    chunk_ids = sorted({t["chunk_id"] for q in questions for t in q["top"][:k]})
    with conn.cursor(row_factory=dict_row) as cur:
        chunks = {
            str(r["id"]): r
            for r in cur.execute(
                sql.SQL(
                    "SELECT t.id, t.clean_text, p.id AS page_id, p.source_s3_uri "
                    "FROM {s}.theory_chunks t JOIN {s}.pages p ON p.id = t.page_id WHERE t.id = ANY(%s)"
                ).format(s=s),
                ([UUID(c) for c in chunk_ids],),
            ).fetchall()
        }
        gold_pages = {}  # (subject, 인쇄 쪽) → pages 행
        wanted = {(q["subject"], p) for q in questions for p in q["pages"]}
        for subj in {w[0] for w in wanted}:
            if subj not in book_ids:
                continue
            nums = [p for (sj, p) in wanted if sj == subj]
            for r in cur.execute(
                sql.SQL(
                    "SELECT id, printed_page_number, source_s3_uri FROM {s}.pages "
                    "WHERE book_id = %s AND printed_page_number = ANY(%s)"
                ).format(s=s),
                (book_ids[subj], nums),
            ).fetchall():
                gold_pages[(subj, str(r["printed_page_number"]))] = r

    thumbs = Thumbnailer(settings, out_dir)
    n_chars = settings.eval_report_text_chars
    items = []
    for q in questions:
        gold = []
        for p in q["pages"]:
            row = gold_pages.get((q["subject"], p))
            gold.append({"page": p, **(thumbs.get(row["id"], row["source_s3_uri"]) if row else {})})
        top = []
        for t in q["top"][:k]:
            c = chunks.get(t["chunk_id"])
            text = (c["clean_text"] or "") if c else ""
            top.append(
                {
                    **t,
                    "text": text[:n_chars] + ("…" if len(text) > n_chars else ""),
                    "missing_chunk": c is None,
                    "gold": bool(q["pages"]) and t["subject"] == q["subject"] and str(t["page"]) in q["pages"],
                    **(thumbs.get(c["page_id"], c["source_s3_uri"]) if c else {}),
                }
            )
        items.append({**q, "gold_pages": gold, "top": top})
    return {"config": report["config"], "summary": report["summary"], "questions": items}


class Thumbnailer:
    """페이지 원본을 줄여 out_dir/thumbs/{page_id}.jpg로 저장하고 보고서 기준 상대 경로를 돌려준다."""

    def __init__(self, settings: Settings, out_dir: Path):
        from app.storage import get_storage

        self.settings = settings
        self.storage = get_storage(settings)
        self.out_dir = out_dir
        self.dir = out_dir / THUMB_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, dict] = {}

    def get(self, page_id, source_uri: str) -> dict:
        key = str(page_id)
        if key not in self.cache:
            self.cache[key] = self._make(key, source_uri)
        return self.cache[key]

    def _make(self, page_id: str, source_uri: str) -> dict:
        path = self.dir / f"{page_id}.jpg"
        out = {"thumb": f"{THUMB_DIR}/{page_id}.jpg"}
        if not path.exists():
            try:
                path.write_bytes(make_thumbnail(self.storage.read(source_uri), self.settings.eval_report_thumb_width))
            except Exception as e:  # noqa: BLE001 - 썸네일 하나 실패로 보고서 전체를 멈추지 않는다
                return {"thumb_error": f"{type(e).__name__}: {e}"}
        if self.settings.storage_backend == "local" and source_uri.startswith("local://"):
            full = self.settings.storage_dir / source_uri[len("local://"):]
            out["full"] = Path(os.path.relpath(full, self.out_dir)).as_posix()
        return out


def make_thumbnail(data: bytes, width: int) -> bytes:
    import cv2

    from app.ingestion.images import decode_bgr

    img = decode_bgr(data)
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("JPEG 인코딩 실패")
    return buf.tobytes()


# ---------- HTML ----------

_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e2e2e0;--ok:#1f7a3f;--okbg:#e6f4ea;
--bad:#b3261e;--badbg:#fbe9e7;--warn:#8a5a00;--warnbg:#fff4d6;--gold:#fff8c5}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--card:#1f1f22;--fg:#ececec;--muted:#9a9aa0;--line:#333338;
--ok:#7bd88f;--okbg:#1d3324;--bad:#ff8a80;--badbg:#3a1f1d;--warn:#ffcf66;--warnbg:#3a3018;--gold:#3a3614}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
font:14px/1.5 "Malgun Gothic","Apple SD Gothic Neo",sans-serif}
h1{font-size:20px;margin:0 0 8px}pre{background:var(--card);border:1px solid var(--line);padding:12px;
overflow-x:auto;font-size:12px;border-radius:6px}
.filters{margin:12px 0;display:flex;gap:6px;flex-wrap:wrap}.filters button{border:1px solid var(--line);
background:var(--card);color:var(--fg);padding:4px 10px;border-radius:14px;cursor:pointer}
.filters button.on{background:var(--fg);color:var(--bg)}
.q{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}
.qh{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.qid{font-weight:700}
.qt{font-size:15px;font-weight:600}.meta{color:var(--muted);font-size:12px}
.badge{font-size:12px;padding:1px 8px;border-radius:10px;font-weight:600}
.hit{background:var(--okbg);color:var(--ok)}.miss{background:var(--badbg);color:var(--bad)}
.none{background:var(--warnbg);color:var(--warn)}
.gold-row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.gold-row figure{margin:0;text-align:center;font-size:12px}
table{border-collapse:collapse;width:100%;margin-top:8px}td,th{border-top:1px solid var(--line);padding:6px;
vertical-align:top;text-align:left}th{font-size:12px;color:var(--muted);font-weight:600}
tr.g td{background:var(--gold)}td.txt{font-size:13px;white-space:pre-wrap;word-break:break-all}
img.th{display:block;max-width:160px;height:auto;border:1px solid var(--line)}
.err{color:var(--bad);font-size:12px}
@media (max-width:700px){td.img{display:none}}
"""

_JS = """
document.querySelectorAll('.filters button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.filters button').forEach(x=>x.classList.toggle('on',x===b));
 const f=b.dataset.f;document.querySelectorAll('.q').forEach(q=>{
  q.style.display=(f==='all'||q.dataset.kind===f)?'':'none'})});
"""


def render_html(data: dict, summary_text: str, title: str) -> str:
    k = data["config"]["k"]
    counts: dict[str, int] = {}
    cards = []
    for q in data["questions"]:
        kind = _kind(q, k)
        counts[kind] = counts.get(kind, 0) + 1
        cards.append(_card(q, k, kind))
    labels = {"all": "전체", "miss": "K 밖(틀림)", "hit": "적중", "none": "자료에 없음"}
    total = len(data["questions"])
    buttons = "".join(
        f'<button data-f="{f}"{" class=on" if f == "all" else ""}>{lab} {total if f == "all" else counts.get(f, 0)}</button>'
        for f, lab in labels.items()
    )
    return (
        "<!doctype html><html lang=ko><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{escape(title)}</h1><pre>{escape(summary_text)}</pre>"
        f'<div class=filters>{buttons}</div>{"".join(cards)}<script>{_JS}</script></body></html>'
    )


def _kind(q: dict, k: int) -> str:
    if not q["pages"]:
        return "none"
    return "hit" if q["rank"] and q["rank"] <= k else "miss"


def _card(q: dict, k: int, kind: str) -> str:
    score = f"{q['top_score']:.3f}" if q["top_score"] is not None else "-"
    if q.get("rerank_top_score") is not None:  # 리랭커 평가: 벡터 1위 점수 + 리랭커 1위 점수
        score = f"벡터 {score} / 리랭커 {q['rerank_top_score']:.3f}"
    if kind == "none":
        badge = f'<span class="badge none">자료에 없음 · 1위 {score}</span>'
    elif kind == "hit":
        badge = f'<span class="badge hit">정답 {q["rank"]}위 · 1위 {score}</span>'
    else:
        where = f"{q['rank']}위(K={k} 밖)" if q["rank"] else "순위 깊이 안에 없음"
        badge = f'<span class="badge miss">정답 {where} · 1위 {score}</span>'
    gold = ""
    if q["pages"]:
        figs = "".join(
            f"<figure>{_thumb(g)}<figcaption>정답 {escape(q['subject'])} p{escape(g['page'])}</figcaption></figure>"
            for g in q["gold_pages"]
        )
        gold = f"<div class=gold-row>{figs}</div>"
    rows = "".join(
        f'<tr{" class=g" if t["gold"] else ""}><td>{t["rank"]}</td><td>{t["score"]:.3f}{_vec(t)}</td>'
        f"<td>{escape(str(t['subject'] or '?'))}<br>p{escape(str(t['page']))}</td>"
        f"<td class=txt><b>{escape(t['title'] or '')}</b>\n"
        f"{escape(t['text']) if not t['missing_chunk'] else '<span class=err>(청크 없음 — 평가 후 재청킹됐을 수 있음)</span>'}</td>"
        f"<td class=img>{_thumb(t)}</td></tr>"
        for t in q["top"]
    )
    return (
        f'<section class=q data-kind="{kind}"><div class=qh><span class=qid>{escape(q["id"])}</span>'
        f"<span class=qt>{escape(q['question'])}</span>{badge}</div>"
        f"<div class=meta>{escape(q.get('note') or '')}</div>{gold}"
        f"<table><tr><th>순위</th><th>점수</th><th>쪽</th><th>청크</th><th>페이지</th></tr>{rows}</table></section>"
    )


def _vec(t: dict) -> str:
    """리랭커 평가일 때 리랭크 전 벡터 순위·점수."""
    if "vector_rank" not in t:
        return ""
    return f"<br><small>벡터 {t['vector_rank']}위 {t['vector_score']:.3f}</small>"


def _thumb(d: dict) -> str:
    if "thumb" not in d:
        return f'<span class=err>{escape(d.get("thumb_error", "이미지 없음"))}</span>'
    img = f'<img class=th loading=lazy src="{escape(d["thumb"])}" alt="">'
    return f'<a href="{escape(d["full"])}" target=_blank>{img}</a>' if d.get("full") else img


# ---------- 실행 ----------


def write_report(settings: Settings, json_path: Path) -> Path:
    from app.db.connection import connect
    from app.retrieval.evaluate import format_summary

    report = json.loads(json_path.read_text(encoding="utf-8"))
    out_dir = json_path.parent
    with connect(settings) as conn:
        data = collect(conn, settings, report, out_dir)
    html = render_html(data, format_summary(report["summary"], report["config"]), f"검색 평가 {json_path.stem}")
    out = json_path.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    ap = argparse.ArgumentParser(description="검색 평가 HTML 보고서")
    ap.add_argument("json", nargs="?", type=Path, help="평가 결과 json(기본: 가장 최근)")
    args = ap.parse_args(argv)
    path = args.json
    if path is None:
        found = sorted((settings.reports_path / "eval").glob("*.json"))
        if not found:
            print("평가 결과 json이 없습니다. 먼저 app.retrieval.evaluate를 실행하세요.")
            return 1
        path = found[-1]
    print(f"보고서: {write_report(settings, path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
