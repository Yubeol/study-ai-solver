"""이론 블록 clean_text 해시(D-JW-007). 005 마이그레이션의 SQL 백필과 같은 규칙이어야 한다(테스트로 묶음).

정규화: CRLF·CR → LF 통일 → 앞뒤의 스페이스·탭·LF만 제거 → UTF-8 → sha256 hex.
Python str.strip()은 모든 유니코드 공백을, PostgreSQL btrim()은 기본으로 스페이스만 지워서
지울 문자를 " \\t\\n"으로 명시해 양쪽을 맞춘다.
"""

import hashlib

STRIP_CHARS = " \t\n"


def normalize_clean_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip(STRIP_CHARS)


def clean_text_hash(text: str) -> str:
    return hashlib.sha256(normalize_clean_text(text).encode("utf-8")).hexdigest()


# 005 마이그레이션 백필과 같은 식(테스트에서 DB 결과와 비교). $1 = clean_text
SQL_EXPR = (
    "encode(sha256(convert_to(btrim(replace(replace({col}, E'\\r\\n', E'\\n'), E'\\r', E'\\n'), E' \\t\\n'), "
    "'UTF8')), 'hex')"
)
