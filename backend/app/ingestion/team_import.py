"""팀 교재 반입 (D-014, D-018).

팀 PDF(휴대폰 촬영 스캔)와 팀원이 추출한 페이지별 텍스트를 books/pages로 넣는다.
업로드 API를 거치지 않고, 팀 텍스트를 extract_text 결과로 저장한다(engine="team_text").

    cd backend
    uv run python -m app.ingestion.team_import                 # dry-run(기본): 계획만 출력·저장
    uv run python -m app.ingestion.team_import --preview subject3:84,85,120
                                                               # 쪽번호 대조용 저해상도 띠 이미지
    uv run python -m app.ingestion.team_import --apply --subject subject1   # 실제 저장 + INSERT(과목 필수, 전체는 all)

- PDF 장 ↔ 인쇄 쪽 매핑은 `{TEAM_IMPORT_DIR}/page_map.json`(사람이 표본 대조로 확정한 값)을 따른다.
- 텍스트는 원문 그대로(UTF-8) 저장하고 교정하지 않는다.
- 재실행 안전: 같은 subject·title·source_name의 book이 있으면 그 과목은 건너뛴다.
- book 단위 트랜잭션, book당 processing_runs 1건. 파일은 트랜잭션 전에 저장하고 실패하면 지운다.
"""

import argparse
import io
import json
import re
import sys
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pypdfium2 as pdfium

from app.core.config import Settings, get_settings
from app.ingestion.stages import text_key

IMPORT_VERSION = "0.1-team-text"
TEXT_ENGINE = "team_text"
_TEXT_NAME = re.compile(r"^.+-(\d+)p\.txt$")  # 과1-14p.txt → 14 (두 쪽짜리 이름은 page_map에 명시)
_MULTI_PAGE_NAME = re.compile(r"^.+-\d+-\d+p\.txt$")
_FOOTER_NUM = re.compile(r"^\s*(\d{1,3})\s*\|?\s*$|\|\s*(\d{1,3})\s*$")  # "215", "14 |", "... | 57"


# ---------- 계획 ----------


@dataclass
class PagePlan:
    pdf_index: int  # 1부터
    printed: int
    status: str  # EXTRACTED / REVIEW_REQUIRED
    text_file: str | None = None
    covers_pages: list[int] = field(default_factory=list)
    text_lines: list[int] | None = None  # [시작, 끝] 줄 번호(1부터, 끝 포함). None이면 파일 전체
    text_note: str | None = None  # 분할 위치, 파일명과 내용이 다른 경우 등 메모
    missing_before: list[dict] = field(default_factory=list)  # 바로 앞에 빠진 쪽(촬영 누락 등)
    reason: str | None = None
    footer_check: str | None = None  # match / mismatch:<숫자들> / none


@dataclass
class BookPlan:
    key: str
    subject: str
    title: str
    material_type: str
    source_name: str
    pdf_file: str
    text_dir: str
    pdf_page_count: int
    pages: list[PagePlan]
    skipped_pdf: list[dict]
    missing_printed: list[dict]
    errors: list[str]


@dataclass(frozen=True)
class TextSource:
    name: str
    covers: list[int]
    lines: list[int] | None = None
    note: str | None = None


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def find_nfc(directory: Path, name: str) -> Path:
    """파일명이 NFD(macOS 압축)로 저장돼 있어도 NFC 이름으로 찾는다."""
    target = nfc(name)
    for p in directory.iterdir():
        if nfc(p.name) == target:
            return p
    raise FileNotFoundError(f"{directory} 안에 {name} 없음")


def resolve(base: Path, rel: str) -> Path:
    cur = base
    for part in Path(rel).parts:
        cur = find_nfc(cur, part)
    return cur


