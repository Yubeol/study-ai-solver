"""과목·자료(books) 생성/조회, 페이지 이미지 다중 업로드."""

from pathlib import PurePath
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import get_conn, get_settings, get_storage
from app.core.config import Settings
from app.ingestion.images import InvalidImage, inspect_image
from app.ingestion.pipeline import PIPELINE_VERSION, run_pipeline
from app.repositories import books as books_repo
from app.repositories import pages as pages_repo
from app.repositories import runs as runs_repo
from app.storage.base import Storage

router = APIRouter(tags=["books"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[Storage, Depends(get_storage)]


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    material_type: Literal["textbook", "lecture_note", "personal_note"]
    edition: str | None = Field(default=None, max_length=100)
    source_name: str | None = Field(default=None, max_length=200)


@router.get("/subjects")
def list_subjects(conn: Conn, settings: SettingsDep) -> list[str]:
    return books_repo.list_subjects(conn, settings)


@router.post("/books", status_code=status.HTTP_201_CREATED)
def create_book(body: BookCreate, conn: Conn, settings: SettingsDep) -> dict:
    data = body.model_dump()
    data["title"] = data["title"].strip()
    data["subject"] = data["subject"].strip()
    if not data["title"] or not data["subject"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "title/subject는 공백일 수 없습니다.")
    book = books_repo.create_book(conn, settings, **data)
    return book | {"page_count": 0, "status_counts": {}}


@router.get("/books")
def list_books(conn: Conn, settings: SettingsDep, subject: Annotated[str | None, Query()] = None) -> list[dict]:
    return books_repo.list_books(conn, settings, subject)


def _require_book(conn: psycopg.Connection, settings: Settings, book_id: UUID) -> dict:
    book = books_repo.get_book(conn, settings, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "자료를 찾을 수 없습니다.")
    return book


@router.get("/books/{book_id}")
def get_book(book_id: UUID, conn: Conn, settings: SettingsDep) -> dict:
    return _require_book(conn, settings, book_id)


@router.get("/books/{book_id}/pages")
def list_book_pages(book_id: UUID, conn: Conn, settings: SettingsDep) -> list[dict]:
    _require_book(conn, settings, book_id)
    return [_public_page(p) for p in pages_repo.list_pages_by_book(conn, settings, book_id)]


def _public_page(page: dict) -> dict:
    # 저장소 URI는 내부 정보이므로 응답에서 뺀다.
    return {k: v for k, v in page.items() if k != "source_s3_uri"}


@router.post("/books/{book_id}/pages", status_code=status.HTTP_202_ACCEPTED)
def upload_pages(
    book_id: UUID,
    files: Annotated[list[UploadFile], File(description="페이지 이미지(PNG/JPEG/WEBP), 업로드 순서가 페이지 순서")],
    background: BackgroundTasks,
    request: Request,
    conn: Conn,
    settings: SettingsDep,
    storage: StorageDep,
) -> dict:
    """이미지를 검증·저장하고 pages 행을 만든 뒤 백그라운드 처리를 시작한다.

    한 장이라도 검증에 실패하면 아무것도 저장하지 않는다.
    """
    _require_book(conn, settings, book_id)
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일이 없습니다.")

    # 1) 전부 검증
    max_bytes = settings.max_upload_mb * 1024 * 1024
    checked = []
    for f in files:
        name = PurePath(f.filename or "unnamed").name[:255]
        data = f.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, f"{name}: {settings.max_upload_mb}MB를 넘습니다."
            )
        try:
            info = inspect_image(data)
        except InvalidImage as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name}: {e}") from e
        checked.append((name, data, info))

    # 2) 저장소에 저장 → 3) DB 기록. DB 기록이 실패하면 저장한 파일을 지운다.
    start = pages_repo.next_upload_index(conn, settings, book_id)
    new_pages: list[pages_repo.NewPage] = []
    try:
        for i, (name, data, info) in enumerate(checked):
            page_id = uuid4()
            uri = storage.save(f"books/{book_id}/{page_id}.{info.extension}", data)
            new_pages.append(
                pages_repo.NewPage(
                    id=page_id,
                    source_uri=uri,
                    width=info.width,
                    height=info.height,
                    upload_index=start + i,
                    original_filename=name,
                )
            )
        with conn.transaction():
            run_id = runs_repo.create_run(
                conn, settings, pipeline_version=PIPELINE_VERSION, page_count=len(new_pages)
            )
            pages_repo.insert_pages(conn, settings, book_id, run_id, new_pages)
    except Exception:
        for p in new_pages:
            try:
                storage.delete(p.source_uri)
            except Exception:
                pass
        raise

    background.add_task(
        run_pipeline,
        request.app.state.pool,
        settings,
        storage,
        run_id,
        [p.id for p in new_pages],
        request.app.state.pipeline_stages,
    )
    return {
        "run_id": run_id,
        "book_id": book_id,
        "pages": [
            {"id": p.id, "upload_index": p.upload_index, "original_filename": p.original_filename}
            for p in new_pages
        ],
    }
