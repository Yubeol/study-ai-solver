"""공통 JSON(데이터 담당 결과물) 읽기·검증·임베딩 텍스트 규칙 (D-M-032). DB에 접근하지 않는다.

- 과목 폴더 `subject{n}/`의 `*_blocks.json`(pages, blocks), `*_relations.json`(block_relations, page_relations),
  `*_manifest.json`, `*_validation_report.json`을 읽는다.
- 과목마다 format_version이 달라도 버전으로 분기하지 않는다. 필드가 있으면 쓰고 없으면 건너뛴다.
  컬럼에 넣지 않은 원본 필드는 `source`에 그대로 남긴다.
- 블록 1개 = 검색 단위 1개. 표 중복 이론(duplicate_of_table_id 필드)과 학습목표(block_role=learning_objective)는
  행은 저장하되 검색에서 뺀다(설정으로 다시 넣을 수 있음).
- 임베딩 텍스트
  - 이론: 제목 경로 + clean_text
  - 표: 제목 경로 + [표] 제목 + 행마다 한 줄(table.rows, 병합 셀 빈칸 채움). raw_text는 쓰지 않는다
  - 시각자료: 제목 경로 + [그림] 제목 + 설명 + 구조 + 그림 속 글자(raw_text). related_theory_context는 빼고
  - model_generated(keywords, exam_clues, confusable_concepts)는 저장만 하고 넣지 않는다
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings

BLOCK_TYPES = ("theory", "table", "visual")  # formula·code는 DB CHECK에는 있지만 적재 규칙이 아직 없어 오류로 멈춘다
BLOCK_ROLES = ("content", "learning_objective")
CORPUS = "common_json"  # documents.corpus 값(검색 대상 SEARCH_CORPUS의 common_json과 같은 이름)
BLOCKS_FORMAT = "adsp_common_json"
RELATIONS_FORMAT = "adsp_common_relations"
EXCLUDE_DUPLICATE = "duplicate_of_table"
EXCLUDE_LEARNING_OBJECTIVE = "learning_objective"
IMAGE_KEYS = ("s3_bucket", "s3_region", "original_s3_key", "thumbnail_s3_key")
TITLE_PATH_SEP = " > "
_BLOCK_ID = re.compile(r"^S(\d+):([A-Z]+):(.+)$")
_SUBJECT_DIR = re.compile(r"^subject(\d+)$")

# 블록 필드 → 컬럼(나머지는 source로)
_MAPPED_FIELDS = {
    "block_id", "source_id", "block_type", "block_role", "printed_page_number", "order_in_page", "title",
    "title_path", "concept_name", "raw_text", "clean_text", "table", "image", "duplicate_of_table_id",
    "model_generated", "confidence", "review", "visual_type", "visual_description", "visual_observation",
    "visual_structure", "related_theory_context", "related_theory_context_source",
}
_VISUAL_FIELDS = ("visual_type", "visual_description", "visual_observation", "visual_structure",
                  "related_theory_context", "related_theory_context_source")


class CommonJsonError(Exception):
    """검증 실패. errors에 전체 목록."""

    def __init__(self, errors: list[str]):
        super().__init__(f"공통 JSON 검증 실패 {len(errors)}건: " + "; ".join(errors[:5]))
        self.errors = errors


@dataclass
class BlockRecord:
    """blocks 테이블 1행(임베딩 제외)."""

    block_id: str
    source_id: str
    block_type: str
    block_role: str
    printed_page_number: int
    order_in_page: int | None
    title: str
    title_path: list[str]
    concept_name: str | None
    raw_text: object
    clean_text: str | None
    table_data: dict | None
    visual_data: dict | None
    image: dict | None
    crop_s3_key: str | None
    thumbnail_s3_key: str | None
    duplicate_of_block_id: str | None
    model_generated: dict
    confidence: float | None
    review: dict
    needs_review: bool
    source: dict
    search_enabled: bool
    search_excluded_reason: str | None
    embedding_text: str
    embedding_text_hash: str
    content_hash: str


@dataclass
class RelationRecord:
    relationship_id: str
    from_block_id: str
    to_block_id: str
    from_page: int | None
    to_page: int | None
    link_type: str
    relation_types: list
    relation_source: str
    relation_scope: str | None
    confidence: float | None
    reason: str | None


@dataclass
class SubjectData:
    key: str  # 'subject1'
    subject_no: int
    document_key: str  # '{format}:subject{n}'
    title: str
    source_format: str | None
    format_version: str | None
    manifest: dict
    pages: list[dict]
    page_relations: list[dict]
    blocks: list[BlockRecord]
    relations: list[RelationRecord]
    warnings: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)


# ----- 파일 -----

def subject_no_of(key: str) -> int:
    m = _SUBJECT_DIR.match(key)
    if not m:
        raise ValueError(f"과목 key는 subject{{n}} 형식이어야 함: {key!r}")
    return int(m.group(1))


def available_subjects(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    keys = [p.name for p in root.iterdir() if p.is_dir() and _SUBJECT_DIR.match(p.name)]
    return sorted(keys, key=subject_no_of)


def _find_one(folder: Path, suffix: str, required: bool) -> Path | None:
    found = sorted(folder.glob(f"*{suffix}"))
    if len(found) > 1:
        raise CommonJsonError([f"{folder.name}: *{suffix} 파일이 {len(found)}개"])
    if not found:
        if required:
            raise CommonJsonError([f"{folder.name}: *{suffix} 파일 없음"])
        return None
    return found[0]


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CommonJsonError([f"{path.name}: 읽기 실패({type(e).__name__})"]) from e


def read_subject(settings: Settings, root: Path, key: str) -> SubjectData:
    """과목 폴더를 읽고 검증한다. 오류가 하나라도 있으면 CommonJsonError."""
    n = subject_no_of(key)
    folder = root / key
    if not folder.is_dir():
        raise CommonJsonError([f"과목 폴더 없음: {folder}"])
    paths = {
        "blocks": _find_one(folder, "_blocks.json", True),
        "relations": _find_one(folder, "_relations.json", True),
        "manifest": _find_one(folder, "_manifest.json", False),
        "validation_report": _find_one(folder, "_validation_report.json", False),
    }
    raw = {k: _read_json(p) if p else None for k, p in paths.items()}
    data = build_subject(settings, key, n, raw["blocks"], raw["relations"], raw["manifest"], raw["validation_report"])
    data.files = {k: p.name for k, p in paths.items() if p}
    return data


# ----- 검증 + 변환 -----

def build_subject(settings: Settings, key: str, n: int, blocks_file, relations_file, manifest, report) -> SubjectData:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(blocks_file, dict) or not isinstance(blocks_file.get("blocks"), list):
        raise CommonJsonError([f"{key}: blocks 파일에 blocks 목록 없음"])
    if not isinstance(relations_file, dict) or not isinstance(relations_file.get("block_relations"), list):
        raise CommonJsonError([f"{key}: relations 파일에 block_relations 목록 없음"])
    manifest = manifest if isinstance(manifest, dict) else {}

    for name, f, fmt in (("blocks", blocks_file, BLOCKS_FORMAT), ("relations", relations_file, RELATIONS_FORMAT)):
        if "format" in f and f["format"] != fmt:
            errors.append(f"{name} format {f['format']!r} ≠ {fmt!r}")
        if "subject" in f and f["subject"] != n:
            errors.append(f"{name} subject {f['subject']!r} ≠ {n}")
    if "subject" in manifest and manifest["subject"] != n:
        errors.append(f"manifest subject {manifest['subject']!r} ≠ {n}")
    if isinstance(report, dict) and report.get("passed") is False:
        errors.append(f"validation_report passed=false (errors: {report.get('errors')})")

    raw_blocks = blocks_file["blocks"]
    types: dict[str, str] = {}
    for i, b in enumerate(raw_blocks):
        bid = b.get("block_id") if isinstance(b, dict) else None
        if not isinstance(bid, str) or not bid:
            errors.append(f"blocks[{i}]: block_id 없음")
            continue
        if bid in types:
            errors.append(f"{bid}: block_id 중복")
            continue
        types[bid] = b.get("block_type")

    records: list[BlockRecord] = []
    pending = settings.common_json_pending_block_id_set
    for b in raw_blocks:
        if not isinstance(b, dict) or not isinstance(b.get("block_id"), str):
            continue
        errs = _check_block(b, n, types)
        if errs:
            errors += errs
            continue
        rec = _to_record(settings, b, n)
        records.append(rec)
        if rec.block_role == "learning_objective" and rec.duplicate_of_block_id:
            warnings.append(f"{rec.block_id}: 학습목표인데 duplicate_of_table_id={b['duplicate_of_table_id']} (확인 필요)")
        if rec.block_id in pending:
            warnings.append(f"{rec.block_id}: 수정본 대기 블록(COMMON_JSON_PENDING_BLOCK_IDS)")

    relations, rel_errors = _relations(relations_file["block_relations"], types)
    errors += rel_errors
    warnings += _duplicate_relation_warnings(relations, {r.block_id: r for r in records})

    pages = blocks_file.get("pages") if isinstance(blocks_file.get("pages"), list) else []
    page_numbers = set()
    for p in pages:
        if not isinstance(p, dict):
            errors.append("pages: 항목이 객체가 아님")
            continue
        page_numbers.add(p.get("printed_page_number"))
        for bid in p.get("block_ids_in_reading_order") or []:
            if bid not in types:
                errors.append(f"pages {p.get('printed_page_number')}: reading_order의 {bid} 블록 없음")
    if pages:
        for r in records:
            if r.printed_page_number not in page_numbers:
                errors.append(f"{r.block_id}: 쪽 {r.printed_page_number}이 pages에 없음")

    if errors:
        raise CommonJsonError([f"{key}: {e}" for e in errors])

    title = manifest.get("subject_name") or next(
        (p.get("subject_name") for p in pages if isinstance(p, dict) and p.get("subject_name")), None
    ) or f"{n}과목"
    fmt = blocks_file.get("format") or BLOCKS_FORMAT
    page_relations = relations_file.get("page_relations")
    return SubjectData(
        key=key,
        subject_no=n,
        document_key=f"{fmt}:{key}",
        title=title,
        source_format=blocks_file.get("format"),
        format_version=blocks_file.get("format_version"),
        manifest=manifest,
        pages=pages,
        page_relations=page_relations if isinstance(page_relations, list) else [],
        blocks=records,
        relations=relations,
        warnings=warnings,
    )


def _is_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _check_block(b: dict, n: int, types: dict[str, str]) -> list[str]:
    bid = b["block_id"]
    errs = []
    btype = b.get("block_type")
    if btype not in BLOCK_TYPES:
        return [f"{bid}: 적재 규칙이 없는 block_type {btype!r}"]
    m = _BLOCK_ID.match(bid)
    if not m:
        errs.append(f"{bid}: block_id 형식이 S{{과목}}:{{TYPE}}:{{source_id}}가 아님")
    else:
        if int(m.group(1)) != n:
            errs.append(f"{bid}: block_id 과목 번호 ≠ {n}")
        if m.group(2) != btype.upper():
            errs.append(f"{bid}: block_id 타입 ≠ block_type {btype}")
        if "source_id" in b and b["source_id"] != m.group(3):
            errs.append(f"{bid}: source_id {b['source_id']!r} 불일치")
    if "subject" in b and b["subject"] != n:
        errs.append(f"{bid}: subject {b['subject']!r} ≠ {n}")
    if not isinstance(b.get("printed_page_number"), int) or isinstance(b.get("printed_page_number"), bool):
        errs.append(f"{bid}: printed_page_number가 정수가 아님")
    tp = b.get("title_path")
    if not (isinstance(tp, list) and len(tp) == 2 and all(_is_str(x) for x in tp)):
        errs.append(f"{bid}: title_path는 비지 않은 문자열 2개여야 함")
    if not _is_str(b.get("title")):
        errs.append(f"{bid}: title 없음")
    role = b.get("block_role")
    if role not in (None, "") and role not in BLOCK_ROLES:
        errs.append(f"{bid}: block_role {role!r} 허용값 아님")

    if btype == "theory":
        if not isinstance(b.get("raw_text"), str):
            errs.append(f"{bid}: 이론 raw_text가 문자열이 아님")
        if not _is_str(b.get("clean_text")):
            errs.append(f"{bid}: 이론 clean_text 없음")
        dup = b.get("duplicate_of_table_id")
        if dup is not None:
            target = resolve_duplicate(dup, n)
            if types.get(target) != "table":
                errs.append(f"{bid}: duplicate_of_table_id {dup!r} → {target} 표 블록 없음")
    else:
        image = b.get("image")
        if not isinstance(image, dict) or not all(_is_str(image.get(k)) for k in IMAGE_KEYS):
            errs.append(f"{bid}: image에 {', '.join(IMAGE_KEYS)} 필요")
    if btype == "table":
        errs += _check_table(bid, b.get("table"))
    if btype == "visual":
        if not (_is_str(b.get("visual_description")) or _is_str(b.get("visual_structure")) or _raw_words(b.get("raw_text"))):
            errs.append(f"{bid}: 시각자료 설명·구조·그림 속 글자가 모두 비어 있음")
    return errs


def _check_table(bid: str, t) -> list[str]:
    if not isinstance(t, dict):
        return [f"{bid}: table 없음"]
    rows = t.get("rows")
    if not (isinstance(rows, list) and rows and all(isinstance(r, list) and r for r in rows)):
        return [f"{bid}: table.rows는 비지 않은 행 목록이어야 함"]
    errs = []
    if any(not isinstance(c, str) for r in rows for c in r):
        errs.append(f"{bid}: table.rows 칸이 문자열이 아님")
    headers = t.get("headers") or []
    if not isinstance(headers, list):
        errs.append(f"{bid}: table.headers가 목록이 아님")
    elif headers and any(len(r) != len(headers) for r in rows):
        errs.append(f"{bid}: table.rows 칸 수가 headers({len(headers)})와 다름")
    for m in t.get("merged_cells") or []:
        try:
            r0, r1, c0, c1 = (int(m[k]) for k in ("start_row", "end_row", "start_col", "end_col"))
        except (KeyError, TypeError, ValueError):
            errs.append(f"{bid}: merged_cells 형식 오류")
            continue
        if not (0 <= r0 <= r1 < len(rows) and 0 <= c0 <= c1 and all(c1 < len(rows[r]) for r in range(r0, r1 + 1))):
            errs.append(f"{bid}: merged_cells 범위가 rows 밖")
    return errs


def resolve_duplicate(value: str, n: int) -> str:
    """duplicate_of_table_id는 source_id('TAB_104_01')로 온다 → 'S{n}:TABLE:TAB_104_01'. 전체 id면 그대로."""
    return value if ":" in value else f"S{n}:TABLE:{value}"


def _relations(items: list, types: dict[str, str]) -> tuple[list[RelationRecord], list[str]]:
    errors, out = [], []
    seen_ids, seen_pairs = set(), set()
    for i, r in enumerate(items):
        if not isinstance(r, dict):
            errors.append(f"block_relations[{i}]: 객체가 아님")
            continue
        rid = r.get("relationship_id")
        a, b = r.get("from_block_id"), r.get("to_block_id")
        label = rid or f"block_relations[{i}]"
        if not _is_str(rid):
            errors.append(f"{label}: relationship_id 없음")
        elif rid in seen_ids:
            errors.append(f"{rid}: relationship_id 중복")
        seen_ids.add(rid)
        if a not in types or b not in types:
            errors.append(f"{label}: 끝점 블록 없음({a} → {b})")
            continue
        expected = f"{types[a].upper()}_TO_{types[b].upper()}"
        if r.get("link_type") != expected:
            errors.append(f"{label}: link_type {r.get('link_type')!r} ≠ {expected}")
        if (a, b) in seen_pairs:
            errors.append(f"{label}: ({a}, {b}) 관계 중복")
        seen_pairs.add((a, b))
        if not _is_str(r.get("relation_source")):
            errors.append(f"{label}: relation_source 없음")
        rtypes = r.get("relation_types", [])
        if not isinstance(rtypes, list):
            errors.append(f"{label}: relation_types가 목록이 아님")
            rtypes = []
        out.append(RelationRecord(
            relationship_id=rid, from_block_id=a, to_block_id=b,
            from_page=r.get("from_page"), to_page=r.get("to_page"), link_type=expected,
            relation_types=rtypes, relation_source=r.get("relation_source"),
            relation_scope=r.get("relation_scope"), confidence=r.get("confidence"), reason=r.get("reason"),
        ))
    return out, errors


def _duplicate_relation_warnings(relations: list[RelationRecord], records: dict[str, BlockRecord]) -> list[str]:
    """relation_source=duplicate_of_table_id 관계인데 이론 블록의 필드가 그 표를 가리키지 않으면 경고(적재는 진행).

    중복 판단은 블록 필드가 기준이다. 필드는 있는데 관계가 없는 경우(1과목)는 정상이라 경고하지 않는다.
    """
    out = []
    for r in relations:
        if r.relation_source != "duplicate_of_table_id":
            continue
        a, b = records.get(r.from_block_id), records.get(r.to_block_id)
        if a is None or b is None:
            continue
        theory, table = (a, b) if a.block_type == "theory" else (b, a)
        if theory.block_type != "theory" or table.block_type != "table" or theory.duplicate_of_block_id != table.block_id:
            out.append(f"{r.relationship_id}: duplicate_of_table_id 관계({r.from_block_id} → {r.to_block_id})가 "
                       f"블록 필드와 맞지 않음(블록 필드 기준으로 처리)")
    return out


def _to_record(settings: Settings, b: dict, n: int) -> BlockRecord:
    btype = b["block_type"]
    role = b.get("block_role") or "content"  # 표·시각자료는 block_role이 없거나 비어 있음 → content
    dup = resolve_duplicate(b["duplicate_of_table_id"], n) if btype == "theory" and b.get("duplicate_of_table_id") else None
    review = b.get("review") if isinstance(b.get("review"), dict) else {}
    image = b.get("image") if isinstance(b.get("image"), dict) else None

    reason = None
    if dup and not settings.common_json_search_duplicate_theory:
        reason = EXCLUDE_DUPLICATE
    elif role == "learning_objective" and not settings.common_json_search_learning_objective:
        reason = EXCLUDE_LEARNING_OBJECTIVE

    text = embedding_text(b)
    return BlockRecord(
        block_id=b["block_id"],
        source_id=b.get("source_id") or _BLOCK_ID.match(b["block_id"]).group(3),
        block_type=btype,
        block_role=role,
        printed_page_number=b["printed_page_number"],
        order_in_page=b.get("order_in_page") if isinstance(b.get("order_in_page"), int) else None,
        title=b["title"],
        title_path=list(b["title_path"]),
        concept_name=b.get("concept_name"),
        raw_text=b.get("raw_text"),
        clean_text=b.get("clean_text") if isinstance(b.get("clean_text"), str) else None,
        table_data=b.get("table") if btype == "table" else None,
        visual_data={k: b[k] for k in _VISUAL_FIELDS if k in b} if btype == "visual" else None,
        image=image,
        crop_s3_key=(image or {}).get("original_s3_key"),
        thumbnail_s3_key=(image or {}).get("thumbnail_s3_key"),
        duplicate_of_block_id=dup,
        model_generated=b.get("model_generated") if isinstance(b.get("model_generated"), dict) else {},
        confidence=b.get("confidence"),
        review=review,
        needs_review=bool(review.get("needs_review")),
        source={k: v for k, v in b.items() if k not in _MAPPED_FIELDS},
        search_enabled=reason is None,
        search_excluded_reason=reason,
        embedding_text=text,
        embedding_text_hash=sha256(text),
        content_hash=sha256(json.dumps(b, ensure_ascii=False, sort_keys=True)),
    )


# ----- 임베딩 텍스트 -----

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def one_line(s) -> str:
    return " ".join(str(s).split())


def _raw_words(v) -> list[str]:
    if isinstance(v, list):
        return [one_line(x) for x in v if isinstance(x, str) and x.strip()]
    if isinstance(v, str) and v.strip():
        return [one_line(v)]
    return []


def fill_merged_cells(table: dict) -> list[list[str]]:
    """rows 복사본에서 병합 셀 범위의 빈 칸만 merged_cells.text로 채운다(이미 값이 있는 칸은 그대로)."""
    rows = [list(r) for r in table.get("rows") or []]
    for m in table.get("merged_cells") or []:
        for r in range(m["start_row"], m["end_row"] + 1):
            for c in range(m["start_col"], m["end_col"] + 1):
                if r < len(rows) and c < len(rows[r]) and not str(rows[r][c]).strip():
                    rows[r][c] = m.get("text") or ""
    return rows


def linearize_table(table: dict) -> str:
    """표 → 행마다 한 줄.

    - 머리행이 있으면 "- 머리1: 값 | 머리2: 값"(빈 머리행 칸은 값만, 빈 값은 생략)
    - 머리행이 없으면 첫 칸을 행 이름으로 "- 행이름: 값 / 값"(row_headers는 rows 첫 칸과 겹쳐 쓰지 않음)
    - units가 있으면 마지막에 "단위: …"
    """
    headers = [one_line(h) for h in table.get("headers") or []]
    lines = []
    for row in fill_merged_cells(table):
        cells = [one_line(c) for c in row]
        if any(headers):
            parts = [f"{h}: {c}" if h else c for h, c in zip(headers, cells) if c]
            lines.append("- " + " | ".join(parts))
        else:
            head, rest = cells[0], [c for c in cells[1:] if c]
            lines.append(f"- {head}: {' / '.join(rest)}" if rest else f"- {head}")
    units = [one_line(u) for u in table.get("units") or [] if str(u).strip()]
    if units:
        lines.append("단위: " + ", ".join(units))
    return "\n".join(lines)


def embedding_text(b: dict, *, with_path: bool = True) -> str:
    """블록 → 텍스트. 기본(with_path=True)은 적재 때 저장하는 임베딩 텍스트(바꾸면 재임베딩).

    with_path=False는 맨 앞 제목 경로만 뺀다. 질의 때 LLM·판정기에 넘기는 근거 본문으로 쓴다(D-M-033,
    제목 경로는 프롬프트에 따로 들어감). b는 원본 블록 또는 block_from_row(DB 행).
    """
    path = TITLE_PATH_SEP.join(one_line(x) for x in b["title_path"])
    btype = b["block_type"]
    if btype == "theory":
        return f"{path}\n\n{b['clean_text'].strip()}" if with_path else b["clean_text"].strip()
    head = f"{path}\n" if with_path else ""
    if btype == "table":
        return f"{head}[표] {one_line(b['title'])}\n{linearize_table(b['table'])}"
    parts = [f"{head}[그림] {one_line(b['title'])}"]
    if _is_str(b.get("visual_description")):
        parts.append(f"설명: {b['visual_description'].strip()}")
    if _is_str(b.get("visual_structure")):
        parts.append(f"구조: {b['visual_structure'].strip()}")
    words = _raw_words(b.get("raw_text"))
    if words:
        parts.append("그림 속 글자: " + " · ".join(words))
    return "\n".join(parts)


def raw_text_display(raw) -> str:
    """blocks.raw_text(JSONB) → 화면 표시용 문자열. 이론(문자열)은 그대로, 표·그림(원문 목록)은 줄바꿈으로 잇기만 한다."""
    if isinstance(raw, list):
        return "\n".join(str(x) for x in raw)
    return "" if raw is None else str(raw)


def block_from_row(row: dict) -> dict:
    """blocks 테이블 행 → embedding_text 입력(원본 블록과 같은 키). 표는 table_data, 그림 필드는 visual_data에 있다."""
    return {
        "block_type": row["block_type"],
        "title": row["title"],
        "title_path": row["title_path"],
        "clean_text": row["clean_text"],
        "raw_text": row["raw_text"],
        "table": row.get("table_data"),
        **(row.get("visual_data") or {}),
    }


# ----- 적재 계획 (DB 상태와 비교) -----

@dataclass
class ExistingBlock:
    content_hash: str
    embedding_text_hash: str | None
    has_embedding: bool
    embedding_model: str | None
    search_enabled: bool


@dataclass
class BlockPlan:
    record: BlockRecord
    status: str  # new / changed / unchanged
    embed: bool  # 이번에 임베딩을 계산하는지
    clear_embedding: bool  # 검색 제외라 임베딩을 지우는지


def plan_blocks(records: list[BlockRecord], existing: dict[str, ExistingBlock], model: str) -> list[BlockPlan]:
    """블록별 처리. 임베딩은 검색 대상이면서 (없음 / 텍스트 바뀜 / 모델 바뀜)일 때만 계산한다."""
    out = []
    for r in records:
        old = existing.get(r.block_id)
        if old is None:
            status = "new"
        elif old.content_hash != r.content_hash or old.search_enabled != r.search_enabled:
            status = "changed"
        else:
            status = "unchanged"
        embed = r.search_enabled and (
            old is None or not old.has_embedding or old.embedding_text_hash != r.embedding_text_hash
            or old.embedding_model != model
        )
        clear = not r.search_enabled and old is not None and old.has_embedding
        if (embed or clear) and status == "unchanged":
            status = "changed"
        out.append(BlockPlan(record=r, status=status, embed=embed, clear_embedding=clear))
    return out


def select_blocks(data: SubjectData, block_ids: list[str]) -> list[BlockRecord]:
    """--block-id 지정분만. 없는 id가 있으면 오류."""
    if not block_ids:
        return data.blocks
    by_id = {r.block_id: r for r in data.blocks}
    if missing := [b for b in block_ids if b not in by_id]:
        raise CommonJsonError([f"{data.key}: 파일에 없는 block_id {', '.join(missing)}"])
    return [by_id[b] for b in block_ids]


def summarize(data: SubjectData) -> dict:
    """블록 수(종류별), 검색 대상·제외 사유별 수."""
    by_type: dict[str, int] = {}
    searchable: dict[str, int] = {}
    excluded: dict[str, int] = {}
    for r in data.blocks:
        by_type[r.block_type] = by_type.get(r.block_type, 0) + 1
        if r.search_enabled:
            searchable[r.block_type] = searchable.get(r.block_type, 0) + 1
        else:
            excluded[r.search_excluded_reason] = excluded.get(r.search_excluded_reason, 0) + 1
    return {
        "blocks": len(data.blocks),
        "by_type": by_type,
        "searchable": sum(searchable.values()),
        "searchable_by_type": searchable,
        "excluded": excluded,
        "relations": len(data.relations),
        "page_relations": len(data.page_relations),
        "pages": len(data.pages),
    }
