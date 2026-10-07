"""답변 근거와 연결된 표·시각자료 찾기 (D-J-005). 데이터는 데이터 담당의 공통 JSON 파일을 직접 읽는다.

- 파일: `COMMON_JSON_DIR` 아래(하위 폴더 포함) `*_blocks.json`(블록) + `*_relations.json`(블록 관계).
  `data/` 아래에 두므로 git에 올라가지 않는다. 파일이 없으면 빈 목록(기능 꺼짐과 같음).
- 찾는 법: /qa 근거 중 **답변이 인용한 것(cited)** 의 (과목, 인쇄 쪽) → 그 쪽의 이론 블록 →
  관계(THEORY_TO_TABLE / THEORY_TO_VISUAL)로 연결된 표·시각자료. 신뢰도 `VISUALS_MIN_CONFIDENCE` 이상만,
  최대 `VISUALS_MAX`개. 지금 DB 청크는 공통 JSON 블록 id가 없어 **쪽 단위**로 맞춘다(재적재 후 블록 단위로 교체).
- 과목 번호는 근거의 책 제목("… - 1과목 …")에서 읽는다.
- 화면에서는 그래프를 다시 그리지 않고 원본 crop 이미지 + 설명을 보여 준다(D-015).
"""

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings

log = logging.getLogger(__name__)

_SUBJECT_RE = re.compile(r"(\d+)\s*과목")
_ASSET_TYPES = {"table", "visual"}


@dataclass
class VisualIndex:
    theory_by_page: dict[tuple[int, int], list[str]] = field(default_factory=dict)  # (과목, 쪽) → 이론 block_id
    assets: dict[str, dict] = field(default_factory=dict)  # block_id → 표·시각자료 블록
    links: dict[str, list[tuple[str, float]]] = field(default_factory=dict)  # 이론 block_id → [(자료 block_id, 신뢰도)]


def _subject_of(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_index(blocks: list[dict], relations: list[dict]) -> VisualIndex:
    idx = VisualIndex()
    types: dict[str, str] = {}
    for b in blocks:
        bid, btype = b.get("block_id"), b.get("block_type")
        subject, page = _subject_of(b.get("subject")), _subject_of(b.get("printed_page_number"))
        if not bid or subject is None or page is None:
            continue
        types[bid] = btype
        if btype == "theory":
            idx.theory_by_page.setdefault((subject, page), []).append(bid)
        elif btype in _ASSET_TYPES and (b.get("image") or {}).get("original_url"):
            idx.assets[bid] = b
    for r in relations:
        a, b, conf = r.get("from_block_id"), r.get("to_block_id"), r.get("confidence")
        if conf is None:
            continue
        # 방향과 상관없이 이론 ↔ 표·시각자료 쌍만 쓴다.
        for theory, asset in ((a, b), (b, a)):
            if types.get(theory) == "theory" and asset in idx.assets:
                idx.links.setdefault(theory, []).append((asset, float(conf)))
    return idx


def _load_json_list(path: Path, key: str) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get(key) if isinstance(data, dict) else data
    return [x for x in items or [] if isinstance(x, dict)]


_cache: dict[str, tuple[tuple, VisualIndex]] = {}
_cache_lock = threading.Lock()


def load_index(directory: Path) -> VisualIndex:
    """폴더의 공통 JSON을 읽어 색인을 만든다. 파일이 바뀌면(이름·수정 시각·크기) 다시 읽는다."""
    if not directory.is_dir():
        return VisualIndex()
    files = sorted(directory.rglob("*_blocks.json")) + sorted(directory.rglob("*_relations.json"))
    stamp = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files)
    key = str(directory.resolve())
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        blocks: list[dict] = []
        relations: list[dict] = []
        for p in files:
            try:
                if p.name.endswith("_blocks.json"):
                    blocks += _load_json_list(p, "blocks")
                else:
                    relations += _load_json_list(p, "block_relations")
            except (OSError, ValueError) as e:
                log.warning("공통 JSON 읽기 실패: %s (%s)", p.name, type(e).__name__)
        idx = build_index(blocks, relations)
        _cache[key] = (stamp, idx)
        return idx


def subject_from_title(book_title: str | None) -> int | None:
    m = _SUBJECT_RE.search(book_title or "")
    return int(m.group(1)) if m else None


def _asset_view(b: dict, confidence: float, linked: list[int]) -> dict:
    image = b.get("image") or {}
    return {
        "asset_id": b.get("source_id"),
        "block_id": b.get("block_id"),
        "kind": b.get("block_type"),
        "title": b.get("title"),
        "concept_name": b.get("concept_name"),
        "subject": _subject_of(b.get("subject")),
        "page": _subject_of(b.get("printed_page_number")),
        "image_url": image.get("original_url"),
        "thumbnail_url": image.get("thumbnail_url"),
        "description": b.get("visual_description"),
        "linked_evidence": sorted(linked),
        "confidence": round(confidence, 2),
    }


def find_visuals(idx: VisualIndex, evidence: list[dict], min_confidence: float, limit: int) -> list[dict]:
    """인용된 근거와 연결된 표·시각자료. 신뢰도 높은 순, 같으면 앞 근거 순."""
    best: dict[str, float] = {}
    linked: dict[str, set[int]] = {}
    first_n: dict[str, int] = {}
    for e in evidence:
        if not e.get("cited"):
            continue
        subject, page = subject_from_title(e.get("book_title")), _subject_of(e.get("page"))
        if subject is None or page is None:
            continue
        for theory in idx.theory_by_page.get((subject, page), []):
            for asset, conf in idx.links.get(theory, []):
                if conf < min_confidence:
                    continue
                best[asset] = max(best.get(asset, 0.0), conf)
                linked.setdefault(asset, set()).add(e["n"])
                first_n.setdefault(asset, e["n"])
    order = sorted(best, key=lambda a: (-best[a], first_n[a], a))[:limit]
    return [_asset_view(idx.assets[a], best[a], list(linked[a])) for a in order]


def visuals_for(settings: Settings, evidence: list[dict]) -> list[dict]:
    """/qa 응답에 붙일 visuals. 공통 JSON이 없거나 읽지 못하면 빈 목록(답변은 막지 않음)."""
    try:
        idx = load_index(settings.common_json_path)
        return find_visuals(idx, evidence, settings.visuals_min_confidence, settings.visuals_max)
    except Exception as e:  # 그림은 부가 정보라 실패해도 답변을 돌려준다
        log.warning("visuals 찾기 실패: %s", type(e).__name__)
        return []
