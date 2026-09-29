import psycopg
import pytest

from app.core.config import get_settings
from app.db.connection import connect


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
