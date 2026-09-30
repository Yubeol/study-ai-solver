# MODIFY_GUIDE — 무엇을 바꾸려면 어디를 고치나 (2026-09-30 기준)

사용자가 직접 값을 조정할 때 보는 문서다. 원칙은 CLAUDE.md의 "조정 가능한 값" 규칙을 따른다. 조정할 만한 값은 `.env` 또는 `backend/app/core/config.py` 한 곳에 있고, LLM 프롬프트 문장은 `backend/app/prompts/` 아래 텍스트 파일에 둔다.

- `.env`를 바꾼 뒤에는 **서버를 껐다가 다시 켜야** 반영된다(`--reload`는 코드 파일 변경만 감지한다).
- 새 설정 이름을 추가할 때는 `config.py`의 `Settings`와 `.env.example`을 같이 고친다.
- 서버 실행: `cd backend; uv run uvicorn app.main:app --reload` / 테스트: 루트에서 `uv run pytest`

## 1. 지금 있는 기능

| 바꾸고 싶은 것 | 열어야 할 파일 | 무엇을 바꾸면 되는지 | 바꾼 뒤 확인 방법 |
|---|---|---|---|
| DB 접속 정보 | `.env` | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | 서버 재시작 → `/docs`에서 `GET /health/db`가 `"status": "ok"` |
| 사용할 스키마 이름 | `.env` | `DB_SCHEMA`(팀 규격, mingyu), `DB_APP_SCHEMA`(서비스용, mingyu_app). 소문자·숫자·밑줄만 가능 | `GET /health/db`의 `schema`, `app_schema`가 true |
| 업로드 1장 최대 크기 | `.env` | `MAX_UPLOAD_MB` (기본 20) | 그보다 큰 이미지를 업로드하면 413 오류 |
| 업로드 허용 형식 | `backend/app/ingestion/images.py` | `ALLOWED_FORMATS` (Pillow 형식 이름 → 저장 확장자) | `uv run pytest` / 해당 형식 업로드가 202 |
| 파일 저장 위치 | `.env` | `LOCAL_STORAGE_DIR` (기본 `data/storage`, 상대경로면 저장소 루트 기준) | 업로드 후 그 폴더 아래 `books/{book_id}/`에 파일이 생기는지 |
| 저장소 종류(local/S3) | `.env` | `STORAGE_BACKEND` — **S3는 아직 미구현**, local만 동작 | — |
| OCR 모델 | `.env` | `OCR_DET_MODEL`(검출), `OCR_REC_MODEL`(인식). 검출을 지정하면 인식도 반드시 지정(D-013). server_det는 CPU에서 너무 느림 | 서버 재시작 → 이미지 1장 업로드 → `pages.page_metadata.ocr`의 `det_model`, `rec_model`, `mean_confidence` / `uv run pytest -m ocr_model` |
| OCR 언어 | `.env` | `OCR_LANG` (모델 이름을 비웠을 때만 쓰임) | 위와 같음 |
| OCR 모델 저장 위치 | `.env` | `OCR_MODEL_DIR` (영문 경로 권장, 현재 `E:\paddle_models`) | 첫 업로드 후 그 폴더 아래 `official_models`에 모델이 생기는지 |
| OCR 장치 | `.env` | `OCR_DEVICE` (현재 `cpu`) | OCR 테스트 실행 |
| OCR 세부 옵션(방향 분류, oneDNN 등) | `backend/app/ingestion/ocr.py` | `PaddleOCR(...)` 호출 인자. `enable_mkldnn=False`는 Paddle 버그 때문(D-013) | `uv run pytest -m ocr_model`, 1장 처리 시간 비교 |
| 처리 단계 순서·단계별 완료 상태 | `backend/app/ingestion/pipeline.py` | `DEFAULT_STAGES` (단계 이름, 함수, 끝나면 설정할 상태) | `uv run pytest` / 업로드 후 `GET /processing-runs/{run_id}` |
| 파이프라인 버전 표시 | `backend/app/ingestion/pipeline.py` | `PIPELINE_VERSION` (processing_runs.pipeline_version에 기록) | DataGrip: `mingyu.processing_runs.pipeline_version` |
| DB 커넥션 풀 크기 | `backend/app/db/connection.py` | `create_pool`의 `min_size`, `max_size` (현재 1/5, 공유 서버이므로 크게 늘리지 않기) | 서버 재시작 → `GET /health/db` |
| Gemini 모델 | `.env` | `GEMINI_MODEL_LITE`, `GEMINI_MODEL_STRONG` — 지금은 processing_runs.gemini_model 기록에만 쓰임 | DataGrip: `mingyu.processing_runs.gemini_model` |
| 판정기 선택 | `.env` | `JUDGE_PROVIDER` (none / jev_typesafe / jev_cloudflare / llm) — 지금은 `/health/db` 표시에만 쓰임 | `GET /health/db`의 `judge_provider` |
| 팀 교재 PDF 장 ↔ 인쇄 쪽 매핑, 과목 제목, 합본 텍스트 파일 처리 | `data/raw/adsp/page_map.json` (gitignore) | `segments`(PDF 장 범위 + offset), `skip_pdf`(중복 촬영 등 건너뛸 장), `text_files`(여러 쪽짜리 텍스트 파일 → 쪽 목록. `split_at_lines`로 나눌 줄 번호 지정, 없으면 첫 쪽에 붙음), `title`/`subject`/`source_name` | `cd backend; uv run python -m app.ingestion.team_import --dry-run` → 요약과 `data/reports/team_import/plan.json`. 실제 반입은 `--apply --subject subject1`(전체는 `all`), 결과는 `apply_{key}.json` |
| 팀 교재 저장 이미지 해상도·화질 | `.env` | `TEAM_IMPORT_RENDER_DPI`(72 = 원본 해상도), `TEAM_IMPORT_JPEG_QUALITY` | dry-run 끝 줄에 적용 값 표시 / 반입 후 `pages.source_width/height` |
| 팀 교재 쪽번호 대조 미리보기 | `.env` | `TEAM_IMPORT_PREVIEW_DPI` (저장용과 별개) | `uv run python -m app.ingestion.team_import --preview subject3:84,85` → `data/reports/team_import/preview_subject3.jpg` |
| 팀 교재·보고서 폴더 위치 | `.env` | `TEAM_IMPORT_DIR`, `REPORTS_DIR` | dry-run 실행 |
| DB 구조(컬럼·테이블 추가) | `backend/migrations/` | 새 번호 파일(`003_...sql`) 추가. 적용된 파일은 수정 금지, 팀 규격 컬럼은 추가만 | `cd backend; uv run python -m app.db.migrate --dry-run` → 사용자 확인 → `uv run python -m app.db.migrate` |

