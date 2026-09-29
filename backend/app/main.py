"""FastAPI 앱 진입점.

실행: cd backend; uv run uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.db.connection import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = create_pool(settings)
    pool.open(wait=False)
    app.state.settings = settings
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="adsp-study-rag", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
