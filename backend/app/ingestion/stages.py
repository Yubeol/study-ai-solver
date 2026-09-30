"""처리 단계 함수. 하나씩 구현하고, 아직 없는 단계는 `StageNotImplemented`를 던진다.

각 단계는 `PageContext`를 받는다. 품질 미달이면 `NeedsReview`를 던지고,
그 밖의 예외는 페이지 실패(FAILED)로 처리된다.
"""

import json
from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.core.config import Settings
from app.ingestion import ocr
from app.ingestion.images import decode_bgr
from app.repositories import books as books_repo
from app.repositories import pages as pages_repo
from app.storage.base import Storage


class NeedsReview(Exception):
    """품질 기준 미달. 페이지를 REVIEW_REQUIRED로 두고 이후 단계를 건너뛴다."""


class StageNotImplemented(Exception):
    """아직 구현하지 않은 단계. 페이지는 마지막으로 끝난 상태에 머문다."""


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


def ocr_key(book_id: UUID, page_id: UUID) -> str:
    return f"books/{book_id}/{page_id}.ocr.json"


def text_key(book_id: UUID, page_id: UUID) -> str:
    """OCR 대신 외부 텍스트(팀 텍스트 등)를 추출 결과로 쓸 때의 저장 키(D-014)."""
    return f"books/{book_id}/{page_id}.text.json"


def extract_text(ctx: PageContext) -> None:
    """텍스트 추출. 인쇄체(textbook/lecture_note) → PaddleOCR, 손필기 → 비전 LLM(미구현) (D-008).

    줄 단위 전체 결과는 저장소 JSON에, page_metadata.ocr에는 요약만 둔다.
    """
    material_type = books_repo.get_material_type(ctx.conn, ctx.settings, ctx.book_id)
    if material_type == "personal_note":
        raise NeedsReview("손필기 추출 미구현")

    image = decode_bgr(ctx.read_source())
    result = ocr.get_engine(ctx.settings).recognize(image)

    data = json.dumps(result.to_json(), ensure_ascii=False).encode("utf-8")
    uri = ctx.storage.save(ocr_key(ctx.book_id, ctx.page_id), data)
    summary = {
        "uri": uri,
        "line_count": len(result.lines),
        "mean_confidence": result.mean_confidence,
        **result.engine,
    }
    pages_repo.merge_metadata(ctx.conn, ctx.settings, ctx.page_id, {"ocr": summary})


def detect_visuals(ctx: PageContext) -> None:
    """TODO: 기울기 보정, 시각자료 crop, 세트 그림 묶기, 표 구조화."""
    raise StageNotImplemented("detect_visuals")


def chunk_theory(ctx: PageContext) -> None:
    """TODO: 이론 청킹(sort_order), 수식 구조화, 제외 영역 분리, 품질 판정."""
    raise StageNotImplemented("chunk_theory")


def embed(ctx: PageContext) -> None:
    """TODO: 시각자료 설명문 생성 + BGE-M3 임베딩 저장, 링크 테이블 채우기."""
    raise StageNotImplemented("embed")
