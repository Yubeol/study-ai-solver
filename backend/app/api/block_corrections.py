"""이론 블록 수정 API (D-JW-007, 마감 축소판). 오류 신고 화면(ReportDrawer)에서 수정안을 등록·승인한다.

- 대상: mingyu_app.blocks의 이론 블록(block_type = theory)의 clean_text만. 표·시각자료는 400
  (내용이 table_data·visual_data에 있어 clean_text로 못 고침 → 신고 resolution = source_fix_requested).
- 등록: 지금 DB clean_text(base_clean_text)와 JSON 원문 해시(blocks.source_clean_text_hash)를 복사해 proposed로 저장.
- 승인: 블록의 원문 해시가 수정안 작성 때와 같은지 확인(다르면 stale, 409) → 새 embedding_text 생성
  (common_json.embedding_text(block_from_row(행), with_path=True) — 리랭커가 embedding_text 칸을 읽음) → 서버에 올라와 있는 임베딩 모델로 계산 → 한 트랜잭션에서
  이전 적용 수정 superseded, 블록 clean_text·임베딩 갱신, 이 수정 applied. 다음 질문부터 검색에 반영된다.
  report_id가 있으면 신고도 resolved(block_corrected)로 닫는다(resolve_report=false면 그대로).
- 한계: 공통 JSON을 다시 적재하면 원문으로 덮어써진다(수정 기록은 남음, D-JW-007). 인증 없음(내부용).
"""

from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import get_conn, get_settings
from app.core.config import Settings
from app.ingestion.common_json import TITLE_PATH_SEP, block_from_row, embedding_text, sha256
from app.ingestion.embedding import to_pgvector
from app.repositories import answer_reports as reports_repo
from app.repositories import block_corrections as repo

router = APIRouter(tags=["block-corrections"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

MAX_CLEAN_TEXT = 2000  # 005 CHECK와 같은 값(D-JW-007: theory 최대 694자 기준)
CorrectionStatus = Literal["proposed", "approved", "applied", "rejected", "withdrawn", "stale", "superseded"]


class CorrectionCreate(BaseModel):
    block_id: str = Field(min_length=1, max_length=100, description="예: S1:THEORY:TH_62_02 (/qa 근거의 block_id)")
    new_clean_text: str = Field(max_length=MAX_CLEAN_TEXT, description="공백·탭·줄바꿈뿐이면 400")
    reason: str = Field(default="", max_length=500)
    report_id: UUID | None = Field(default=None, description="어느 오류 신고에서 나온 수정인지(선택)")


class Review(BaseModel):
    reviewed_by: str | None = Field(default=None, max_length=100)
    review_note: str = Field(default="", max_length=500)


class Approve(Review):
    resolve_report: bool = Field(default=True, description="report_id가 있으면 신고를 resolved(block_corrected)로 닫기")


def _block_view(b: dict, active: dict | None) -> dict:
    return {
        "block_id": b["block_id"],
        "kind": b["block_type"],  # /qa evidence의 kind와 같은 값
        "block_type": b["block_type"],
        "title": b["title"],
        "title_path": b["title_path"] or [],
        "path": TITLE_PATH_SEP.join(b["title_path"] or []) or b["title"],
        "page": b["printed_page_number"],
        "document_title": b["document_title"],
        "clean_text": b["clean_text"],
        "editable": b["block_type"] == "theory" and b["source_clean_text_hash"] is not None,
        "active_correction_id": active["id"] if active else None,
        "updated_at": b["updated_at"],
    }


@router.get("/blocks/{block_id}")
def get_block(block_id: str, conn: Conn, settings: SettingsDep) -> dict:
    """수정 화면용: 블록의 지금 clean_text와 수정 가능 여부(이론 블록만 editable)."""
    b = repo.get_block(conn, settings, block_id)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "블록을 찾을 수 없습니다.")
    return _block_view(b, repo.active_for_block(conn, settings, block_id))


@router.post("/block-corrections", status_code=status.HTTP_201_CREATED)
def create_correction(body: CorrectionCreate, conn: Conn, settings: SettingsDep) -> dict:
    """수정안 등록(proposed). 블록은 아직 바뀌지 않는다."""
    new_text = body.new_clean_text.strip()
    if not new_text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "수정할 내용을 입력해 주세요(공백·탭·줄바꿈만 있음).")
    b = repo.get_block(conn, settings, body.block_id)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "블록을 찾을 수 없습니다.")
    if b["block_type"] != "theory":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "이론 블록만 고칠 수 있습니다(표·시각자료는 데이터 담당에게 JSON 수정 요청).")
    if b["source_clean_text_hash"] is None or b["clean_text"] is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "원문 해시가 없는 블록입니다(005 백필 확인 필요).")
    if new_text == b["clean_text"].strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지금 내용과 같습니다.")
    if body.report_id is not None and not reports_repo.report_exists(conn, settings, body.report_id):
        raise HTTPException(422, "report_id에 해당하는 오류 신고가 없습니다.")
    return repo.insert(conn, settings, block_id=body.block_id, report_id=body.report_id,
                       base_clean_text=b["clean_text"], base_clean_text_hash=b["source_clean_text_hash"],
                       new_clean_text=new_text, reason=body.reason.strip())