def pdf_to_printed(cfg: dict, pdf_page_count: int) -> tuple[dict[int, int], list[str]]:
    """segments/skip_pdf로 PDF 장 → 인쇄 쪽 사전을 만든다. 빠지거나 겹친 장은 오류로 모은다."""
    errors: list[str] = []
    skip = {s["pdf"] for s in cfg.get("skip_pdf", [])}
    mapping: dict[int, int] = {}
    for seg in cfg["segments"]:
        for i in range(seg["pdf_from"], seg["pdf_to"] + 1):
            if i in mapping or i in skip:
                errors.append(f"PDF {i}장이 segments/skip_pdf에 중복")
            mapping[i] = i + seg["offset"]
    covered = set(mapping) | skip
    expected = set(range(1, pdf_page_count + 1))
    if missing := sorted(expected - covered):
        errors.append(f"매핑 없는 PDF 장: {missing}")
    if extra := sorted(covered - expected):
        errors.append(f"PDF에 없는 장 번호: {extra}")
    seen: dict[int, int] = {}
    for i, printed in sorted(mapping.items()):
        if printed in seen:
            errors.append(f"{printed}쪽이 PDF {seen[printed]}장과 {i}장에 중복")
        seen[printed] = i
    return mapping, errors


def slice_lines(text: str, lines: list[int] | None) -> str:
    """줄 범위만 잘라낸다. 줄바꿈을 포함해 자르므로 조각을 이으면 원문과 같다(내용 변경 없음)."""
    if lines is None:
        return text
    start, end = lines
    return "".join(text.splitlines(keepends=True)[start - 1 : end])


def _split_sources(name: str, covers: list[int], splits: list[int], text: str, note: str | None):
    """`split_at_lines`(다음 쪽이 시작하는 줄 번호들)로 한 파일을 쪽별로 나눈다."""
    n = len(text.splitlines(keepends=True))
    if len(splits) != len(covers) - 1 or splits != sorted(set(splits)) or not all(1 < s <= n for s in splits):
        raise ValueError(f"{name}: split_at_lines {splits}가 쪽 {covers} / 줄 수 {n}과 맞지 않음")
    starts = [1, *splits]
    ends = [s - 1 for s in splits] + [n]
    where = ", ".join(f"{s}번째 줄" for s in splits)
    out = {}
    for page, s, e in zip(covers, starts, ends, strict=True):
        memo = f"{name}의 {where}에서 분할 ({page}쪽 = {s}~{e}줄)"
        out[page] = TextSource(name, [page], [s, e], f"{memo}. {note}" if note else memo)
    return out


def text_file_pages(cfg: dict, texts: dict[str, str]) -> tuple[dict[int, TextSource], list[str]]:
    """텍스트 파일 → 쪽.

    - 보통 파일: 파일명의 쪽번호(`과1-14p.txt` → 14)
    - page_map `text_files`에 적힌 파일: `pages` 목록을 따른다. `split_at_lines`가 있으면 쪽별로 나누고,
      없으면 첫 쪽에 전체를 붙인다(나머지 쪽은 합본 표시).
    """
    overrides = {nfc(k): v for k, v in cfg.get("text_files", {}).items()}
    errors: list[str] = []
    result: dict[int, TextSource] = {}

    def put(page: int, src: TextSource) -> None:
        if page in result:
            errors.append(f"{page}쪽 텍스트 파일 중복: {result[page].name}, {src.name}")
        result[page] = src

    for name in sorted(texts):
        if name in overrides:
            ov = overrides[name]
            covers = list(ov["pages"])
            if splits := ov.get("split_at_lines"):
                try:
                    for page, src in _split_sources(name, covers, splits, texts[name], ov.get("note")).items():
                        put(page, src)
                except ValueError as e:
                    errors.append(str(e))
            else:
                put(covers[0], TextSource(name, covers, note=ov.get("note")))
        elif _MULTI_PAGE_NAME.match(name):
            errors.append(f"여러 쪽짜리 파일은 page_map text_files에 적어야 함: {name}")
        elif m := _TEXT_NAME.match(name):
            put(int(m.group(1)), TextSource(name, [int(m.group(1))]))
        else:
            errors.append(f"쪽번호를 알 수 없는 파일명: {name}")
    return result, errors


