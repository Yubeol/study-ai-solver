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
    gemini_timeout_seconds: float = Field(default=60, gt=0)  # 요청 1번의 제한 시간
    gemini_max_retries: int = Field(default=3, ge=0)  # 429/503/시간 초과 시 같은 모델로 다시 시도할 횟수(D-010)
    gemini_retry_base_seconds: float = Field(default=2, ge=0)  # 재시도 대기 = 이 값 × 2^(시도-1)

    # 질의 답변 (ARCHITECTURE "질의 흐름"). 프롬프트는 backend/app/prompts/answer_*.txt
    answer_model: Literal["lite", "strong"] = "lite"  # strong이 재시도 후에도 실패하면 lite로 폴백(D-010)
    # 0 고정(2026-10-01): 실행 간 흔들림을 줄여 비교 가능하게. 0이어도 완전 결정적이라는 보장은 없음(D-025)
    answer_temperature: float = Field(default=0, ge=0, le=2)
    # 서버 시작 시 임베딩·리랭커를 로드하고 한 번 돌려 둔다(첫 질문 지연 방지). false면 질의 API가 503(지연 로딩 안 함).
    # 테스트(conftest)에서만 false로 둔다.
    preload_models: bool = True

    # 임베딩
    embedding_model: str = ""
    embedding_dim: int = 1024
    embedding_model_dir: Path | None = None  # HF_HOME으로 전달(모델·xet 캐시). 비우면 ~/.cache/huggingface(C:)
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=8, gt=0)
    embedding_max_seq_length: int = Field(default=1024, gt=0)  # 토큰. 청크는 약 800자라 충분(모델 최대 8192)
    # true면 HF_HUB_OFFLINE=1로 모델을 캐시(EMBEDDING_MODEL_DIR)에서만 읽는다(인터넷 확인 안 함). 캐시에 없으면 오류
    embedding_offline: bool = False

    # 검색
    search_top_k: int = Field(default=5, gt=0)
    search_candidates_n: int = Field(default=10, gt=0)  # 리랭커에 넘길 벡터 후보 수(리랭커 없으면 안 씀, D-024)

    # 리랭커 (ARCHITECTURE "검색 단계 상세"). 모델 이름이 비면 리랭크 없이 벡터 순위 그대로. 캐시는 EMBEDDING_MODEL_DIR
    reranker_model: str = ""
    reranker_max_length: int = Field(default=1024, gt=0)  # 질문+청크 토큰 최대(넘으면 잘림)
    reranker_batch_size: int = Field(default=8, gt=0)
    reranker_device: str = "cpu"
    reranker_input: Literal["embedding_text", "clean_text"] = "embedding_text"  # 청크 쪽 입력 텍스트

    # "확인 불가" 판단 (ARCHITECTURE "확인 불가" 3구간). 1단계: 벡터 1위 점수 < 하한이면 바로 확인 불가.
    # 2단계(리랭커 1위 점수): < 하한 → 확인 불가(reject) / 하한~상한 → 회색(gray) / ≥ 상한 → 답변(answer).
    # 리랭커가 없으면 2단계 생략. 값은 33문항 기준 잠정값(D-024)
    answerable_min_vector_score: float = Field(default=0.45, ge=0, le=1)
    answerable_min_rerank_score: float = Field(default=0.03, ge=0, le=1)
    answerable_confident_rerank_score: float = Field(default=0.15, ge=0, le=1)

    # 검색 평가 (ARCHITECTURE "검색 평가")
    eval_questions_path: Path = Field(default=Path("eval/questions.csv"))  # 상대경로면 저장소 루트 기준
    eval_rank_depth: int = Field(default=20, gt=0)  # 정답 순위를 찾을 깊이(K보다 작으면 K)
    eval_thresholds: str = "0.40,0.45,0.50,0.55,0.60"  # "확인 불가" 1위 점수 임계값 후보(쉼표 구분)
    eval_rerank_thresholds: str = "0.01,0.05,0.1,0.15,0.2,0.3,0.5,0.7"  # 리랭커 1위 점수 임계값 후보
    eval_report_thumb_width: int = Field(default=320, gt=0)  # HTML 보고서 페이지 썸네일 가로 픽셀
    eval_report_text_chars: int = Field(default=200, gt=0)  # HTML 보고서에 보일 청크 텍스트 앞부분 글자 수
    # 기출 객관식 답변 확인 (python -m app.qa.mcq_run)
    mcq_selection_path: Path = Field(default=Path("data/eval/mcq_selection.json"))  # 실행할 문제 key 목록
    mcq_request_interval_seconds: float = Field(default=6.0, ge=0)  # /qa 요청 사이 대기(Gemini 무료 한도)
    mcq_max_questions: int = Field(default=20, gt=0)  # 한 번에 실행할 최대 문제 수

    # 판정기
    judge_provider: Literal["none", "jev_typesafe", "jev_cloudflare", "llm"] = "none"
    typesafe_api_key: SecretStr = SecretStr("")
    # Jev(TypeSafe 직접 API, D-007). 회색 구간에서만 can_answer(noul, 예일 확률 0~1)를 부른다(D-028).
    jev_api_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = Field(default=20, gt=0)  # 요청 1번의 제한 시간
    judge_max_retries: int = Field(default=2, ge=0)  # 429/529/5xx/시간 초과 시 다시 시도할 횟수
    judge_retry_base_seconds: float = Field(default=2, ge=0)  # 재시도 대기 = 이 값 × 2^(시도-1)
    # 회색 구간 판정 (잠정값, 재적재 후 다시 조정): 확률 < CAN_ANSWER_MIN → 확인 불가(LLM 호출 없음) /
    # CAN_ANSWER_MIN 이상 → 답변, 그중 CONFIDENT_MIN 이상이면 "근거 확신 낮음" 해제
    judge_can_answer_min: float = Field(default=0.5, ge=0, le=1)
    judge_confident_min: float = Field(default=0.8, ge=0, le=1)
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
    # 보충 이론 등록(POST /supplements, D-JW-004). 파일 크기 한도는 MAX_UPLOAD_MB를 같이 쓴다.
    supplement_max_text_chars: int = Field(default=20000, gt=0)
    supplement_max_pdf_pages: int = Field(default=50, gt=0)

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

    # 공통 JSON 적재 (D-M-032, python -m app.ingestion.common_json_load). 과목 폴더 subject{n}/ 아래
    # *_blocks.json, *_relations.json(+ manifest, validation_report)
    common_json_dir: Path = Field(default=Path("data/common_json"))
    common_json_subject: str = "ADsP"  # documents.subject 값(books.subject와 같게)
    # 검색 제외 규칙(행은 저장, search_enabled=false). true로 바꾸고 다시 적재하면 검색 대상이 된다(비교 실험용)
    common_json_search_learning_objective: bool = False  # block_role=learning_objective(학습목표·출제 중요도)
    common_json_search_duplicate_theory: bool = False  # duplicate_of_table_id가 있는 이론(표가 대표)
    # 수정본을 기다리는 block_id(쉼표 구분). 적재는 하되 리포트에 경고로 표시
    common_json_pending_block_ids: str = ""

    # 이론 청킹 (D-019). 글자 수 기준(공백 포함). 청크는 페이지를 넘지 않는다.
    chunk_max_chars: int = Field(default=800, gt=0)  # 청크 clean_text 최대 길이(문단 하나가 더 길면 자르지 않음)
    chunk_overlap_chars: int = Field(default=120, ge=0)  # 긴 절을 나눌 때 앞 조각 끝 문단을 이만큼까지 다시 넣음
    chunk_min_chars: int = Field(default=80, ge=0)  # 이보다 짧은 끝 조각은 앞 조각에 합침
    chunk_heading_max_chars: int = Field(default=60, gt=0)  # 번호가 있어도 이보다 긴 줄은 제목이 아닌 본문
    # clean_text가 review_max_chars보다 짧고 본문 한글 비율이 이보다 낮으면 needs_review=true(검색 제외)
    chunk_review_max_chars: int = Field(default=80, ge=0)
    chunk_review_min_hangul_ratio: float = Field(default=0.3, ge=0, le=1)

    @field_validator("ocr_model_dir", "embedding_model_dir", mode="before")
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

    @model_validator(mode="after")
    def _check_rerank_zones(self):
        if self.answerable_min_rerank_score > self.answerable_confident_rerank_score:
            raise ValueError("ANSWERABLE_MIN_RERANK_SCORE는 ANSWERABLE_CONFIDENT_RERANK_SCORE 이하여야 합니다.")
        if self.judge_can_answer_min > self.judge_confident_min:
            raise ValueError("JUDGE_CAN_ANSWER_MIN은 JUDGE_CONFIDENT_MIN 이하여야 합니다.")
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

    @property
    def common_json_path(self) -> Path:
        return _from_root(self.common_json_dir)

    @property
    def common_json_pending_block_id_set(self) -> set[str]:
        return {x.strip() for x in self.common_json_pending_block_ids.split(",") if x.strip()}

    @property
    def eval_questions_file(self) -> Path:
        return _from_root(self.eval_questions_path)

    @property
    def mcq_selection_file(self) -> Path:
        return _from_root(self.mcq_selection_path)

    @property
    def eval_threshold_list(self) -> list[float]:
        return _floats(self.eval_thresholds)

    @property
    def eval_rerank_threshold_list(self) -> list[float]:
        return _floats(self.eval_rerank_thresholds)


def _floats(s: str) -> list[float]:
    return [float(x) for x in s.split(",") if x.strip()]


def _from_root(p: Path) -> Path:
    """상대 경로는 저장소 루트 기준으로 해석한다."""
    return p if p.is_absolute() else ROOT_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
