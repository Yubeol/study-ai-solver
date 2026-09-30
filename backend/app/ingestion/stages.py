"""처리 단계 함수. 하나씩 구현하고, 아직 없는 단계는 `StageNotImplemented`를 던진다.

각 단계는 `PageContext`를 받는다. 품질 미달이면 `NeedsReview`를 던지고,
그 밖의 예외는 페이지 실패(FAILED)로 처리된다.
"""

import json
from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.core.config import Settings
from app.ingestion import chunking, embedding, ocr
from app.ingestion.images import decode_bgr
from app.repositories import books as books_repo
from app.repositories import pages as pages_repo
from app.repositories import theory_chunks as chunks_repo
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


def chunk_params(settings: Settings) -> chunking.ChunkParams:
    return chunking.ChunkParams(
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
        min_chars=settings.chunk_min_chars,
        heading_max_chars=settings.chunk_heading_max_chars,
        review_max_chars=settings.chunk_review_max_chars,
        review_min_hangul_ratio=settings.chunk_review_min_hangul_ratio,
    )


def read_page_lines(
    storage: Storage, text_meta: dict | None, ocr_meta: dict | None
) -> tuple[list[str], str, str]:
    """추출 결과를 (줄 목록, 출처, uri)로 읽는다. 팀 텍스트(.text.json의 text)가 있으면 그것을, 없으면 OCR 줄."""
    if text_meta and text_meta.get("uri"):
        data = json.loads(storage.read(text_meta["uri"]).decode("utf-8"))
        return data["text"].splitlines(), "team_text", text_meta["uri"]
    if ocr_meta and ocr_meta.get("uri"):
        data = json.loads(storage.read(ocr_meta["uri"]).decode("utf-8"))
        return [line["text"] for line in data["lines"]], "ocr", ocr_meta["uri"]
    raise ValueError("추출 결과 없음(page_metadata.text / .ocr)")


def chunking_metadata(result: chunking.PageChunks, source: str, prev_state: str) -> dict:
    """page_metadata.chunking에 남길 요약. end_state는 다음 페이지가 제목 경로를 이어받는 데 쓴다."""
    return {
        "source": source,
        "chunk_count": len(result.chunks),
        "needs_review_count": sum(1 for c in result.chunks if c.needs_review),
        "excluded": [
            {"type": e.section_type, "title": e.title, "line_range": e.line_range, "continued": e.continued}
            for e in result.excluded
        ],
        "dropped_lines": result.dropped_lines,
        "prev_state": prev_state,  # previous / none(첫 페이지) / missing(앞 페이지 미청킹)
        "end_state": result.end_state.to_json(),
    }


def chunk_theory(ctx: PageContext) -> None:
    """이론 청킹(D-019). 제목 경로는 앞 페이지의 page_metadata.chunking.end_state에서 이어받는다.

    페이지 단위 트랜잭션으로 기존 청크를 지우고 다시 넣는다(재실행 안전).
    """
    row = pages_repo.get_chunk_input(ctx.conn, ctx.settings, ctx.page_id)
    lines, source, uri = read_page_lines(ctx.storage, row["text"], row["ocr"])
    has_prev, prev = pages_repo.get_previous_chunk_state(ctx.conn, ctx.settings, row["book_id"], row["upload_index"])
    prev_state = "previous" if prev is not None else ("missing" if has_prev else "none")

    result = chunking.chunk_page(
        lines, row["printed_page_number"], chunking.ChunkState.from_json(prev), chunk_params(ctx.settings)
    )
    chunks_repo.replace_page_chunks(
        ctx.conn,
        ctx.settings,
        ctx.page_id,
        ctx.run_id,
        result.chunks,
        result.excluded,
        chunking_metadata(result, source, prev_state),
        uri,
    )


def embed(ctx: PageContext) -> None:
    """이론 청크 BGE-M3 임베딩(정규화) 저장 (D-020). 입력은 embedding_text.

    TODO: 시각자료 설명문 생성·임베딩, 링크 테이블 채우기(시각자료 단계 구현 후).
    """
    rows = chunks_repo.list_for_embedding(ctx.conn, ctx.settings, ctx.page_id)
    if not rows:
        return
    vecs = embedding.get_embedder(ctx.settings).encode([text for _, text in rows])
    chunks_repo.save_embeddings(
        ctx.conn, ctx.settings, [(cid, embedding.to_pgvector(v)) for (cid, _), v in zip(rows, vecs, strict=True)]
    )
