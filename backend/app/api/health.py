from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/db")
def health_db(request: Request) -> dict:
    """DB 연결과 설정된 두 스키마의 존재를 확인한다."""
    settings = request.app.state.settings
    with request.app.state.pool.connection(timeout=10) as conn:
        rows = conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)",
            ([settings.db_schema, settings.db_app_schema],),
        ).fetchall()
    found = {r[0] for r in rows}
    return {
        "status": "ok" if len(found) == 2 else "degraded",
        "schema": settings.db_schema in found,
        "app_schema": settings.db_app_schema in found,
        "judge_provider": settings.judge_provider,
    }