def footer_numbers(text: str) -> list[int]:
    """본문 끝부분의 쪽번호 후보(머리말/꼬리말 줄). 매핑 확인용일 뿐 텍스트는 바꾸지 않는다."""
    nums = []
    for line in [ln for ln in text.splitlines() if ln.strip()][-4:]:
        if m := _FOOTER_NUM.search(line):
            nums.append(int(m.group(1) or m.group(2)))
    return nums


def footer_matches(num: int, pages: list[int]) -> bool:
    """쪽번호 옆 `|`가 OCR에서 1로 읽힌 경우("| 27" → 127, "66 |" → 661)도 일치로 본다."""
    return any(str(num) in (str(p), f"1{p}", f"{p}1") for p in pages)


def build_plan(cfg: dict, pdf_page_count: int, texts: dict[str, str]) -> BookPlan:
    """PDF 장 수와 텍스트 파일({파일명: 내용})로 페이지별 계획을 만든다(DB·파일 접근 없음)."""
    mapping, errors = pdf_to_printed(cfg, pdf_page_count)
    texts = {nfc(k): v for k, v in texts.items()}
    by_page, text_errors = text_file_pages(cfg, texts)
    errors += text_errors

    merged_into: dict[int, str] = {}  # 나누지 않은 합본 파일의 두 번째 이후 쪽 → 파일명
    for first, src in by_page.items():
        for p in src.covers[1:]:
            merged_into[p] = f"{first}쪽 파일({src.name})"

    missing = list(cfg.get("missing_printed", []))
    printed_all = sorted(mapping.values())
    pages: list[PagePlan] = []
    used: set[int] = set()
    for pdf_index, printed in sorted(mapping.items()):
        # 이 쪽 바로 앞(이전 반입 쪽과 이 쪽 사이)에 빠진 쪽
        prev = max((q for q in printed_all if q < printed), default=None)
        before = [m for m in missing if (prev is None or m["printed"] > prev) and m["printed"] < printed]
        if printed in by_page:
            src = by_page[printed]
            used.add(printed)
            nums = footer_numbers(slice_lines(texts[src.name], src.lines))
            if not nums:
                check = "none"
            elif any(footer_matches(n, src.covers) for n in nums):
                check = "match"
            else:
                check = "mismatch:" + ",".join(map(str, nums))
            pages.append(
                PagePlan(
                    pdf_index, printed, "EXTRACTED", src.name, src.covers, src.lines, src.note, before,
                    footer_check=check,
                )
            )
        else:
            reason = "team_text 없음"
            if printed in merged_into:
                reason += f" (이 쪽 내용은 {merged_into[printed]}에 합쳐져 있음)"
            pages.append(PagePlan(pdf_index, printed, "REVIEW_REQUIRED", missing_before=before, reason=reason))
    if unused := sorted(set(by_page) - used):
        errors.append(f"PDF 장에 연결되지 않은 텍스트: {[by_page[p].name for p in unused]}")

    return BookPlan(
        key=cfg["key"],
        subject=cfg["subject"],
        title=cfg["title"],
        material_type=cfg.get("material_type", "textbook"),
        source_name=cfg["source_name"],
        pdf_file=cfg["pdf"],
        text_dir=cfg["text_dir"],
        pdf_page_count=pdf_page_count,
        pages=pages,
        skipped_pdf=list(cfg.get("skip_pdf", [])),
        missing_printed=missing,
        errors=errors,
    )


# ---------- 파일 읽기 ----------


def load_map(settings: Settings) -> dict:
    return json.loads((settings.team_import_path / "page_map.json").read_text(encoding="utf-8"))


def open_pdf(path: Path) -> pdfium.PdfDocument:
    # PDFium은 한글·NFD 경로를 못 여는 경우가 있어 파일 객체로 넘긴다(D-018).
    return pdfium.PdfDocument(path.open("rb"), autoclose=True)


def read_texts(text_dir: Path) -> dict[str, str]:
    # strict utf-8: 인코딩이 다르면 조용히 깨뜨리지 않고 실패한다(2026-09-30 전 파일 UTF-8 확인).
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(text_dir.glob("*.txt"))}


