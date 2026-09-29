"""업로드 이미지 검증. 원본 바이트는 바꾸지 않고 형식·크기만 확인한다."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

# Pillow 형식 이름 → 저장 확장자
ALLOWED_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


class InvalidImage(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    extension: str
    width: int
    height: int


def inspect_image(data: bytes) -> ImageInfo:
    if not data:
        raise InvalidImage("빈 파일")
    try:
        with Image.open(BytesIO(data)) as img:
            fmt = img.format
            width, height = img.size
            img.verify()  # 잘린 파일 등 구조 오류 확인
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as e:
        raise InvalidImage(f"이미지로 열 수 없음 ({type(e).__name__})") from e
    if fmt not in ALLOWED_FORMATS:
        raise InvalidImage(f"지원하지 않는 형식: {fmt} (PNG/JPEG/WEBP만 가능)")
    return ImageInfo(extension=ALLOWED_FORMATS[fmt], width=width, height=height)
