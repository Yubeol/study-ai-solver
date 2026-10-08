"""clean_text 해시: Python 함수와 005 SQL 백필이 같은 값을 내는지(D-JW-007). DB 테스트는 접속 불가면 건너뛴다."""

import hashlib

import pytest
from psycopg import errors, sql

from app.core.text_hash import SQL_EXPR, clean_text_hash, normalize_clean_text

SAMPLES = [
    "지니 지수는 1에서 각 범주 비율의 제곱합을 뺀 값이다.",
    "  앞뒤 공백\t\n",
    "\r\nCRLF 줄\r\n둘째 줄\r셋째 줄\r\n",
    "\t탭으로 시작\t",
    "",
    "  ",
    " 유니코드 공백(NBSP)은 지우지 않음　",
    "가나다 abc 123 ①② ×÷ √",
]


def test_normalize_rules():
    assert normalize_clean_text("\r\n a\r\nb\rc \t\n") == "a\nb\nc"
    assert normalize_clean_text(" x　") == " x　"  # 스페이스·탭·LF 외는 남긴다(SQL btrim과 맞춤)
    assert clean_text_hash("") == hashlib.sha256(b"").hexdigest()
    assert clean_text_hash("a\r\nb") == clean_text_hash(" a\nb\n")


def test_sql_expression_matches_python(db_conn):
    expr = sql.SQL(SQL_EXPR.format(col="%s"))
    for s in SAMPLES:
        got = db_conn.execute(sql.SQL("SELECT ") + expr, (s,)).fetchone()[0]
        assert got == clean_text_hash(s), repr(s)


def test_backfilled_blocks_match_python(db_conn, settings):
    """005 적용 후: 이론 블록의 source_clean_text_hash가 Python 값과 같다(아직 수정이 적용되지 않은 블록 기준)."""
    q = sql.SQL(
        "SELECT clean_text, source_clean_text_hash FROM {}.blocks "
        "WHERE block_type = 'theory' AND clean_text IS NOT NULL ORDER BY block_id LIMIT 20"
    ).format(sql.Identifier(settings.db_app_schema))
    try:
        rows = db_conn.execute(q).fetchall()
    except errors.UndefinedColumn:
        db_conn.rollback()
        pytest.skip("005 마이그레이션 적용 전")
    except errors.UndefinedTable:
        db_conn.rollback()
        pytest.skip("blocks 테이블 없음")
    if not rows:
        pytest.skip("이론 블록 없음")
    for clean_text, h in rows:
        assert h == clean_text_hash(clean_text)