def plan_book(settings: Settings, cfg: dict) -> BookPlan:
    base = settings.team_import_path
    pdf = open_pdf(resolve(base, cfg["pdf"]))
    try:
        count = len(pdf)
    finally:
        pdf.close()
    return build_plan(cfg, count, read_texts(resolve(base, cfg["text_dir"])))


def render_jpeg(pdf: pdfium.PdfDocument, pdf_index: int, dpi: int, quality: int) -> tuple[bytes, int, int]:
    image = pdf[pdf_index - 1].render(scale=dpi / 72).to_pil().convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue(), image.width, image.height


# ---------- 미리보기 (쪽번호 대조) ----------


def preview(settings: Settings, cfg: dict, pdf_indexes: list[int]) -> Path:
    """지정한 장들의 아래쪽 14%를 저해상도로 잘라 한 장으로 붙인다(저장용 이미지와 별개)."""
    from PIL import Image, ImageDraw

    pdf = open_pdf(resolve(settings.team_import_path, cfg["pdf"]))
    strips = []
    try:
        for i in pdf_indexes:
            img = pdf[i - 1].render(scale=settings.team_import_preview_dpi / 72).to_pil().convert("RGB")
            w, h = img.size
            strip = img.crop((0, int(h * 0.86), w, h))
            canvas = Image.new("RGB", (w, strip.height + 16), "white")
            canvas.paste(strip, (0, 16))
            ImageDraw.Draw(canvas).text((4, 2), f"PDF {i}", fill="red")
            strips.append(canvas)
    finally:
        pdf.close()
    width = max(s.width for s in strips)
    sheet = Image.new("RGB", (width, sum(s.height for s in strips)), "white")
    y = 0
    for s in strips:
        sheet.paste(s, (0, y))
        y += s.height
    out = settings.reports_path / "team_import" / f"preview_{cfg['key']}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=85)
    out.write_bytes(buf.getvalue())
    return out


# ---------- 적용 ----------