## 2. 아직 없는 기능 (구현하면 채운다)

| 바꾸고 싶은 것 | 열어야 할 파일 | 무엇을 바꾸면 되는지 | 바꾼 뒤 확인 방법 |
|---|---|---|---|
| 머리말/쪽번호 제거 규칙, 기출 표시(exam_clues) 규칙 | | | |
| 청크 크기·겹침 | | | |
| 제외 영역(예제/기출/코드) 판단 기준 | | | |
| 원근·조명 보정 강도 | | | |
| 시각자료 검출(레이아웃 모델, 신뢰도 기준) | | | |
| crop 여백 | | | |
| 시각자료 설명문 프롬프트 | | | |
| 임베딩 모델·차원 | | | |
| 검색 개수(Top-K), 벡터/키워드 비중 | | | |
| 답변 생성 프롬프트(시험모드) | | | |
| 제약 프리셋 | | | |
| 문제 사진 추출 프롬프트(그래프 텍스트화 포함) | | | |
| 판정기 신뢰도 임계값 | | | |
| Gemini 재시도 횟수·대기 시간, 분당 요청 수 | | | |
| 오답노트 틀린 유형·비교 프롬프트 | | | |
| 재질문 문제 생성 프롬프트 | | | |
| 검수 보고서 표시 항목·색 | | | |
| 손필기 추출 프롬프트 | | | |
