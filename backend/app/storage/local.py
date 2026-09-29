"""로컬 폴더 저장소 (STORAGE_BACKEND=local).

URI 형식: `local://{key}`. 루트 폴더는 `LOCAL_STORAGE_DIR`이며 한글 경로일 수 있으므로
pathlib + 바이트 입출력만 쓴다.
"""

from pathlib import Path

from app.storage.base import Storage, validate_key


class LocalStorage(Storage):
    scheme = "local"

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"저장소 밖을 가리키는 키: {key!r}")
        return path

    def _key(self, uri: str) -> str:
        prefix = f"{self.scheme}://"
        if not uri.startswith(prefix):
            raise ValueError(f"로컬 저장소 URI가 아님: {uri!r}")
        return uri[len(prefix):]

    def save(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"{self.scheme}://{key}"

    def read(self, uri: str) -> bytes:
        return self._path(self._key(uri)).read_bytes()

    def delete(self, uri: str) -> None:
        self._path(self._key(uri)).unlink(missing_ok=True)
