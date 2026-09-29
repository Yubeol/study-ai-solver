"""업로드 후 백그라운드 처리 파이프라인.

팀 규격 processing_status에는 "처리 중" 값이 없으므로 상태는 단계 묶음이 끝날 때만 바꾼다.
    extract_text                → EXTRACTED
    detect_visuals, chunk_theory → VERIFIED (품질 미달이면 REVIEW_REQUIRED 후 중단)
    embed                       → EMBEDDED
    예외                         → FAILED
    미구현 단계(StageNotImplemented) → 상태를 바꾸지 않고 멈춤(마지막으로 끝난 상태 유지)
현재 단계와 오류는 `page_metadata.pipeline`에 기록한다.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from psycopg_pool import ConnectionPool

from app.core.config import Settings
from app.ingestion import stages
from app.ingestion.stages import NeedsReview, PageContext, StageNotImplemented
from app.repositories import pages as pages_repo
from app.repositories import runs as runs_repo
from app.storage.base import Storage

log = logging.getLogger(__name__)

PIPELINE_VERSION = "0.2-ocr"
_ERROR_MAX_LEN = 500


@dataclass(frozen=True)
class Stage:
    name: str
    func: Callable[[PageContext], None]
    done_status: str | None = None  # 이 단계가 끝나면 설정할 processing_status


DEFAULT_STAGES: tuple[Stage, ...] = (
    Stage("extract_text", stages.extract_text, "EXTRACTED"),
    Stage("detect_visuals", stages.detect_visuals),
    Stage("chunk_theory", stages.chunk_theory, "VERIFIED"),
    Stage("embed", stages.embed, "EMBEDDED"),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def process_page(ctx: PageContext, stage_list: Sequence[Stage]) -> str:
    """한 페이지를 처리하고 최종 상태를 돌려준다. 예외를 밖으로 던지지 않는다."""
    conn, settings = ctx.conn, ctx.settings
    current = None
    try:
        for stage in stage_list:
            current = stage.name
            pages_repo.set_pipeline_info(conn, settings, ctx.page_id, {"stage": current, "updated_at": _now()})
            stage.func(ctx)
            if stage.done_status:
                pages_repo.set_status(
                    conn, settings, ctx.page_id, stage.done_status, {"stage": current, "updated_at": _now()}
                )
        return "DONE"
    except StageNotImplemented:
        info = {"stage": current, "stopped": "not_implemented", "updated_at": _now()}
        pages_repo.set_pipeline_info(conn, settings, ctx.page_id, info)
        return "INCOMPLETE"
    except NeedsReview as e:
        info = {"stage": current, "reason": str(e)[:_ERROR_MAX_LEN], "updated_at": _now()}
        pages_repo.set_status(conn, settings, ctx.page_id, "REVIEW_REQUIRED", info)
        return "REVIEW_REQUIRED"
    except Exception as e:
        log.exception("페이지 처리 실패 page_id=%s stage=%s", ctx.page_id, current)
        info = {"stage": current, "error": f"{type(e).__name__}: {e}"[:_ERROR_MAX_LEN], "updated_at": _now()}
        try:
            pages_repo.set_status(conn, settings, ctx.page_id, "FAILED", info)
        except Exception:
            log.exception("FAILED 상태 기록 실패 page_id=%s", ctx.page_id)
        return "FAILED"


def run_pipeline(
    pool: ConnectionPool,
    settings: Settings,
    storage: Storage,
    run_id: UUID,
    page_ids: Sequence[UUID],
    stage_list: Sequence[Stage] = DEFAULT_STAGES,
) -> None:
    """실행 1건의 페이지들을 순서대로 처리하고 processing_runs에 집계를 기록한다."""
    counts = {"DONE": 0, "INCOMPLETE": 0, "REVIEW_REQUIRED": 0, "FAILED": 0}
    for page_id in page_ids:
        try:
            with pool.connection() as conn:
                page = pages_repo.get_page(conn, settings, page_id)
                if page is None:  # 처리 전에 삭제됨
                    counts["FAILED"] += 1
                    continue
                ctx = PageContext(
                    page_id=page_id,
                    book_id=page["book_id"],
                    run_id=run_id,
                    source_uri=page["source_s3_uri"],
                    conn=conn,
                    settings=settings,
                    storage=storage,
                )
                counts[process_page(ctx, stage_list)] += 1
        except Exception:
            log.exception("페이지 처리 준비 실패 page_id=%s", page_id)
            counts["FAILED"] += 1

    try:
        with pool.connection() as conn:
            status = runs_repo.finish_run(
                conn,
                settings,
                run_id,
                success=counts["DONE"],
                review=counts["REVIEW_REQUIRED"],
                failure=counts["FAILED"],
                incomplete=counts["INCOMPLETE"],
            )
        log.info("처리 완료 run_id=%s status=%s counts=%s", run_id, status, counts)
    except Exception:
        log.exception("실행 집계 기록 실패 run_id=%s", run_id)
