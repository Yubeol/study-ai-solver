"""번호 붙은 SQL 마이그레이션 실행기.

사용법:
    uv run python -m app.db.migrate --dry-run   # 치환된 SQL만 출력 (DB 변경 없음)
    uv run python -m app.db.migrate             # 미적용 파일을 순서대로 적용

- 파일 안의 {{schema}}, {{app_schema}} 를 설정값 DB_SCHEMA, DB_APP_SCHEMA 로 치환한다.
- 파일 하나를 트랜잭션 하나로 적용한다.
- 적용 이력은 {{app_schema}}.schema_migrations 에 남긴다(002에서 생성).
"""

import argparse
import hashlib
from pathlib import Path

import psycopg
from psycopg import sql

from app.core.config import ROOT_DIR, Settings, get_settings
from app.db.connection import connect

MIGRATIONS_DIR = ROOT_DIR / "backend" / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))


def render(path: Path, settings: Settings) -> str:
    text = path.read_text(encoding="utf-8")
    return text.replace("{{schema}}", settings.db_schema).replace(
        "{{app_schema}}", settings.db_app_schema
    )


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _applied(conn: psycopg.Connection, settings: Settings) -> dict[str, str]:
    table = f"{settings.db_app_schema}.schema_migrations"
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (table,))
        if cur.fetchone()[0] is None:
            return {}
        cur.execute(
            sql.SQL("SELECT filename, checksum FROM {}.schema_migrations").format(
                sql.Identifier(settings.db_app_schema)
            )
        )
        return dict(cur.fetchall())


def _record(conn: psycopg.Connection, settings: Settings, paths: list[Path]) -> None:
    with conn.cursor() as cur:
        for p in paths:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.schema_migrations (filename, checksum) VALUES (%s, %s) "
                    "ON CONFLICT (filename) DO NOTHING"
                ).format(sql.Identifier(settings.db_app_schema)),
                (p.name, checksum(p)),
            )


def migrate(settings: Settings, dry_run: bool = False) -> list[str]:
    files = migration_files()
    if dry_run:
        for p in files:
            print(f"-- ===== {p.name} =====")
            print(render(p, settings))
        return []

    applied_now: list[str] = []
    with connect(settings) as conn:
        applied = _applied(conn, settings)
        for p in files:
            if p.name in applied:
                if applied[p.name] != checksum(p):
                    raise RuntimeError(f"적용된 마이그레이션이 변경됨: {p.name}")
                continue
            with conn.transaction():
                conn.execute(render(p, settings))
            applied_now.append(p.name)
            print(f"적용: {p.name}")
        # 이력 테이블은 002에서 생기므로, 이번에 적용한 파일을 마지막에 한 번에 기록한다.
        if applied_now:
            with conn.transaction():
                _record(conn, settings, [p for p in files if p.name in applied_now])
    return applied_now


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    done = migrate(get_settings(), dry_run=args.dry_run)
    if not args.dry_run:
        print("완료" if done else "적용할 마이그레이션 없음")


if __name__ == "__main__":
    main()
