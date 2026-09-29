"""처리 상태 조회."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.books import Conn, SettingsDep, _public_page
from app.repositories import pages as pages_repo
from app.repositories import runs as runs_repo

router = APIRouter(tags=["processing"])


@router.get("/processing-runs/{run_id}")
def get_run(run_id: UUID, conn: Conn, settings: SettingsDep) -> dict:
    run = runs_repo.get_run(conn, settings, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "처리 기록을 찾을 수 없습니다.")
    pages = [_public_page(p) for p in pages_repo.list_pages_by_run(conn, settings, run_id)]
    return run | {"pages": pages}
