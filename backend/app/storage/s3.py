"""S3 저장소 (STORAGE_BACKEND=s3). 팀 버킷 사용 여부가 확인되면 구현한다."""

from app.core.config import Settings
from app.storage.base import Storage


class S3Storage(Storage):
    scheme = "s3"

    def __init__(self, settings: Settings):
        self.bucket = settings.s3_bucket

    def save(self, key: str, data: bytes) -> str:
        raise NotImplementedError("S3 저장소는 아직 구현되지 않았습니다. STORAGE_BACKEND=local을 쓰세요.")

    def read(self, uri: str) -> bytes:
        raise NotImplementedError("S3 저장소는 아직 구현되지 않았습니다.")

    def delete(self, uri: str) -> None:
        raise NotImplementedError("S3 저장소는 아직 구현되지 않았습니다.")
