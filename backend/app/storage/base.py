"""파일 저장소 인터페이스.

업로드 원본과 이후 crop 산출물을 저장한다. DB에는 `save()`가 돌려준 URI만 저장하고,
실제 위치(로컬 폴더 / S3 버킷)는 구현체가 해석한다. `STORAGE_BACKEND`로 교체한다.
"""

from abc import ABC, abstractmethod
from pathlib import PurePosixPath


class Storage(ABC):
    scheme: str

    @abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """`key`(예: books/{book_id}/{page_id}.png)에 저장하고 URI를 돌려준다."""

    @abstractmethod
    def read(self, uri: str) -> bytes: ...

    @abstractmethod
    def delete(self, uri: str) -> None:
        """없는 파일이면 조용히 넘어간다."""


def validate_key(key: str) -> str:
    """상대 경로 형태의 키만 허용한다(경로 탈출 방지)."""
    if not key or "\\" in key or ":" in key:
        raise ValueError(f"잘못된 저장소 키: {key!r}")
    p = PurePosixPath(key)
    if p.is_absolute() or any(part in ("", ".", "..") for part in key.split("/")):
        raise ValueError(f"잘못된 저장소 키: {key!r}")
    return key
