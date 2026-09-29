"""DB 연결.

- 세션 단위 `SET search_path`는 쓰지 않는다(풀에서 다른 요청으로 새어 나간다).
- 스키마가 필요하면 `sql.Identifier(settings.db_schema)`로 명시하거나,
  `scoped_transaction()` 안에서 `SET LOCAL search_path`를 쓴다(트랜잭션 종료 시 원복).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool

from app.core.config import Settings


def conninfo(settings: Settings) -> str:
    return psycopg.conninfo.make_conninfo(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        connect_timeout=10,
        application_name="adsp-study-rag",
    )


def connect(settings: Settings) -> psycopg.Connection:
    """스크립트용 단일 연결(autocommit, 트랜잭션은 conn.transaction()으로 명시)."""
    return psycopg.connect(conninfo(settings), autocommit=True)


def create_pool(settings: Settings) -> ConnectionPool:
    return ConnectionPool(
        conninfo(settings),
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True},
        open=False,
    )


@contextmanager
def scoped_transaction(conn: psycopg.Connection, settings: Settings) -> Iterator[psycopg.Connection]:
    """트랜잭션 안에서만 search_path를 내 스키마로 고정한다.

    public은 pgvector/pg_trgm 확장 타입·연산자를 찾기 위해 마지막에만 둔다.
    """
    with conn.transaction():
        conn.execute(
            sql.SQL("SET LOCAL search_path TO {}, {}, public").format(
                sql.Identifier(settings.db_app_schema), sql.Identifier(settings.db_schema)
            )
        )
        yield conn
