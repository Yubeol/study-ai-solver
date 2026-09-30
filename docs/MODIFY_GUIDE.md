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
| 청크 크기·겹침·짧은 끝 조각 합치기 | `.env` | `CHUNK_MAX_CHARS`(800), `CHUNK_OVERLAP_CHARS`(120), `CHUNK_MIN_CHARS`(80). 글자 수 기준, 청크는 페이지를 넘지 않음 | `cd backend; uv run python -m app.ingestion.run_stages --subject subject1` → 요약의 `clean_chars`, `data/reports/chunking/subject1.txt` |
| 제목으로 인정할 최대 길이 | `.env` | `CHUNK_HEADING_MAX_CHARS`(60). "1. …", "2) …"여도 이보다 길면 본문 | 위 dry-run → 리포트의 청크 `제목=` |
| 검색에서 뺄 조각(R 출력·그림 글자) 기준 | `.env` | `CHUNK_REVIEW_MAX_CHARS`(80) 미만 **그리고** 본문 한글 비율 `CHUNK_REVIEW_MIN_HANGUL_RATIO`(0.3) 미만이면 needs_review=true | 위 dry-run 요약의 `needs_review` |
| 머리말/쪽번호 제거, 제목 인식, 기출 표시(exam_clues), 기출 문제 블록(제외 영역) 규칙 | `backend/app/ingestion/chunking.py` | 맨 위 패턴(`_BOOK_HEADER`, `_SUBJECT_FOOTER`, `_SECTION`, `_ITEM`, `_EXAM_MARK`, `_EXAM_BLOCK_START`, `_EXAM_BLOCK_END` 등), `looks_like_exam`(다음 쪽으로 이어지는 문제 블록 판단). 규칙 설명은 DECISIONS D-019 | `uv run pytest backend/tests/test_chunking.py` → dry-run 리포트 확인 → `--apply --subject …`(기존 청크를 지우고 다시 넣음, 임베딩도 다시 해야 함) |
| 임베딩 모델·차원 | `.env` | `EMBEDDING_MODEL`(BAAI/bge-m3), `EMBEDDING_DIM`(1024, DB 컬럼이 vector(1024)라 바꾸면 안 됨). 모델을 바꾸면 전체 재임베딩 필요 | `uv run pytest -m embedding_model` |
| 임베딩 장치 | `.env` | `EMBEDDING_DEVICE` (기본 `cpu`, `.env`에 없으면 config 기본값 cpu). 지금 설치된 torch는 CPU 빌드라 GPU 값은 동작하지 않음 | `uv run pytest -m embedding_model` |
| 임베딩 모델 저장 위치 | `.env` | `EMBEDDING_MODEL_DIR` (HF_HOME으로 전달, 현재 `E:\hf_models`, 비우면 C:) | 첫 실행 후 그 폴더 아래 `hub/models--BAAI--bge-m3` |
| 임베딩 속도·메모리 | `.env` | `EMBEDDING_BATCH_SIZE`(8), `EMBEDDING_MAX_SEQ_LENGTH`(1024 토큰, 넘으면 잘림) | `run_stages --stages embed --pages 14,15` 실행 시간 |
| 검색 개수(Top-K) | `.env` | `SEARCH_TOP_K`(5) | `cd backend; uv run python -m app.retrieval.search "질문"` |
| 검색 평가 질문 세트·임계값 후보 | `.env` / `data/eval/questions.csv` | `EVAL_QUESTIONS_PATH`(질문 CSV, 형식은 ARCHITECTURE "검색 평가"), `EVAL_RANK_DEPTH`(20, 정답 순위 찾는 깊이), `EVAL_THRESHOLDS`(0.40,0.45,0.50,0.55,0.60) | `cd backend; uv run python -m app.retrieval.evaluate --check`(형식만) → `uv run python -m app.retrieval.evaluate` → `data/reports/eval/` |
| 검색 평가 HTML 보고서 | `.env` | `EVAL_REPORT_THUMB_WIDTH`(320, 페이지 썸네일 가로 픽셀), `EVAL_REPORT_TEXT_CHARS`(200, 청크 텍스트 앞부분 글자 수). 평가 실행 시 자동 생성, 이미 있는 json으로 다시 만들기: `cd backend; uv run python -m app.retrieval.eval_report [json 경로]` | `data/reports/eval/{시각}.html` (썸네일은 `thumbs/`, 교재 이미지라 커밋 안 함) |
| 청킹·임베딩 다시 돌리기 | 명령 | `cd backend; uv run python -m app.ingestion.run_stages --apply --subject all` (청킹, VERIFIED) / `--stages embed` (임베딩, EMBEDDED) / `--stages chunk,embed` / `--pages 14,15`로 쪽 제한 / 업로드 자료는 `--book-id`. Ctrl+C로 끊으면 그 run은 FAILED로 닫히고, 같은 명령을 다시 실행하면 됨 | DataGrip: `mingyu.theory_chunks`, `pages.page_metadata.chunking` |
| DB 구조(컬럼·테이블 추가) | `backend/migrations/` | 새 번호 파일(`003_...sql`) 추가. 적용된 파일은 수정 금지, 팀 규격 컬럼은 추가만 | `cd backend; uv run python -m app.db.migrate --dry-run` → 사용자 확인 → `uv run python -m app.db.migrate` |

## 2. 아직 없는 기능 (구현하면 채운다)

| 바꾸고 싶은 것 | 열어야 할 파일 | 무엇을 바꾸면 되는지 | 바꾼 뒤 확인 방법 |
|---|---|---|---|
| 원근·조명 보정 강도 | | | |
| 시각자료 검출(레이아웃 모델, 신뢰도 기준) | | | |
| crop 여백 | | | |
| 시각자료 설명문 프롬프트 | | | |
| 벡터/키워드 검색 비중(하이브리드) | | | |
| 답변 생성 프롬프트(시험모드) | | | |
| 제약 프리셋 | | | |
| 문제 사진 추출 프롬프트(그래프 텍스트화 포함) | | | |
| 판정기 신뢰도 임계값 | | | |
| Gemini 재시도 횟수·대기 시간, 분당 요청 수 | | | |
| 오답노트 틀린 유형·비교 프롬프트 | | | |
| 재질문 문제 생성 프롬프트 | | | |
| 검수 보고서 표시 항목·색 | | | |
| 손필기 추출 프롬프트 | | | |
