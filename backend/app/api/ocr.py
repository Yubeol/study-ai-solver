"""문제 사진 → 텍스트 API (프론트 QuestionForm의 "추출된 문제" 칸 채우기, D-J-001).

- 업로드 경로와 같은 인쇄체 PaddleOCR 엔진(`app.ingestion.ocr.get_engine`)을 쓴다. 첫 호출 때 모델을 올리므로 느리다.
- 사진은 저장하지 않는다. 결과 텍스트는 사용자가 화면에서 고친 뒤 `/qa`로 보낸다.
"""

from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_settings
from app.core.config import Settings
from app.ingestion import ocr
from app.ingestion.images import InvalidImage, decode_bgr, inspect_image
from app.ingestion.ocr import OcrLine

router = APIRouter(tags=["ocr"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


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


@router.post("/ocr")
def extract_problem_text(
    file: Annotated[UploadFile, File(description="문제 사진(PNG/JPEG/WEBP)")],
    settings: SettingsDep,
) -> dict:
    name = PurePath(file.filename or "unnamed").name[:255]
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{name}: {settings.max_upload_mb}MB를 넘습니다.")
    try:
        inspect_image(data)
        image = decode_bgr(data)
    except InvalidImage as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name}: {e}") from e

    result = ocr.get_engine(settings).recognize(image)
    return {
        "text": lines_to_text(result.lines),
        "line_count": len(result.lines),
        "mean_confidence": result.mean_confidence,
    }