@router.get("/block-corrections")
def list_corrections(
    conn: Conn,
    settings: SettingsDep,
    status_: Annotated[CorrectionStatus | None, Query(alias="status")] = None,
    block_id: str | None = None,
    report_id: UUID | None = None,
    limit: Annotated[int, Query(gt=0, le=200)] = 50,
) -> list[dict]:
    """수정안 목록(최신순). 검토 대기는 status=proposed."""
    return repo.list_(conn, settings, status=status_, block_id=block_id, report_id=report_id, limit=limit)


def _proposed(conn, settings, correction_id: UUID) -> dict:
    c = repo.get(conn, settings, correction_id, for_update=True)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "수정안을 찾을 수 없습니다.")
    if c["status"] != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"검토 대기(proposed) 수정안만 처리할 수 있습니다(지금 {c['status']}).")
    return c


@router.post("/block-corrections/{correction_id}/approve")
def approve(correction_id: UUID, body: Approve, request: Request, conn: Conn, settings: SettingsDep) -> dict:
    """승인 = 블록 clean_text 수정 + 재임베딩(바로 검색에 반영)."""
    models = getattr(request.app.state, "qa_models", None)
    embedder = getattr(models, "embedder", None)
    if embedder is None:
        raise HTTPException(503, "임베딩 모델이 로드되지 않았습니다(PRELOAD_MODELS=false).")

    c = repo.get(conn, settings, correction_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "수정안을 찾을 수 없습니다.")
    b = repo.get_block(conn, settings, c["block_id"])
    if b is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "블록이 없어졌습니다(재적재 확인).")
    # 임베딩은 시간이 걸리므로 트랜잭션 밖에서 먼저 계산하고, 안에서 원문 해시를 다시 확인한다.
    # embedding_text는 적재와 같은 함수로 만든다(리랭커가 이 칸을 읽으므로 clean_text·embedding과 같이 바꿈).
    text = embedding_text(block_from_row(dict(b) | {"clean_text": c["new_clean_text"]}), with_path=True)
    vec = to_pgvector(embedder.encode([text])[0])
    model = settings.embedding_model

    stale = False
    with conn.transaction():
        c = _proposed(conn, settings, correction_id)
        b = repo.get_block(conn, settings, c["block_id"], for_update=True)
        if b is None or b["source_clean_text_hash"] != c["base_clean_text_hash"]:
            stale = True
            repo.set_status(conn, settings, correction_id, "stale", review_note=body.review_note,
                            reviewed_by=body.reviewed_by,
                            applied_note="블록 없음" if b is None else "원문 해시가 수정안 작성 때와 다름")
        else:
            repo.supersede_active(conn, settings, c["block_id"], correction_id)
            repo.apply_to_block(conn, settings, c["block_id"], clean_text=c["new_clean_text"], embedding_text=text,
                                embedding_text_hash=sha256(text), embedding=vec, embedding_model=model)
            out = repo.set_status(conn, settings, correction_id, "applied", review_note=body.review_note,
                                  reviewed_by=body.reviewed_by, applied_note=f"재임베딩 {model}")
            if body.resolve_report and c["report_id"] is not None:
                reports_repo.update_review(conn, settings, c["report_id"], status="resolved",
                                           resolution="block_corrected", resolution_note=body.review_note or None,
                                           linked_block_ids=None, reviewed_by=body.reviewed_by)
    if stale:
        raise HTTPException(status.HTTP_409_CONFLICT, "교재 원문이 수정안 작성 뒤 바뀌었습니다. 새 수정안을 만들어 주세요.")
    return out


def _close(correction_id: UUID, new_status: str, body: Review, conn, settings) -> dict:
    with conn.transaction():
        _proposed(conn, settings, correction_id)
        return repo.set_status(conn, settings, correction_id, new_status, review_note=body.review_note,
                               reviewed_by=body.reviewed_by)


@router.post("/block-corrections/{correction_id}/reject")
def reject(correction_id: UUID, body: Review, conn: Conn, settings: SettingsDep) -> dict:
    """반려. 블록은 바뀌지 않는다."""
    return _close(correction_id, "rejected", body, conn, settings)


@router.post("/block-corrections/{correction_id}/withdraw")
def withdraw(correction_id: UUID, body: Review, conn: Conn, settings: SettingsDep) -> dict:
    """철회(작성자가 취소). 블록은 바뀌지 않는다."""
    return _close(correction_id, "withdrawn", body, conn, settings)