def apply_book(settings: Settings, plan: BookPlan) -> str:
    """파일 저장 → book 단위 트랜잭션으로 books/processing_runs/pages 기록. 결과 한 줄을 돌려준다."""
    from app.db.connection import connect
    from app.repositories import books as books_repo
    from app.repositories import pages as pages_repo
    from app.repositories import runs as runs_repo
    from app.storage import get_storage

    if plan.errors:
        return f"[{plan.key}] 계획 오류가 있어 건너뜀: {plan.errors}"
    storage = get_storage(settings)
    base = settings.team_import_path
    key_args = {"subject": plan.subject, "title": plan.title, "source_name": plan.source_name}

    with connect(settings) as conn:
        if existing := books_repo.find_book_ids(conn, settings, **key_args):
            return f"[{plan.key}] 이미 반입됨(book {existing[0]}) → 건너뜀"

        book_id = uuid.uuid4()
        texts = {nfc(k): v for k, v in read_texts(resolve(base, plan.text_dir)).items()}
        pdf_name = nfc(resolve(base, plan.pdf_file).name)
        saved: list[str] = []
        new_pages: list[pages_repo.NewPage] = []
        try:
            pdf = open_pdf(resolve(base, plan.pdf_file))
            try:
                for n, pp in enumerate(plan.pages):
                    page_id = uuid.uuid4()
                    data, w, h = render_jpeg(
                        pdf, pp.pdf_index, settings.team_import_render_dpi, settings.team_import_jpeg_quality
                    )
                    uri = storage.save(f"books/{book_id}/{page_id}.jpg", data)
                    saved.append(uri)
                    meta: dict = {
                        "pdf_file": pdf_name,
                        "pdf_index": pp.pdf_index,
                        "text_source": TEXT_ENGINE,
                        "render_dpi": settings.team_import_render_dpi,
                    }
                    if pp.missing_before:
                        meta["missing_before"] = pp.missing_before
                    if pp.text_file:
                        text = slice_lines(texts[pp.text_file], pp.text_lines)  # 원문 그대로(줄 범위만)
                        source = {
                            "engine": TEXT_ENGINE,
                            "source_file": pp.text_file,
                            "covers_pages": pp.covers_pages,
                            "lines": pp.text_lines,
                            "note": pp.text_note,
                        }
                        t_uri = storage.save(
                            text_key(book_id, page_id),
                            json.dumps({**source, "text": text}, ensure_ascii=False).encode("utf-8"),
                        )
                        saved.append(t_uri)
                        meta["text"] = {"uri": t_uri, **source, "char_count": len(text)}
                    new_pages.append(
                        pages_repo.NewPage(
                            id=page_id,
                            source_uri=uri,
                            width=w,
                            height=h,
                            upload_index=n,
                            original_filename=f"{pdf_name}#{pp.pdf_index}",
                            printed_page_number=str(pp.printed),
                            extra_metadata=meta,
                        )
                    )
            finally:
                pdf.close()

            now = datetime.now(UTC).isoformat()
            with conn.transaction():
                if existing := books_repo.find_book_ids(conn, settings, **key_args):
                    raise RuntimeError(f"렌더링 중 다른 실행이 먼저 반입함(book {existing[0]})")
                books_repo.create_book(
                    conn, settings, material_type=plan.material_type, book_id=book_id, **key_args
                )
                run_id = runs_repo.create_run(
                    conn, settings, pipeline_version=f"team-import-{IMPORT_VERSION}", page_count=len(new_pages)
                )
                pages_repo.insert_pages(conn, settings, book_id, run_id, new_pages)
                review = 0
                for np_, pp in zip(new_pages, plan.pages, strict=True):
                    info = {"stage": "extract_text", "source": TEXT_ENGINE, "updated_at": now}
                    if pp.status == "REVIEW_REQUIRED":
                        info["reason"] = pp.reason
                        review += 1
                    pages_repo.set_status(conn, settings, np_.id, pp.status, info)
                # EXTRACTED 페이지는 이후 단계가 남았으므로 미완료로 센다 → run은 PARTIAL
                status = runs_repo.finish_run(
                    conn, settings, run_id, success=0, review=review, failure=0,
                    incomplete=len(new_pages) - review,
                )
        except BaseException:
            for u in saved:
                try:
                    storage.delete(u)
                except Exception:
                    pass
            raise
    # books·processing_runs에는 메모 컬럼이 없으므로 누락 쪽·특이사항은 반입 리포트에 남긴다.
    report = {
        "key": plan.key,
        "book_id": str(book_id),
        "run_id": str(run_id),
        "run_status": status,
        "imported_at": now,
        "pdf_file": pdf_name,
        "page_count": len(new_pages),
        "review_count": review,
        "missing_printed": plan.missing_printed,
        "skipped_pdf": plan.skipped_pdf,
        "text_notes": [
            {"printed": p.printed, "pdf_index": p.pdf_index, "file": p.text_file, "note": p.text_note}
            for p in plan.pages
            if p.text_note
        ],
    }
    out = settings.reports_path / "team_import" / f"apply_{plan.key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return (
        f"[{plan.key}] 반입 완료 book={book_id} run={run_id}({status}) pages={len(new_pages)} "
        f"review={review} 리포트={out}"
    )


# ---------- 출력 ----------


