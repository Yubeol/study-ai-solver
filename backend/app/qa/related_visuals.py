"""근거에 연결된 그림·표 이미지 붙이기(D-JW-008). /qa 근거(K개)가 정해진 뒤 후처리로만 붙인다.

- 대상: kind = theory이고 block_id가 있는 근거(공통 JSON 이론 블록).
- 연결: mingyu_app.block_relations(THEORY_TO_VISUAL / THEORY_TO_TABLE / VISUAL_TO_THEORY / TABLE_TO_THEORY, 양방향).
- 거르기: 신뢰도 ≥ RELATED_VISUAL_MIN_CONFIDENCE, 근거당 최대 RELATED_VISUAL_MAX개(신뢰도 높은 순),
  이미 근거 목록에 있는 블록 제외, 이미지 주소를 만들 수 없는 블록 제외(키 없음 또는 ASSET_URL_TEMPLATE 비어 있음).
- 결과: evidence[i]["related_visuals"] = [{block_id, kind, title, thumbnail_url, image_url}] (없으면 []).
- 이미지는 부가 정보라 조회가 실패해도 답변은 막지 않는다(경고 로그만, 빈 목록).
"""

import logging

import psycopg

from app.core.config import Settings
from app.repositories import related_visuals as related_repo

log = logging.getLogger(__name__)


def _view(settings: Settings, r: dict) -> dict | None:
    image_url = settings.asset_url(r.get("crop_s3_key"))
    thumbnail_url = settings.asset_url(r.get("thumbnail_s3_key"))
    if image_url is None and thumbnail_url is None:
        return None
    return {
        "block_id": r["block_id"],
        "kind": r["block_type"],
        "title": r.get("title"),
        "thumbnail_url": thumbnail_url or image_url,
        "image_url": image_url or thumbnail_url,
    }


def attach(evidence: list[dict], rows: list[dict], settings: Settings) -> None:
    """조회 결과(rows)를 걸러 각 근거에 related_visuals를 넣는다(evidence를 고침)."""
    in_evidence = {e.get("block_id") for e in evidence if e.get("block_id")}
    by_source: dict[str, list[dict]] = {}
    for r in rows:
        conf = r.get("confidence")
        if conf is None or conf < settings.related_visual_min_confidence or r["block_id"] in in_evidence:
            continue
        by_source.setdefault(r["source_block_id"], []).append(r)
    for e in evidence:
        out: list[dict] = []
        seen: set[str] = set()
        if e.get("kind") == "theory" and e.get("block_id"):
            cands = sorted(by_source.get(e["block_id"], []), key=lambda r: (-r["confidence"], r["block_id"]))
            for r in cands:
                if len(out) >= settings.related_visual_max:
                    break
                if r["block_id"] in seen:
                    continue
                view = _view(settings, r)
                if view is not None:
                    seen.add(r["block_id"])
                    out.append(view)
        e["related_visuals"] = out


def add_related_visuals(conn: psycopg.Connection | None, settings: Settings, evidence: list[dict]) -> None:
    """근거 K개의 이론 block_id로 한 번에 조회해서 붙인다. 조회할 게 없거나 실패하면 모두 []."""
    ids = sorted({e["block_id"] for e in evidence if e.get("kind") == "theory" and e.get("block_id")})
    rows: list[dict] = []
    if ids and conn is not None and settings.related_visual_max > 0:
        try:
            rows = related_repo.fetch(conn, settings, ids)
        except psycopg.Error as e:
            log.warning("연결 그림·표 조회 실패: %s", type(e).__name__)
            rows = []
    attach(evidence, rows, settings)
