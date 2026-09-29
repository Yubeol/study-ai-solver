"""처리 단계 함수. 지금은 모두 빈 함수이고, 다음 세션부터 하나씩 구현한다.

각 단계는 `PageContext`를 받는다. 품질 미달이면 `NeedsReview`를 던지고,
그 밖의 예외는 페이지 실패(FAILED)로 처리된다.
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.core.config import Settings
from app.storage.base import Storage


class NeedsReview(Exception):
    """품질 기준 미달. 페이지를 REVIEW_REQUIRED로 두고 이후 단계를 건너뛴다."""


@dataclass
class PageContext:
    page_id: UUID
    book_id: UUID
    run_id: UUID
    source_uri: str
    conn: psycopg.Connection
    settings: Settings
    storage: Storage

    def read_source(self) -> bytes:
        return self.storage.read(self.source_uri)


def extract_text(ctx: PageContext) -> None:
    """TODO: 텍스트 추출. 인쇄체 → PaddleOCR, 손필기 → 비전 LLM (D-008)."""


def detect_visuals(ctx: PageContext) -> None:
    """TODO: 기울기 보정, 시각자료 crop, 세트 그림 묶기, 표 구조화."""


def chunk_theory(ctx: PageContext) -> None:
    """TODO: 이론 청킹(sort_order), 수식 구조화, 제외 영역 분리, 품질 판정."""


def embed(ctx: PageContext) -> None:
    """TODO: 시각자료 설명문 생성 + BGE-M3 임베딩 저장, 링크 테이블 채우기."""