def summarize(plan: BookPlan) -> list[str]:
    ext = [p for p in plan.pages if p.status == "EXTRACTED"]
    rev = [p for p in plan.pages if p.status == "REVIEW_REQUIRED"]
    printed = [p.printed for p in plan.pages]
    checks: dict[str, int] = {}
    for p in ext:
        k = p.footer_check.split(":")[0] if p.footer_check else "none"
        checks[k] = checks.get(k, 0) + 1
    lines = [
        f"[{plan.key}] {plan.title}",
        f"  PDF {plan.pdf_file}: {plan.pdf_page_count}장 → pages 행 {len(plan.pages)}개 "
        f"(쪽 {min(printed)}~{max(printed)}), EXTRACTED {len(ext)} / REVIEW_REQUIRED {len(rev)}",
        f"  텍스트 끝 쪽번호 대조: {checks}",
    ]
    for s in plan.skipped_pdf:
        lines.append(f"  건너뛰는 PDF 장: {s['pdf']}장 — {s['reason']}")
    for m in plan.missing_printed:
        lines.append(f"  없는 쪽: {m['printed']}쪽 — {m['reason']}")
    for p in rev:
        lines.append(f"  REVIEW_REQUIRED: PDF {p.pdf_index}장 = {p.printed}쪽 — {p.reason}")
    for p in plan.pages:
        for m in p.missing_before:
            lines.append(f"  앞쪽 누락 기록: PDF {p.pdf_index}장 = {p.printed}쪽 (앞에 {m['printed']}쪽 없음)")
    for p in ext:
        if p.text_note or len(p.covers_pages) > 1:
            lines.append(
                f"  특수 텍스트: PDF {p.pdf_index}장 = {p.printed}쪽 ← {p.text_file} "
                f"(덮는 쪽 {p.covers_pages}, 줄 {p.text_lines or '전체'}) {p.text_note or ''}"
            )
        if p.footer_check and p.footer_check.startswith("mismatch"):
            lines.append(f"  쪽번호 불일치 의심: PDF {p.pdf_index}장 = {p.printed}쪽, 텍스트 끝 {p.footer_check}")
    for e in plan.errors:
        lines.append(f"  오류: {e}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="팀 교재 반입 (기본 dry-run)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="계획만 출력·저장(기본)")
    mode.add_argument("--apply", action="store_true", help="이미지·텍스트 저장 + DB INSERT")
    mode.add_argument("--preview", metavar="KEY:장,장", help="쪽번호 대조용 저해상도 띠 이미지 (예: subject3:84,85)")
    ap.add_argument(
        "--subject", metavar="KEY[,KEY]", help="대상 과목 page_map key (예: subject1, subject2,subject3, all). --apply에는 필수"
    )
    args = ap.parse_args(argv)
    if args.apply and not args.subject:
        ap.error("--apply에는 --subject가 필요합니다(예: --subject subject1, 전체는 --subject all)")

    settings = get_settings()
    books_cfg = load_map(settings)["books"]
    if args.subject and args.subject != "all":
        keys = args.subject.split(",")
        if unknown := set(keys) - {c["key"] for c in books_cfg}:
            ap.error(f"page_map에 없는 과목: {sorted(unknown)}")
        books_cfg = [c for c in books_cfg if c["key"] in keys]

    if args.preview:
        key, _, idx = args.preview.partition(":")
        cfg = next(c for c in books_cfg if c["key"] == key)
        print(f"미리보기 저장: {preview(settings, cfg, [int(x) for x in idx.split(',')])}")
        return 0

    plans = [plan_book(settings, c) for c in books_cfg]
    for plan in plans:
        print("\n".join(summarize(plan)))

    out = settings.reports_path / "team_import" / "plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(p) for p in plans], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"계획 저장: {out}")

    if not args.apply:
        print(
            f"dry-run: DB·저장소 변경 없음. 저장용 렌더 {settings.team_import_render_dpi} DPI, "
            f"JPEG 품질 {settings.team_import_jpeg_quality}"
        )
        _report_existing(settings, plans)
        return 1 if any(p.errors for p in plans) else 0

    for plan in plans:
        print(apply_book(settings, plan))
    return 0


def _report_existing(settings: Settings, plans: list[BookPlan]) -> None:
    """dry-run에서 재실행 시 건너뛸 과목을 미리 알려 준다(읽기만)."""
    from app.db.connection import connect
    from app.repositories import books as books_repo

    try:
        with connect(settings) as conn:
            for p in plans:
                ids = books_repo.find_book_ids(
                    conn, settings, subject=p.subject, title=p.title, source_name=p.source_name
                )
                print(f"  DB 확인 [{p.key}]: " + (f"이미 있음(book {ids[0]}) → --apply 시 건너뜀" if ids else "없음 → 새로 반입"))
    except Exception as e:
        print(f"  DB 확인 불가: {type(e).__name__}")


if __name__ == "__main__":
    sys.exit(main())
