"""저장소 모듈 (DB 불필요). 한글 경로에서 동작하는지 확인한다."""

import pytest

from app.core.config import get_settings
from app.storage import get_storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "자료실" / "저장소")


def test_save_read_delete_under_korean_path(storage):
    uri = storage.save("books/abc/페이지 1.png", b"\x89PNG data")
    assert uri == "local://books/abc/페이지 1.png"
    assert (storage.root / "books" / "abc" / "페이지 1.png").read_bytes() == b"\x89PNG data"
    assert storage.read(uri) == b"\x89PNG data"
    storage.delete(uri)
    assert not (storage.root / "books" / "abc" / "페이지 1.png").exists()
    storage.delete(uri)  # 없는 파일 삭제는 조용히 넘어간다


@pytest.mark.parametrize(
    "key", ["", "../x.png", "books/../../x.png", "/abs.png", "C:/x.png", "books\\x.png", "books//x.png", "./x"]
)
def test_rejects_escaping_keys(storage, key):
    with pytest.raises(ValueError):
        storage.save(key, b"x")


def test_rejects_foreign_uri(storage):
    with pytest.raises(ValueError):
        storage.read("s3://bucket/x.png")


def test_get_storage_by_setting():
    settings = get_settings()
    local = get_storage(settings.model_copy(update={"storage_backend": "local"}))
    assert isinstance(local, LocalStorage)
    assert local.root == settings.storage_dir.resolve()
    s3 = get_storage(settings.model_copy(update={"storage_backend": "s3"}))
    assert isinstance(s3, S3Storage)
    with pytest.raises(NotImplementedError):
        s3.save("books/x.png", b"x")
