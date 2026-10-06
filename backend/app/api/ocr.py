"""문제 사진 → 문제 텍스트 API (프론트 QuestionForm의 "추출된 문제" 칸 채우기, D-J-001~003).

엔진은 PROBLEM_OCR_ENGINE으로 고른다.
- google_vision(기본): Google Cloud Vision DOCUMENT_TEXT_DETECTION으로 사진 전체 글자를 읽는다(D-J-003).
  문제 하나만 골라내지는 않으므로 사용자가 입력칸에서 다른 문제 글자를 지운다.
- gemini: Gemini 비전(구조화 출력)으로 사진에서 문제 1개와 선택지만 옮겨 적는다. 기울어지거나 휜 사진,
  위아래에 걸린 다른 문제, 비친 뒷장 글자를 걸러낸다. 모델은 PROBLEM_EXTRACT_MODEL, 프롬프트는 prompts/problem_extract_*.
- 대체: 고른 엔진의 키가 없거나 호출이 실패하면 업로드 경로의 인쇄체 PaddleOCR로 읽는다(응답 fallback_reason).
- 사진은 저장하지 않는다. 결과 텍스트는 사용자가 화면에서 고친 뒤 `/qa`로 보낸다.
"""

from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.api.deps import get_settings
from app.core.config import Settings
from app.ingestion import ocr
from app.ingestion.images import InvalidImage, decode_bgr, inspect_image
from app.ingestion.ocr import OcrLine
from app.llm.gemini import GeminiClient, GeminiError
from app.prompts import load_json, load_text
from app.vision.google_vision import GoogleVisionClient, VisionError

router = APIRouter(tags=["ocr"])

SettingsDep = Annotated[Settings, Depends(get_settings)]

_MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def lines_to_text(lines: list[OcrLine]) -> str:
    """OCR 줄을 읽는 순서(위→아래, 같은 높이면 왼→오른)로 이어 붙인다.

    세로 중심이 앞 줄 높이의 절반 안이면 같은 줄로 보고 공백으로, 다른 줄은 줄바꿈으로 잇는다.
    """
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda ln: (ln.bbox[1] + ln.bbox[3]) / 2):
        center = (line.bbox[1] + line.bbox[3]) / 2
        if rows:
            last = rows[-1][-1]
            last_center = (last.bbox[1] + last.bbox[3]) / 2
            if abs(center - last_center) <= (last.bbox[3] - last.bbox[1]) / 2:
                rows[-1].append(line)
                continue
        rows.append([line])
    texts = [" ".join(ln.text.strip() for ln in sorted(row, key=lambda ln: ln.bbox[0]) if ln.text.strip()) for row in rows]
    return "\n".join(t for t in texts if t)


def compose_problem(problem_text: str, choices: list[str], figure_description: str) -> str:
    """질문 입력칸에 넣을 문자열: 문제 → [그림·표 설명] → ①② 선택지(한 줄에 하나)."""
    parts = [problem_text.strip()]
    if figure_description.strip():
        parts.append(f"[그림·표] {figure_description.strip()}")
    for i, choice in enumerate(c.strip() for c in choices):
        if choice:
            mark = _CIRCLED[i] if i < len(_CIRCLED) else f"({i + 1})"
            parts.append(f"{mark} {choice}")
    return "\n".join(p for p in parts if p)


def _extract_with_gemini(llm: GeminiClient, settings: Settings, data: bytes, mime_type: str) -> dict:
    r = llm.generate_json(
        llm.models_for(settings.problem_extract_model),
        system=load_text("problem_extract_system.txt"),
        user=load_text("problem_extract_user.txt"),
        schema=load_json("problem_extract_schema.json"),
        temperature=settings.problem_extract_temperature,
        images=[(data, mime_type)],
    )
    d = r.data
    found = d.get("found") is not False
    problem_text = str(d.get("problem_text") or "") if found else ""
    choices = [str(c) for c in d.get("choices") or [] if str(c).strip()] if found else []
    figure = str(d.get("figure_description") or "") if found else ""
    return {
        "text": compose_problem(problem_text, choices, figure),
        "engine": "gemini",
        "model": r.model,
        "problem_text": problem_text,
        "choices": choices,
        "figure_description": figure,
        "fallback_reason": None,
    }


def vision_client(settings: Settings) -> GoogleVisionClient:
    """테스트에서 가짜 전송으로 바꿀 수 있게 따로 둔다."""
    return GoogleVisionClient(settings)


def _extract_with_vision(settings: Settings, data: bytes) -> dict:
    client = vision_client(settings)
    try:
        text = client.document_text(data).strip()
    finally:
        client.close()
    return {
        "text": text,
        "engine": "google_vision",
        "model": None,
        "problem_text": text,
        "choices": [],
        "figure_description": "",
        "fallback_reason": None,
    }


def _extract_with_paddle(settings: Settings, data: bytes, fallback_reason: str) -> dict:
    result = ocr.get_engine(settings).recognize(decode_bgr(data))
    text = lines_to_text(result.lines)
    return {
        "text": text,
        "engine": "paddleocr",
        "model": None,
        "problem_text": text,
        "choices": [],
        "figure_description": "",
        "fallback_reason": fallback_reason,
    }


@router.post("/ocr")
def extract_problem_text(
    file: Annotated[UploadFile, File(description="문제 사진(PNG/JPEG/WEBP)")],
    request: Request,
    settings: SettingsDep,
) -> dict:
    name = PurePath(file.filename or "unnamed").name[:255]
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{name}: {settings.max_upload_mb}MB를 넘습니다.")
    try:
        info = inspect_image(data)
        decode_bgr(data)  # 깨진 파일은 외부 API에 보내기 전에 걸러낸다
    except InvalidImage as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name}: {e}") from e

    if settings.problem_ocr_engine == "google_vision":
        if not settings.google_vision_api_key.get_secret_value():
            return _extract_with_paddle(settings, data, "vision_not_configured")
        try:
            return _extract_with_vision(settings, data)
        except VisionError:
            return _extract_with_paddle(settings, data, "vision_failed")

    models = getattr(request.app.state, "qa_models", None)
    llm = getattr(models, "llm", None)
    if llm is None:
        return _extract_with_paddle(settings, data, "llm_not_configured")
    try:
        return _extract_with_gemini(llm, settings, data, _MIME[info.extension])
    except GeminiError:
        return _extract_with_paddle(settings, data, "llm_failed")
