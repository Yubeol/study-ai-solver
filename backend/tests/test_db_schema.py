"""DB 연결과 스키마 고정 확인 (공유 DB 필요, 읽기만 한다)."""

from psycopg import sql

from app.db.connection import create_pool, scoped_transaction
from app.db.migrate import checksum, migration_files


def test_configured_schemas_exist(db_conn, settings):
    rows = db_conn.execute(
        "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)",
        ([settings.db_schema, settings.db_app_schema],),
    ).fetchall()
    assert {r[0] for r in rows} == {settings.db_schema, settings.db_app_schema}


def test_scoped_transaction_pins_schema_and_reverts(db_conn, settings):
    before = db_conn.execute("SHOW search_path").fetchone()[0]
    with scoped_transaction(db_conn, settings) as conn:
        inside = conn.execute("SHOW search_path").fetchone()[0]
        # 스키마 없이 쓴 테이블 이름이 내 스키마로 해석되는지
        resolved = conn.execute(
            "SELECT n.nspname || '.' || c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.oid = 'books'::regclass"
        ).fetchone()[0]
    after = db_conn.execute("SHOW search_path").fetchone()[0]

    assert inside.split(", ")[:2] == [settings.db_app_schema, settings.db_schema]
    assert resolved == f"{settings.db_schema}.books"
    assert after == before  # SET LOCAL은 트랜잭션 밖으로 새지 않는다


def test_pool_connection_does_not_leak_search_path(settings):
    pool = create_pool(settings)
    pool.open(wait=True, timeout=15)
    try:
        with pool.connection() as conn:
            default = conn.execute("SHOW search_path").fetchone()[0]
            with scoped_transaction(conn, settings):
                pass
        with pool.connection() as conn:
            assert conn.execute("SHOW search_path").fetchone()[0] == default
    finally:
        pool.close()


def test_all_migrations_applied(db_conn, settings):
    rows = db_conn.execute(
        sql.SQL("SELECT filename, checksum FROM {}.schema_migrations").format(
            sql.Identifier(settings.db_app_schema)
        )
    ).fetchall()
    applied = dict(rows)
    for p in migration_files():
        assert applied.get(p.name) == checksum(p), p.name


def test_supplement_columns_exist(db_conn, settings):
    rows = db_conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = %s",
        (settings.db_schema,),
    ).fetchall()
    cols = set(rows)
    for expected in [
        ("books", "subject"),
        ("books", "material_type"),
        ("theory_chunks", "sort_order"),
        ("theory_chunks", "processing_run_id"),
        ("visual_assets", "processing_run_id"),
    ]:
        assert expected in cols


def test_app_tables_exist(db_conn, settings):
    rows = db_conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
        (settings.db_app_schema,),
    ).fetchall()
    assert {r[0] for r in rows} >= {
        "problems",
        "problem_extractions",
        "solutions",
        "solution_evidence",
        "judgments",
        "schema_migrations",
    }
