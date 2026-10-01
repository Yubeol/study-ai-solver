"""FastAPI 앱 진입점.

실행: cd backend; uv run uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import books, health, qa, runs
from app.core.config import get_settings
from app.db.connection import create_pool
from app.ingestion.pipeline import DEFAULT_STAGES
from app.qa.service import load_qa_models
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
    # 질의 모델(임베딩·리랭커)은 시작 시 미리 로드한다(약 40초, RAM 약 4.7GB). 테스트는 가짜를 넣거나 끈다.
    if getattr(app.state, "qa_models", None) is None and settings.preload_models:
        app.state.qa_models = load_qa_models(settings)
    try:
        yield
    finally:
        qa_models = getattr(app.state, "qa_models", None)
        if qa_models is not None and qa_models.llm is not None:
            qa_models.llm.close()
        if qa_models is not None and qa_models.judge is not None:
            qa_models.judge.close()
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="adsp-study-rag", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(books.router)
    app.include_router(runs.router)
    app.include_router(qa.router)
    return app


app = create_app()
