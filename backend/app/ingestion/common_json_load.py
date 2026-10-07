"""공통 JSON 적재·재임베딩 (D-M-032). 기본은 dry-run(검증 + 바뀔 내용 보고), DB 쓰기는 --apply.

    cd backend
    uv run python -m app.ingestion.common_json_load --subject subject1 --no-db      # 파일 검증·임베딩 텍스트만(DB 없음)
    uv run python -m app.ingestion.common_json_load --subject subject1,subject2      # dry-run: DB와 비교(읽기만)
    uv run python -m app.ingestion.common_json_load --apply --subject all            # 적재(바뀐 블록만 임베딩)
    uv run python -m app.ingestion.common_json_load --apply --subject subject2 --block-id S2:TABLE:TAB_104_01
    uv run python -m app.ingestion.common_json_load --apply --subject subject2 --prune     # 파일에서 빠진 블록 삭제
    uv run python -m app.ingestion.common_json_load --apply --subject subject2 --delete    # 문서째 삭제
    uv run python -m app.ingestion.common_json_load --subject subject2 --no-db --show S2:TABLE:TAB_104_01

- 파일 전체를 검증한 뒤(하나라도 실패하면 아무것도 쓰지 않음) 임베딩 텍스트를 만들고,
  DB와 비교해 바뀐 블록만 임베딩한다. 임베딩은 DB 쓰기 전에 끝내고, 과목(문서) 1개당 트랜잭션 1개로 쓴다.
- block_id로 upsert하므로 여러 번 돌려도 결과가 같다. 관계는 문서 단위로 파일과 똑같이 맞춘다.
- 실행 기록은 processing_runs 1건(과목당), 리포트는 data/reports/common_json/.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.core.config import Settings, get_settings
from app.ingestion.common_json import (
    CORPUS,
    BlockPlan,
    CommonJsonError,
    SubjectData,
    available_subjects,
    plan_blocks,
    read_subject,
    select_blocks,
    summarize,
)

LOAD_VERSION = "0.1"
BLOCK_EMBEDDING_DIM = 1024  # 004 마이그레이션의 blocks.embedding vector(1024)
EMBED_PROGRESS_BATCH = 32  # 진행 표시 단위(배치 크기는 EMBEDDING_BATCH_SIZE)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="공통 JSON 적재·재임베딩 (기본 dry-run)")
    ap.add_argument("--subject", required=True, metavar="KEY[,KEY]", help="과목 폴더(subject1, subject2, all)")
    ap.add_argument("--apply", action="store_true", help="DB에 쓴다(없으면 dry-run)")
    ap.add_argument("--block-id", action="append", default=[], help="이 블록만 적재(여러 번 지정 가능)")
    ap.add_argument("--prune", action="store_true", help="DB에만 있고 파일에 없는 블록 삭제")
    ap.add_argument("--delete", action="store_true", help="과목 문서를 블록·관계째 삭제")
    ap.add_argument("--no-db", action="store_true", help="DB 없이 파일 검증·임베딩 텍스트만(dry-run 전용)")
    ap.add_argument("--dir", type=Path, default=None, help="공통 JSON 폴더(기본 COMMON_JSON_DIR)")
    ap.add_argument("--show", action="append", default=[], metavar="BLOCK_ID", help="이 블록의 임베딩 텍스트 출력")
    args = ap.parse_args(argv)
    if args.no_db and (args.apply or args.delete):
        ap.error("--no-db는 dry-run 전용입니다")
    if args.delete and (args.block_id or args.prune):
        ap.error("--delete는 --block-id·--prune과 함께 쓸 수 없습니다")
    if args.prune and args.block_id:
        ap.error("--prune은 과목 전체 적재에서만 씁니다(--block-id와 함께 쓸 수 없음)")
    return args


def resolve_keys(root: Path, subject: str) -> list[str]:
    keys = available_subjects(root) if subject == "all" else [k.strip() for k in subject.split(",") if k.strip()]
    if not keys:
        raise SystemExit(f"과목 폴더가 없습니다: {root}")
    return keys


def split_block_ids(datas: list[SubjectData], block_ids: list[str]) -> dict[str, list[str]]:
    """block_id 앞의 S{n}으로 과목에 나눈다. 고른 과목에 없는 번호면 오류."""
    by_no = {d.subject_no: d.key for d in datas}
    out: dict[str, list[str]] = {d.key: [] for d in datas}
    for bid in block_ids:
        no = bid.split(":", 1)[0].removeprefix("S")
        if not no.isdigit() or int(no) not in by_no:
            raise CommonJsonError([f"--block-id {bid}: 고른 과목({', '.join(out)})의 블록이 아님"])
        out[by_no[int(no)]].append(bid)
    return out


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    args = parse_args(argv)
    settings = settings or get_settings()
    root = args.dir or settings.common_json_path
    keys = resolve_keys(root, args.subject)

    if args.delete:
        return _delete(settings, root, keys, apply=args.apply)

    try:
        datas = [read_subject(settings, root, k) for k in keys]
        selected = split_block_ids(datas, args.block_id) if args.block_id else {d.key: [] for d in datas}
        targets = {d.key: select_blocks(d, selected[d.key]) for d in datas}
    except CommonJsonError as e:
        print("검증 실패 — 아무것도 쓰지 않았습니다.")
        for err in e.errors:
            print(f"  - {err}")
        return 1

    for bid in args.show:
        _show(datas, bid)

    if args.no_db:
        plans = {d.key: plan_blocks(targets[d.key], {}, settings.embedding_model) for d in datas}
        report = _report(settings, datas, plans, mode="dry-run-no-db", db_only={}, partial=bool(args.block_id))
        _print_summary(report)
        return 0

    from app.db.connection import connect
    from app.repositories import blocks as blocks_repo

    with connect(settings) as conn:
        plans, db_only, doc_ids = {}, {}, {}
        for d in datas:
            doc_ids[d.key] = blocks_repo.get_document_id(conn, settings, d.document_key)
            existing = blocks_repo.existing_blocks(conn, settings, [r.block_id for r in targets[d.key]])
            plans[d.key] = plan_blocks(targets[d.key], existing, settings.embedding_model)
            in_db = blocks_repo.document_block_ids(conn, settings, doc_ids[d.key]) if doc_ids[d.key] else set()
            db_only[d.key] = sorted(in_db - {r.block_id for r in d.blocks})
            if args.block_id:
                if doc_ids[d.key] is None:
                    print(f"{d.key}: 문서가 아직 적재되지 않았습니다. --block-id 없이 과목 전체를 먼저 적재하세요.")
                    return 1
                endpoints = {x for r in d.relations for x in (r.from_block_id, r.to_block_id)}
                if missing := sorted(endpoints - in_db - set(selected[d.key])):
                    print(f"{d.key}: 관계 끝점 블록이 DB에 없습니다({', '.join(missing[:5])} …). 과목 전체를 적재하세요.")
                    return 1

        mode = "apply" if args.apply else "dry-run"
        report = _report(settings, datas, plans, mode=mode, db_only=db_only, partial=bool(args.block_id))
        if not args.apply:
            _print_summary(report)
            return 0

        if settings.embedding_dim != BLOCK_EMBEDDING_DIM:
            print(f"EMBEDDING_DIM={settings.embedding_dim}이 blocks.embedding 차원({BLOCK_EMBEDDING_DIM})과 다릅니다.")
            return 1
        vectors = _embed_all(settings, [p for d in datas for p in plans[d.key] if p.embed])
        for d in datas:
            book_id = _find_book_id(conn, settings, d.key)
            _apply_subject(conn, settings, d, plans[d.key], vectors, book_id,
                           prune=db_only[d.key] if args.prune else [], partial=bool(args.block_id),
                           report_subject=report["subjects"][d.key])
        _write_report(settings, report)
        _print_summary(report)
    return 0


def _apply_subject(conn, settings: Settings, d: SubjectData, plans: list[BlockPlan], vectors: dict[str, str],
                   book_id: UUID | None, *, prune: list[str], partial: bool, report_subject: dict) -> None:
    from app.repositories import blocks as blocks_repo
    from app.repositories import runs as runs_repo

    run_id = runs_repo.create_run(conn, settings, pipeline_version=f"common-json-load-{LOAD_VERSION}",
                                  page_count=len(d.pages))
    try:
        with conn.transaction():
            doc_id = blocks_repo.upsert_document(conn, settings, d, corpus=CORPUS, book_id=book_id)
            written = blocks_repo.upsert_blocks(conn, settings, doc_id, run_id, plans, vectors, settings.embedding_model)
            relations = blocks_repo.replace_relations(conn, settings, doc_id, d.relations)
            pruned = blocks_repo.delete_blocks(conn, settings, doc_id, prune)
    except BaseException:
        runs_repo.finish_run(conn, settings, run_id, success=0, review=0, failure=0,
                             incomplete=len(d.pages), interrupted=True)
        raise
    status = runs_repo.finish_run(conn, settings, run_id, success=len(d.pages), review=0, failure=0)
    result = {"document_id": str(doc_id), "run_id": str(run_id), "run_status": status, "written_blocks": written,
              "relations": relations, "pruned": pruned, "partial": partial, "book_id": str(book_id) if book_id else None}
    runs_repo.merge_run_metadata(conn, settings, run_id, {
        "common_json": {"document_key": d.document_key, "format_version": d.format_version, "files": d.files,
                        **{k: v for k, v in result.items() if k not in ("run_id", "run_status")},
                        "counts": report_subject["plan"], "warnings": d.warnings}})
    report_subject["result"] = result


def _embed_all(settings: Settings, plans: list[BlockPlan]) -> dict[str, str]:
    """임베딩이 필요한 블록만 계산한다(DB 쓰기 전). block_id → pgvector 텍스트."""
    if not plans:
        return {}
    from app.ingestion.embedding import get_embedder, to_pgvector

    t0 = time.perf_counter()
    embedder = get_embedder(settings)
    print(f"임베딩 모델 로드 {time.perf_counter() - t0:.0f}초, 대상 {len(plans)}블록", flush=True)
    out: dict[str, str] = {}
    t0 = time.perf_counter()
    for i in range(0, len(plans), EMBED_PROGRESS_BATCH):
        part = plans[i: i + EMBED_PROGRESS_BATCH]
        vecs = embedder.encode([p.record.embedding_text for p in part])
        for p, v in zip(part, vecs):
            out[p.record.block_id] = to_pgvector(v)
        print(f"  임베딩 {min(i + EMBED_PROGRESS_BATCH, len(plans))}/{len(plans)} ({time.perf_counter() - t0:.0f}초)",
              flush=True)
    return out


def _find_book_id(conn, settings: Settings, key: str) -> UUID | None:
    """같은 교재의 기존 팀 텍스트 book(page_map의 같은 과목 key). 없거나 여러 개면 None."""
    try:
        from app.ingestion.team_import import load_map

        cfg = next((c for c in load_map(settings)["books"] if c["key"] == key), None)
    except (OSError, ValueError, KeyError):
        return None
    if cfg is None:
        return None
    from app.repositories import books as books_repo

    ids = books_repo.find_book_ids(conn, settings, subject=cfg["subject"], title=cfg["title"],
                                   source_name=cfg["source_name"])
    return ids[0] if len(ids) == 1 else None


def _delete(settings: Settings, root: Path, keys: list[str], *, apply: bool) -> int:
    from app.db.connection import connect
    from app.ingestion.common_json import BLOCKS_FORMAT
    from app.repositories import blocks as blocks_repo

    with connect(settings) as conn:
        for key in keys:
            # 문서 key는 파일의 format으로 만든다. 파일이 없어도 지울 수 있게 기본 format으로 찾는다.
            try:
                document_key = read_subject(settings, root, key).document_key
            except CommonJsonError:
                document_key = f"{BLOCKS_FORMAT}:{key}"
            doc_id = blocks_repo.get_document_id(conn, settings, document_key)
            if doc_id is None:
                print(f"{key}: DB에 문서 없음({document_key})")
                continue
            counts = blocks_repo.count_document(conn, settings, doc_id)
            if not apply:
                print(f"{key}: 삭제 예정(dry-run) {document_key} — 블록 {counts['blocks']}, "
                      f"임베딩 {counts['embedded']}, 관계 {counts['relations']}")
                continue
            with conn.transaction():
                blocks_repo.delete_document(conn, settings, doc_id)
            print(f"{key}: 삭제 완료 {document_key} — 블록 {counts['blocks']}, 관계 {counts['relations']}")
    return 0


def _show(datas: list[SubjectData], block_id: str) -> None:
    rec = next((r for d in datas for r in d.blocks if r.block_id == block_id), None)
    if rec is None:
        print(f"--show {block_id}: 고른 과목에 없는 블록")
        return
    state = "검색 대상" if rec.search_enabled else f"검색 제외({rec.search_excluded_reason})"
    print(f"===== {block_id} [{rec.block_type}/{rec.block_role}] {rec.printed_page_number}쪽 · {state}")
    print(rec.embedding_text)
    print()


def _report(settings: Settings, datas: list[SubjectData], plans: dict[str, list[BlockPlan]], *, mode: str,
            db_only: dict[str, list[str]], partial: bool) -> dict:
    subjects = {}
    for d in datas:
        ps = plans[d.key]
        counts = {s: sum(p.status == s for p in ps) for s in ("new", "changed", "unchanged")}
        counts |= {"embed": sum(p.embed for p in ps), "clear_embedding": sum(p.clear_embedding for p in ps),
                   "targets": len(ps)}
        subjects[d.key] = {
            "document_key": d.document_key,
            "title": d.title,
            "format_version": d.format_version,
            "files": d.files,
            "summary": summarize(d),
            "plan": counts,
            "db_only_blocks": db_only.get(d.key, []),
            "warnings": d.warnings,
            "blocks": [
                {"block_id": p.record.block_id, "type": p.record.block_type, "role": p.record.block_role,
                 "page": p.record.printed_page_number, "search_enabled": p.record.search_enabled,
                 "excluded_reason": p.record.search_excluded_reason, "status": p.status, "embed": p.embed,
                 "embedding_text_chars": len(p.record.embedding_text), "embedding_text": p.record.embedding_text}
                for p in ps
            ],
        }
    report = {
        "mode": mode,
        "partial": partial,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "embedding_model": settings.embedding_model,
        "rules": {"search_learning_objective": settings.common_json_search_learning_objective,
                  "search_duplicate_theory": settings.common_json_search_duplicate_theory},
        "subjects": subjects,
    }
    if mode != "apply":
        _write_report(settings, report)
    return report


def _write_report(settings: Settings, report: dict) -> None:
    out_dir = settings.reports_path / "common_json"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["created_at"].replace(":", "").replace("-", "").replace("T", "-")
    out = out_dir / f"{stamp}_{report['mode']}.json"
    n = 2
    while out.exists():  # 같은 초에 다시 돌려도 앞 리포트를 덮어쓰지 않는다
        out = out_dir / f"{stamp}_{report['mode']}_{n}.json"
        n += 1
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    report["report_path"] = str(out)


def _print_summary(report: dict) -> None:
    print(f"[{report['mode']}{' / 일부 블록' if report['partial'] else ''}] 임베딩 모델 {report['embedding_model']}")
    for key, s in report["subjects"].items():
        sm, pl = s["summary"], s["plan"]
        print(f"{key} ({s['title']}, {s['format_version']})")
        print(f"  블록 {sm['blocks']} {sm['by_type']} · 관계 {sm['relations']} · 쪽 관계 {sm['page_relations']} · 쪽 {sm['pages']}")
        print(f"  검색 대상 {sm['searchable']} {sm['searchable_by_type']} · 제외 {sm['excluded']}")
        print(f"  이번 대상 {pl['targets']}: 새로 {pl['new']} / 바뀜 {pl['changed']} / 같음 {pl['unchanged']}"
              f" · 임베딩 계산 {pl['embed']} · 임베딩 지움 {pl['clear_embedding']}")
        if s["db_only_blocks"]:
            print(f"  DB에만 있는 블록 {len(s['db_only_blocks'])}개(--prune으로 삭제): {', '.join(s['db_only_blocks'][:5])}")
        for w in s["warnings"]:
            print(f"  경고: {w}")
        if r := s.get("result"):
            print(f"  적재: 블록 {r['written_blocks']}행 · 관계 {r['relations']} · 삭제 {r['pruned']} · run {r['run_status']}")
    if path := report.get("report_path"):
        print(f"리포트: {path}")


if __name__ == "__main__":
    sys.exit(main())
