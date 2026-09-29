from app.core.config import Settings
from app.storage.base import Storage


def get_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        from app.storage.local import LocalStorage

        return LocalStorage(settings.storage_dir)
    from app.storage.s3 import S3Storage

    return S3Storage(settings)
