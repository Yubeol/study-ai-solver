from collections.abc import Iterator

import psycopg
from fastapi import Request

from app.core.config import Settings
from app.storage.base import Storage


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.pool.connection(timeout=10) as conn:
        yield conn
