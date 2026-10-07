"""보충 이론 등록 API (D-J-004). 오류 신고 안의 첨부와 "확인 불가" 답변의 [이론 보충하기]가 같은 API를 쓴다.

- 프론트 이름도 받는다: 본문 `text`(= `content`), `kind` 생략 시 자동(파일이 PDF면 pdf, 그 밖의 파일은 image, 파일 없으면 text).
- 텍스트 / 이미지(PNG·JPEG·WEBP) / PDF를 받아 **검토 대기(pending_review)** 로만 저장한다. 임베딩하지 않는다.
- 텍스트는 DB에 본문을, 이미지·PDF는 저장소(`supplements/{id}.{확장자}`)에 원본을 두고 URI를 저장한다.
- 승인 → 추출·청킹·임베딩은 이 API 범위 밖이다(적재 코드 담당과 협의 후 별도 작업).
"""

from pathlib import PurePath
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
import pypdfium2 as pdfium
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import get_conn, get_settings, get_storage
from app.core.config import Settings
from app.ingestion.images import InvalidImage, inspect_image
from app.repositories import answer_reports as reports_repo
from app.repositories import supplements as supplements_repo
from app.storage.base import Storage

router = APIRouter(tags=["supplements"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[Storage, Depends(get_storage)]

SupplementStatus = Literal["pending_review", "approved", "rejected"]
_IMAGE_MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def pdf_page_count(data: bytes) -> int:
    """PDF 쪽 수. 열 수 없으면 ValueError."""
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise ValueError("PDF로 열 수 없음") from e
    try:
        return len(pdf)
    finally:
        pdf.close()


def _read_upload(file: UploadFile, settings: Settings) -> tuple[str, bytes]:
    name = PurePath(file.filename or "unnamed").name[:255]
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{name}: {settings.max_upload_mb}MB를 넘습니다.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name}: 빈 파일입니다.")
    return name, data


def infer_kind(content: str | None, filename: str | None, data: bytes) -> str:
    """kind를 생략했을 때: 파일이 있으면 PDF(시그니처·확장자) / 이미지, 없으면 텍스트."""
    if data:
        is_pdf = data[:5] == b"%PDF-" or (filename or "").lower().endswith(".pdf")
        return "pdf" if is_pdf else "image"
    if content is not None and content.strip():
        return "text"
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "보충할 이론 내용을 입력하거나 파일을 선택해 주세요.")


@router.post("/supplements", status_code=status.HTTP_201_CREATED)
def create_supplement(
    conn: Conn,
    settings: SettingsDep,
    storage: StorageDep,
    source: Annotated[Literal["report", "unanswerable"], Form(description="report: 오류 신고 안 / unanswerable: 확인 불가 버튼")],
    kind: Annotated[Literal["text", "image", "pdf"] | None, Form(description="생략하면 파일 유무·형식으로 정함")] = None,
    title: Annotated[str, Form(max_length=200)] = "",
    content: Annotated[str | None, Form(description="kind=text일 때 본문")] = None,
    text: Annotated[str | None, Form(description="content와 같음(프론트 이름)")] = None,
    file: Annotated[UploadFile | None, File(description="kind=image(PNG/JPEG/WEBP) 또는 pdf")] = None,
    subject: Annotated[str | None, Form(max_length=100)] = None,
    question: Annotated[str | None, Form(max_length=2000)] = None,
    report_id: Annotated[UUID | None, Form()] = None,
    query_log_id: Annotated[UUID | None, Form()] = None,
) -> dict:
    """보충 자료 1건을 검토 대기로 저장한다."""
    if report_id is not None and not reports_repo.report_exists(conn, settings, report_id):
        raise HTTPException(422, "report_id에 해당하는 오류 신고가 없습니다.")

    supplement_id = uuid4()
    content_text = file_uri = name = mime_type = None
    byte_size = page_count = None
    data = b""
    if file is not None:
        name, data = _read_upload(file, settings)
    kind = kind or infer_kind(content if content is not None else text, name, data)
    if kind == "text":
        content_text = (content if content is not None else text or "").strip()
        if not content_text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "보충할 이론 내용을 입력해 주세요.")
        if len(content_text) > settings.supplement_max_text_chars:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"내용은 {settings.supplement_max_text_chars}자 이하로 입력해 주세요.")
    else:
        if file is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일을 선택해 주세요.")
        if kind == "image":
            try:
                ext = inspect_image(data).extension
            except InvalidImage as e:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name}: {e}") from e
            mime_type = _IMAGE_MIME[ext]
        else:
            try:
                page_count = pdf_page_count(data)
            except ValueError as e:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name}: {e}") from e
            if page_count > settings.supplement_max_pdf_pages:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    f"{name}: {settings.supplement_max_pdf_pages}쪽 이하 PDF만 올릴 수 있습니다({page_count}쪽).")
            ext, mime_type = "pdf", "application/pdf"
        byte_size = len(data)
        file_uri = storage.save(f"supplements/{supplement_id}.{ext}", data)

    try:
        return supplements_repo.insert_supplement(
            conn, settings,
            supplement_id=supplement_id, report_id=report_id, query_log_id=query_log_id, source=source, kind=kind,
            title=title.strip(), subject=subject, question_text=question, content_text=content_text,
            file_uri=file_uri, original_filename=name, mime_type=mime_type, byte_size=byte_size, page_count=page_count,
        )
    except Exception as e:
        if file_uri is not None:
            storage.delete(file_uri)
        if isinstance(e, psycopg.errors.ForeignKeyViolation):
            raise HTTPException(422, "query_log_id에 해당하는 질문 기록이 없습니다.") from e
        raise


@router.get("/supplements")
def list_supplements(
    conn: Conn,
    settings: SettingsDep,
    status_: Annotated[SupplementStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(gt=0, le=200)] = 50,
) -> list[dict]:
    """보충 자료 목록(최신순). 검토 대기는 status=pending_review."""
    return supplements_repo.list_supplements(conn, settings, status=status_, limit=limit)
