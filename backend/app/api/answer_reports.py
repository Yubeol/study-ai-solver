"""답변 오류 신고 API (D-JW-004). 요청 값은 프론트 오류 신고 화면(ReportDrawer)에 맞춘다.

근거 스냅샷: query_logs에는 근거가 청크 id·쪽·점수로만 남으므로(metadata.evidence), 신고하는 순간
청크를 조회해 책 제목·제목 경로·원문까지 신고 행에 복사한다. 재적재로 청크가 없어졌으면 화면이 보낸
근거(/qa 응답의 evidence)로 채운다.
"""

from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AliasChoices, BaseModel, Field

from app.api.deps import get_conn, get_settings
from app.core.config import Settings
from app.qa.service import heading_path
from app.repositories import answer_reports as reports_repo

router = APIRouter(tags=["answer-reports"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

ReportType = Literal[
    "wrong_answer", "wrong_explanation", "wrong_concept", "missing_concept", "wrong_ocr", "insufficient", "other"
]
ReportStatus = Literal["open", "resolved"]
# 처리 결과(005, D-JW-007). source_fix_requested = 표·시각자료 오류를 데이터 담당 JSON 수정 요청으로 닫음
Resolution = Literal["block_corrected", "supplement_added", "source_fix_requested", "prompt_issue",
                     "retrieval_issue", "not_an_error", "duplicate", "other"]


class EvidenceIn(BaseModel):
    """화면이 가진 근거(/qa 응답 evidence 항목). 스냅샷 대체용이라 모두 선택값."""

    n: int | None = None
    chunk_id: str | None = None
    book_title: str | None = None
    page: str | int | None = None
    path: str | None = None
    raw_text: str | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    cited: bool | None = None
    # 검색 대상 전환(D-M-033)에서 추가. corpus가 common_json이면 chunk_id는 blocks.id
    corpus: str | None = None
    kind: str | None = None
    block_id: str | None = None


class ReportCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # 프론트(ReportDrawer)는 report_type으로 보낸다. 둘 다 받는다(D-JW-004).
    type: ReportType = Field(validation_alias=AliasChoices("type", "report_type"))
    concept_details: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default=[], max_length=10)
    detail: str = Field(default="", max_length=500)
    query_log_id: UUID | None = Field(default=None, description="/qa 응답의 query_log_id(있으면 답·근거를 기록에서 가져옴)")
    answer: str | None = Field(default=None, max_length=10000, description="query_log_id가 없을 때만 사용")
    evidence: list[EvidenceIn] = Field(default=[], max_length=20)


class ReportUpdate(BaseModel):
    """빠진 값은 그대로 둔다. resolved로 바꿀 때는 resolution이 필요하다(이미 있으면 생략 가능)."""

    status: ReportStatus | None = None
    resolution: Resolution | None = None
    resolution_note: str | None = Field(default=None, max_length=500)
    linked_block_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(default=None, max_length=20)
    reviewed_by: str | None = Field(default=None, max_length=100)


_SNAPSHOT_KEYS = ("n", "chunk_id", "book_title", "page", "path", "raw_text", "vector_score", "rerank_score", "cited",
                  "corpus", "kind", "block_id")


def build_snapshot(logged: list[dict], chunks: dict[str, dict], client: list[dict]) -> list[dict]:
    """근거 스냅샷 목록.

    - logged: query_logs.metadata.evidence(n, chunk_id, page, 점수, cited). 비어 있으면 화면 값만 쓴다.
    - chunks: 청크 id → 현재 DB의 청크 정보(get_chunks) 또는 블록 정보(get_blocks, path 포함).
      있으면 책 제목·경로·원문을 여기서 채운다.
    - client: 화면이 보낸 근거. 청크가 없어졌을 때(재적재) 대신 쓴다.
    각 항목의 `source`: db(청크 조회) / client(화면 값) / missing(둘 다 없음, 원문 없음).
    """
    by_n = {c.get("n"): c for c in client if c.get("n") is not None}
    by_id = {str(c.get("chunk_id")): c for c in client if c.get("chunk_id")}
    if not logged:
        return [{k: c.get(k) for k in _SNAPSHOT_KEYS} | {"source": "client"} for c in client]
    out = []
    for e in logged:
        item = {k: e.get(k) for k in _SNAPSHOT_KEYS}
        row = chunks.get(str(e.get("chunk_id")))
        fallback = by_id.get(str(e.get("chunk_id"))) or by_n.get(e.get("n"))
        if row is not None:
            item |= {"book_title": row["book_title"], "path": row.get("path") or heading_path(row),
                     "raw_text": row["raw_text"],
                     "page": e.get("page") if e.get("page") is not None else row["printed_page_number"],
                     "source": "db"}
        elif fallback is not None:
            item |= {k: fallback.get(k) for k in ("book_title", "path", "raw_text")} | {"source": "client"}
        else:
            item["source"] = "missing"
        out.append(item)
    return out


@router.post("/answer-reports", status_code=status.HTTP_201_CREATED)
def create_report(body: ReportCreate, conn: Conn, settings: SettingsDep) -> dict:
    """오류 신고 1건 저장. query_log_id가 있으면 질문·답·근거를 그 기록에서 스냅샷으로 남긴다."""
    client = [e.model_dump() for e in body.evidence]
    question, answer, logged = body.question.strip(), body.answer, []
    if body.query_log_id is not None:
        log = reports_repo.get_query_log(conn, settings, body.query_log_id)
        if log is None:
            raise HTTPException(422, "query_log_id에 해당하는 질문 기록이 없습니다.")
        question = log["question_text"] or question
        answer = log["answer"]
        logged = [e for e in log["evidence"] if isinstance(e, dict)]
    # 근거 조회: 블록 근거(block_id 있음, chunk_id = blocks.id)는 blocks에서, 나머지는 theory_chunks에서(D-M-033)
    chunks = reports_repo.get_chunks(
        conn, settings, [str(e.get("chunk_id")) for e in logged if not e.get("block_id")]) if logged else {}
    if block_ids := [str(e.get("chunk_id")) for e in logged if e.get("block_id")]:
        chunks |= reports_repo.get_blocks(conn, settings, block_ids)
    return reports_repo.insert_report(
        conn,
        settings,
        query_log_id=body.query_log_id,
        question_text=question,
        answer_text=answer,
        report_type=body.type,
        concept_details=body.concept_details,
        detail=body.detail.strip(),
        evidence_snapshot=build_snapshot(logged, chunks, client),
    )


@router.get("/answer-reports")
def list_reports(
    conn: Conn,
    settings: SettingsDep,
    status_: Annotated[ReportStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(gt=0, le=200)] = 50,
) -> list[dict]:
    """오류 신고 목록(최신순)."""
    return reports_repo.list_reports(conn, settings, status=status_, limit=limit)


@router.patch("/answer-reports/{report_id}")
def update_report(report_id: UUID, body: ReportUpdate, conn: Conn, settings: SettingsDep) -> dict:
    """신고 처리: 상태(open ↔ resolved)·처리 결과·메모·연결 블록·검토자. resolved면 resolution 필수."""
    if not body.model_fields_set:
        raise HTTPException(422, "바꿀 값이 없습니다.")
    try:
        row = reports_repo.update_review(
            conn, settings, report_id, status=body.status, resolution=body.resolution,
            resolution_note=body.resolution_note.strip() if body.resolution_note is not None else None,
            linked_block_ids=body.linked_block_ids, reviewed_by=body.reviewed_by)
    except psycopg.errors.CheckViolation as e:
        raise HTTPException(422, "resolved로 바꾸려면 resolution(처리 결과)이 필요합니다.") from e
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "신고를 찾을 수 없습니다.")
    return row
