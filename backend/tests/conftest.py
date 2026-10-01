import os

import psycopg
import pytest

# 테스트에서는 서버 시작 시 실제 모델(임베딩·리랭커)을 로드하지 않는다. 질의 테스트는 가짜 모델을 app.state에 넣는다.
os.environ["PRELOAD_MODELS"] = "false"

from app.core.config import get_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def db_conn(settings):
    """공유 DB 연결. 접속할 수 없으면 DB 테스트는 건너뛴다."""
    try:
        conn = connect(settings)
    except psycopg.OperationalError as e:
        pytest.skip(f"DB 접속 불가: {type(e).__name__}")
    yield conn
    conn.close()
