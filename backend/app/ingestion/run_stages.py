"""이미 추출된 페이지에 이후 단계만 다시 돌리는 실행 진입점 (D-019).

extract_text는 다시 하지 않고(팀 텍스트·OCR 결과를 그대로 읽음), detect_visuals는 아직 없으므로 건너뛴다.
건너뛴 단계는 page_metadata.pipeline.skipped에 남긴다.

    cd backend
    uv run python -m app.ingestion.run_stages                                # dry-run(기본): 전체 과목, 리포트만
    uv run python -m app.ingestion.run_stages --subject subject1             # dry-run, 1과목만
    uv run python -m app.ingestion.run_stages --apply --subject subject1     # DB 반영(과목 필수, 전체는 all)
    uv run python -m app.ingestion.run_stages --book-id <uuid>               # 업로드 자료

- 대상 페이지: processing_status가 EXTRACTED / VERIFIED / EMBEDDED인 페이지(upload_index 순서).
  REVIEW_REQUIRED·FAILED·RAW는 건드리지 않고 개수만 알려 준다.
- chunk_theory가 끝나면 VERIFIED. 기존 청크는 페이지 단위 트랜잭션으로 지우고 다시 넣는다(임베딩도 사라짐).
- --apply는 자료(book)마다 processing_runs 1건을 만든다.
- dry-run 리포트: {REPORTS_DIR}/chunking/{key}.json (청크 전체), {key}.txt (사람이 읽는 표본)
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.db.connection import connect, create_pool
from app.ingestion import chunking, stages
from app.ingestion.pipeline import PIPELINE_VERSION, Stage, run_pipeline
from app.ingestion.team_import import load_map
from app.repositories import books as books_repo
from app.repositories import runs as runs_repo
from app.storage.base import Storage

TARGET_STATUSES = ("EXTRACTED", "VERIFIED", "EMBEDDED")
SKIPPED = ["detect_visuals"]  # 구현 전까지 건너뛰는 단계
_CHUNK = Stage("chunk_theory", stages.chunk_theory, "VERIFIED")
_EMBED = Stage("embed", stages.embed, "EMBEDDED")
STAGE_SETS = {
    "chunk": (_CHUNK,),
    "embed": (_EMBED,),  # 청킹된(VERIFIED/EMBEDDED) 페이지만
    "chunk,embed": (_CHUNK, _EMBED),
}
EMBED_STATUSES = ("VERIFIED", "EMBEDDED")
_SAMPLE_PAGES = 12  # dry-run 표본 텍스트에 넣을 페이지 수(앞에서부터, 제외 구간 있는 페이지 우선 포함)


@dataclass
class Target:
    key: str  # 리포트 파일 이름(page_map key 또는 book id)
    book_id: UUID
    title: str


def resolve_targets(conn: psycopg.Connection, settings: Settings, subject: str | None, book_ids: list[str]) -> list[Target]:
    if book_ids:
        out = []
        for b in book_ids:
            book = books_repo.get_book(conn, settings, UUID(b))
            if book is None:
                raise SystemExit(f"book 없음: {b}")
            out.append(Target(key=b, book_id=book["id"], title=book["title"]))
        return out
    books_cfg = load_map(settings)["books"]
    if subject and subject != "all":
        keys = subject.split(",")
        if unknown := set(keys) - {c["key"] for c in books_cfg}:
            raise SystemExit(f"page_map에 없는 과목: {sorted(unknown)}")
        books_cfg = [c for c in books_cfg if c["key"] in keys]
    out = []
    for c in books_cfg:
        ids = books_repo.find_book_ids(
            conn, settings, subject=c["subject"], title=c["title"], source_name=c["source_name"]
        )
        if not ids:
            print(f"  [{c['key']}] DB에 없음(반입 전) → 건너뜀")
            continue
        out.append(Target(key=c["key"], book_id=ids[0], title=c["title"]))
    return out


def list_book_pages(conn: psycopg.Connection, settings: Settings, book_id: UUID) -> list[dict]:
    q = sql.SQL(
        "SELECT id, printed_page_number, processing_status, (page_metadata->>'upload_index')::int AS upload_index, "
        "page_metadata->'text' AS text, page_metadata->'ocr' AS ocr, "
        "(SELECT count(*) FROM {s}.theory_chunks t WHERE t.page_id = p.id) AS existing_chunks "
        "FROM {s}.pages p WHERE book_id = %s "
        "ORDER BY (page_metadata->>'upload_index')::int NULLS LAST, created_at"
    ).format(s=sql.Identifier(settings.db_schema))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, (book_id,)).fetchall()


# ---------- dry-run ----------


def dry_run(settings: Settings, storage: Storage, target: Target, pages: list[dict]) -> dict:
    """DB를 바꾸지 않고 청킹 결과를 계산해 리포트로 저장한다. 제목 경로는 메모리에서 이어받는다."""
    params = stages.chunk_params(settings)
    state = chunking.ChunkState()
    report_pages = []
    for p in pages:
        lines, source, _ = stages.read_page_lines(storage, p["text"], p["ocr"])
        result = chunking.chunk_page(lines, p["printed_page_number"], state, params)
        state = result.end_state
        report_pages.append(
            {
                "page_id": str(p["id"]),
                "printed_page": p["printed_page_number"],
                "status": p["processing_status"],
                "existing_chunks": p["existing_chunks"],
                "source": source,
                "chunks": [asdict(c) for c in result.chunks],
                "excluded": [asdict(e) for e in result.excluded],
                "dropped_lines": result.dropped_lines,
                "lines": lines,
            }
        )
    sizes = [len(c["clean_text"]) for rp in report_pages for c in rp["chunks"]]
    summary = {
        "book_id": str(target.book_id),
        "title": target.title,
        "pages": len(report_pages),
        "chunks": len(sizes),
        "needs_review": sum(1 for rp in report_pages for c in rp["chunks"] if c["needs_review"]),
        "excluded_blocks": sum(len(rp["excluded"]) for rp in report_pages),
        "pages_without_chunks": [rp["printed_page"] for rp in report_pages if not rp["chunks"]],
        "clean_chars": {
            "avg": round(sum(sizes) / len(sizes)) if sizes else 0,
            "max": max(sizes, default=0),
            "under_min": sum(1 for x in sizes if x < settings.chunk_min_chars),
        },
        "existing_chunks_to_replace": sum(rp["existing_chunks"] for rp in report_pages),
        "params": asdict(params),
    }
    out_dir = settings.reports_path / "chunking"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{target.key}.json").write_text(
        json.dumps({"summary": summary, "pages": report_pages}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out_dir / f"{target.key}.txt").write_text(sample_text(report_pages), encoding="utf-8")
    summary["report"] = str(out_dir / f"{target.key}.json")
    return summary


def sample_text(report_pages: list[dict]) -> str:
    """사람이 훑어볼 표본: 앞쪽 페이지 몇 장 + 제외 구간이 있는 페이지 몇 장."""
    picked = report_pages[: _SAMPLE_PAGES // 2]
    picked += [rp for rp in report_pages if rp["excluded"] and rp not in picked][: _SAMPLE_PAGES // 2]
    out = []
    for rp in picked:
        out.append(f"########## {rp['printed_page']}쪽 (page {rp['page_id']})")
        for c in rp["chunks"]:
            review = f" needs_review={c['review_reasons']}" if c["needs_review"] else ""
            out.append(f"--- 청크 {c['sort_order']} 줄 {c['line_range']} 제목={c['title']!r}{review}")
            out.append("[embedding_text]\n" + c["embedding_text"])
            out.append("[raw_text]\n" + c["raw_text"])
            out.append("[exam_clues] " + json.dumps(c["exam_clues"], ensure_ascii=False))
        for e in rp["excluded"]:
            a, b = e["line_range"]
            body = "\n".join(line for line in rp["lines"][a : b + 1] if line.strip())
            out.append(f"--- 제외 구간 {e['section_type']} {e['title']!r} 줄 {e['line_range']} 이어짐={e['continued']}")
            out.append(body)
        out.append("")
    return "\n".join(out)


# ---------- apply ----------


def apply(settings: Settings, storage: Storage, target: Target, pages: list[dict], stage_list) -> dict:
    page_ids = [p["id"] for p in pages]
    with connect(settings) as conn:
        run_id = runs_repo.create_run(conn, settings, pipeline_version=PIPELINE_VERSION, page_count=len(page_ids))
    pool = create_pool(settings)
    pool.open()
    try:
        counts = run_pipeline(
            pool,
            settings,
            storage,
            run_id,
            page_ids,
            stage_list=stage_list,
            pipeline_extra={"skipped": SKIPPED, "runner": "run_stages"},
        )
    finally:
        pool.close()
    return {"run_id": str(run_id), **counts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="추출된 페이지에 청킹 등 이후 단계 실행 (기본 dry-run)")
    ap.add_argument("--apply", action="store_true", help="DB 반영(기본은 dry-run: 리포트만)")
    ap.add_argument("--subject", metavar="KEY[,KEY]", help="page_map key (subject1, subject2,subject3, all)")
    ap.add_argument("--book-id", action="append", default=[], help="대상 book id(업로드 자료). 여러 번 지정 가능")
    ap.add_argument("--stages", choices=list(STAGE_SETS), default="chunk", help="실행할 단계 묶음")
    ap.add_argument("--pages", metavar="쪽,쪽", help="인쇄 쪽번호로 대상 제한(시험용, 예: 14,15,16)")
    args = ap.parse_args(argv)
    if args.apply and not (args.subject or args.book_id):
        ap.error("--apply에는 --subject 또는 --book-id가 필요합니다(전체는 --subject all)")
    if args.subject and args.book_id:
        ap.error("--subject와 --book-id는 함께 쓸 수 없습니다")

    from app.storage import get_storage

    settings = get_settings()
    storage = get_storage(settings)
    with connect(settings) as conn:
        targets = resolve_targets(conn, settings, args.subject, args.book_id)
        plans = []
        for t in targets:
            pages = list_book_pages(conn, settings, t.book_id)
            allowed = EMBED_STATUSES if args.stages == "embed" else TARGET_STATUSES
            todo = [p for p in pages if p["processing_status"] in allowed]
            if args.pages:
                wanted = set(args.pages.split(","))
                todo = [p for p in todo if p["printed_page_number"] in wanted]
            others: dict[str, int] = {}
            for p in pages:
                if p["processing_status"] not in allowed:
                    others[p["processing_status"]] = others.get(p["processing_status"], 0) + 1
            plans.append((t, todo, others))

    for t, todo, others in plans:
        print(f"[{t.key}] {t.title}: 대상 {len(todo)}쪽" + (f", 제외 {others}" if others else ""))
        if not args.apply and "chunk" in args.stages:
            summary = dry_run(settings, storage, t, todo)
            print("  " + json.dumps({k: v for k, v in summary.items() if k != "params"}, ensure_ascii=False))
        else:
            print("  " + json.dumps(apply(settings, storage, t, todo, STAGE_SETS[args.stages]), ensure_ascii=False))
    if not args.apply:
        print(f"dry-run: DB 변경 없음. 청크 설정 {asdict(stages.chunk_params(settings))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
