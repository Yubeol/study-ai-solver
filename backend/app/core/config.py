"""`.env` 설정 로딩.

모델 이름, 스키마 이름 등은 코드에 하드코딩하지 않고 모두 이 설정에서 가져온다.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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

    # OCR (PaddleOCR, 인쇄체). 모델 이름이 비어 있으면 언어 기본 모델을 쓴다.
    ocr_model_dir: Path | None = None  # PADDLE_PDX_CACHE_HOME으로 전달. 비우면 ~/.paddlex
    ocr_lang: str = "korean"
    ocr_det_model: str = ""
    ocr_rec_model: str = ""
    ocr_device: str = "cpu"

    # 팀 교재 반입 (D-014, D-018). 팀 PDF는 1pt = 사진 1픽셀이라 72 DPI가 원본 해상도다.
    team_import_dir: Path = Field(default=Path("data/raw/adsp"))  # page_map.json, pdf/, team_text/ 위치
    team_import_render_dpi: int = Field(default=72, gt=0)  # 저장용 페이지 이미지
    team_import_jpeg_quality: int = Field(default=92, ge=1, le=100)
    team_import_preview_dpi: int = Field(default=14, gt=0)  # 쪽번호 대조용 저해상도 미리보기
    reports_dir: Path = Field(default=Path("data/reports"))  # dry-run 계획·미리보기 출력

    @field_validator("ocr_model_dir", mode="before")
    @classmethod
    def _empty_path_is_none(cls, v):
        return None if v == "" else v

    @field_validator("db_schema", "db_app_schema")
    @classmethod
    def _check_schema_name(cls, v: str) -> str:
        # 스키마 이름은 식별자로 쿼리에 들어가므로 소문자/숫자/밑줄만 허용한다.
        if not v or not set(v) <= _IDENTIFIER_CHARS or v[0].isdigit():
            raise ValueError(f"잘못된 스키마 이름: {v!r}")
        return v

    @model_validator(mode="after")
    def _check_ocr_models(self):
        # 검출 모델 이름만 주면 PaddleOCR가 lang을 무시하고 비한국어 인식 모델을 올린다(D-013).
        if self.ocr_det_model and not self.ocr_rec_model:
            raise ValueError("OCR_DET_MODEL을 지정하면 OCR_REC_MODEL도 지정해야 합니다.")
        return self

    @property
    def storage_dir(self) -> Path:
        return _from_root(self.local_storage_dir)

    @property
    def team_import_path(self) -> Path:
        return _from_root(self.team_import_dir)

    @property
    def reports_path(self) -> Path:
        return _from_root(self.reports_dir)


def _from_root(p: Path) -> Path:
    """상대 경로는 저장소 루트 기준으로 해석한다."""
    return p if p.is_absolute() else ROOT_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
