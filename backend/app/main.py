"""FastAPI 앱 진입점.

실행: cd backend; uv run uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import books, health, runs
from app.core.config import get_settings
from app.db.connection import create_pool
from app.ingestion.pipeline import DEFAULT_STAGES
from app.storage import get_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = create_pool(settings)
    pool.open(wait=False)
    app.state.settings = settings
    app.state.pool = pool
    app.state.storage = get_storage(settings)
    # 테스트에서 가짜 단계로 바꿀 수 있게 앱 상태에 둔다.
    app.state.pipeline_stages = getattr(app.state, "pipeline_stages", DEFAULT_STAGES)
    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="adsp-study-rag", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(books.router)
    app.include_router(runs.router)
    return app


app = create_app()
