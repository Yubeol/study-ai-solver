"""`.env` 설정 로딩.

모델 이름, 스키마 이름 등은 코드에 하드코딩하지 않고 모두 이 설정에서 가져온다.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → 저장소 루트
ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"

_IDENTIFIER_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 공유 DB
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: SecretStr
    db_schema: str
    db_app_schema: str

    # LLM / Vision
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model_lite: str = ""
    gemini_model_strong: str = ""

    # 임베딩
    embedding_model: str = ""
    embedding_dim: int = 1024

    # 판정기
    judge_provider: Literal["none", "jev_typesafe", "jev_cloudflare", "llm"] = "none"
    typesafe_api_key: SecretStr = SecretStr("")
    cloudflare_account_id: str = ""
    cloudflare_api_token: SecretStr = SecretStr("")

    # 파일 저장소
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_dir: Path = Field(default=Path("data/storage"))
    s3_bucket: str = ""
    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: SecretStr = SecretStr("")

    # 업로드
    max_upload_mb: int = Field(default=20, gt=0)

    @field_validator("db_schema", "db_app_schema")
    @classmethod
    def _check_schema_name(cls, v: str) -> str:
        # 스키마 이름은 식별자로 쿼리에 들어가므로 소문자/숫자/밑줄만 허용한다.
        if not v or not set(v) <= _IDENTIFIER_CHARS or v[0].isdigit():
            raise ValueError(f"잘못된 스키마 이름: {v!r}")
        return v

    @property
    def storage_dir(self) -> Path:
        p = self.local_storage_dir
        return p if p.is_absolute() else ROOT_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
