"""질의 API (ARCHITECTURE "질의 흐름"). 모델은 서버 시작 시 미리 로드되어 app.state.qa_models에 있다."""

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_conn, get_settings
from app.core.config import Settings
from app.qa.service import answer_question
from app.visuals.common_json import visuals_for

router = APIRouter(tags=["qa"])


class QaRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int | None = Field(default=None, gt=0, le=20, description="근거 개수(기본 SEARCH_TOP_K)")


@router.post("/qa")
def ask(
    body: QaRequest,
    request: Request,
    conn: psycopg.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> dict:
    """질문 → 검색 → "확인 불가" 3구간 → 답변(근거 번호 인용) → query_logs 기록.

    status: answered / unanswerable / error. low_confidence가 true면 "근거 확신 낮음" 표시.
    citations는 답변이 인용한 근거(raw_text = 교재 원문), evidence는 넘긴 근거 전체.
    visuals는 인용된 근거와 연결된 표·시각자료(공통 JSON, D-J-005). 없으면 빈 목록.
    """
    models = getattr(request.app.state, "qa_models", None)
    if models is None:
        raise HTTPException(503, "질의 모델이 로드되지 않았습니다(PRELOAD_MODELS=false).")
    result = answer_question(conn, settings, models, body.question.strip(), body.k)
    result["visuals"] = visuals_for(settings, result.get("evidence") or []) if settings.visuals_max else []
    return result
