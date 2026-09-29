# ARCHITECTURE

## 저장소 구조
```text
adsp-study-rag/
├── pyproject.toml / uv.lock / .python-version   # 백엔드 Python 환경 (루트), pytest 설정 포함
├── .env / .env.example
├── CLAUDE.md
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI 앱 (lifespan에서 커넥션 풀 열고 닫음)
│   │   ├── api/           # 라우터: health, books(과목·자료·업로드), runs(처리 상태), deps
│   │   ├── core/config.py # .env 설정 (pydantic-settings, 스키마 이름 검증)
│   │   ├── db/            # connection.py(풀, scoped_transaction), migrate.py(마이그레이션 실행기)
│   │   ├── repositories/  # books / pages / runs SQL (스키마는 Identifier로 명시)
│   │   ├── storage/       # Storage 인터페이스, local(구현), s3(자리만), get_storage()
│   │   └── ingestion/     # images(업로드 검증·decode_bgr), ocr(PaddleOCR 엔진, 지연 로딩·잠금), pipeline(단계 실행·상태 갱신), stages(단계 함수)
│   │   # 이후 추가 예정: retrieval, judge, llm
│   ├── migrations/   # 번호 붙은 SQL 파일 (DDL 변경 이력)
│   └── tests/        # DB 테스트는 접속 불가 시 skip
├── frontend/         # React + Vite (미생성)
├── docs/
└── data/             # 로컬 이미지/산출물 (gitignore)
```
- 실행: `cd backend; uv run uvicorn app.main:app --reload` → `/health`, `/health/db`, `/docs`

## API (현재)
- `GET /subjects`: books.subject 고유값
- `POST /books` {title, subject, material_type, edition?, source_name?} / `GET /books?subject=` / `GET /books/{id}` (page_count, status_counts 포함)
- `POST /books/{id}/pages` (multipart `files` 여러 장, PNG/JPEG/WEBP, 장당 `MAX_UPLOAD_MB`) → 202 {run_id, pages}. 전부 검증 후 저장, 한 장이라도 실패하면 아무것도 저장하지 않음
- `GET /books/{id}/pages`, `GET /processing-runs/{run_id}` (run 요약 + 페이지별 상태·현재 단계·오류)
- 응답에서 저장소 URI(source_s3_uri)는 뺀다.
- 테스트: 루트에서 `uv run pytest`

## DB 접근 규칙 (구현)
- 드라이버: psycopg 3 + psycopg_pool, ORM 없이 SQL 직접 작성. 풀 연결은 autocommit, 트랜잭션은 `conn.transaction()`으로 명시.
- 스키마 지정: `sql.Identifier(settings.db_schema)`로 명시하거나 `scoped_transaction()`(트랜잭션 안 `SET LOCAL search_path TO app_schema, schema, public`)을 쓴다. public은 확장 타입/연산자용.
- 마이그레이션: `backend/migrations/NNN_*.sql`에 `{{schema}}`, `{{app_schema}}` 자리표시자를 쓰고 실행기가 설정값으로 치환한다. 파일당 트랜잭션 1개, 이력은 `{{app_schema}}.schema_migrations`(파일명+sha256). 적용된 파일을 수정하면 실행기가 오류를 낸다 → 변경은 새 번호 파일로.
  - `cd backend; uv run python -m app.db.migrate --dry-run` (치환 결과만 출력) / `uv run python -m app.db.migrate` (적용)

## DB (확정)
- 팀 공유 PostgreSQL 16.15, DB `cert_rag`, pgvector 0.8.6, pg_trgm 1.6, pgcrypto 1.3
- 내 스키마: `mingyu` (팀 규격 테이블, 팀원이 생성 완료). 다른 스키마: jaewon, sugi, sumin (접근 금지)
- 내 서비스용 스키마: `mingyu_app` (002 마이그레이션으로 생성, 2026-09-29)
- 확장은 모두 `public`에 설치됨 → 인덱스 연산자 클래스는 `public.gin_trgm_ops`처럼 명시

### mingyu 스키마 (팀 규격, 기존)
- 자료 계층: books → chapters(parent_chapter_id 계층, sort_order) → pages(source_s3_uri, processing_status CHECK, quality_passed, review_required, processing_run_id)
- 검색 대상: theory_chunks(embedding_text NOT NULL, embedding vector(1024), embedding_enabled, needs_review), visual_assets(visual_type CHECK, crop_s3_uri, 구조 JSONB 다수, embedding_text, embedding, crop_complete)
- 구조 데이터: visual_groups, visual_tables(page 단위 독립, 임베딩 없음), formulas(임베딩 없음)
- 관계: theory_visual_links, visual_formula_links, concept_relations, concepts(canonical_name, aliases)
- 제외 영역: excluded_sections(page_id, section_type, reason, bbox, needs_review) — 예제/기출/코드 등 검색 제외 구간
- 운영: processing_runs(status CHECK RUNNING/SUCCESS/PARTIAL/FAILED), constraint_presets(settings JSONB, 기존 3행), query_logs(question_text, question_image_s3_uri, retrieved_*_ids, answer, 비용)
- pages.processing_status CHECK: RAW / EXTRACTED / REVIEW_REQUIRED / VERIFIED / EMBEDDED / FAILED
- 인덱스: theory_chunks HNSW(vector_cosine_ops, WHERE embedding_enabled), visual_assets HNSW(cosine), theory_chunks.clean_text trgm, books.title trgm
- 뷰: v_searchable_theory(enabled + 임베딩 있음 + needs_review=false), v_searchable_visual(임베딩 있음 + needs_review=false + crop_complete), v_review_queue
- 주의: 표·수식은 이론과 직접 링크가 없으므로 page_id / concept_id로 모아 온다.

### mingyu 스키마 보완 (001 적용 완료, 컬럼/인덱스 추가만)
- books: subject, material_type(CHECK textbook/lecture_note/personal_note), books_subject_idx
- theory_chunks: sort_order(페이지 내 순서), processing_run_id(FK SET NULL), (page_id, sort_order) 인덱스
- visual_assets: processing_run_id(FK SET NULL)
- trgm 인덱스: visual_assets.embedding_text, concepts.canonical_name
- 새 컬럼은 모두 NULL 허용. 기존 뷰는 변경하지 않았으므로 v_searchable_*에는 새 컬럼이 없다(필요 시 원본 테이블 조인).

### mingyu_app 스키마 (002 적용 완료)
- schema_migrations: filename, checksum, applied_at
- problems: input_type(image/text), image_uri, question_text, subject, status(RECEIVED/EXTRACTED/SOLVED/FAILED)
- problem_extractions: extractor, problem_text, choices/formulas(JSONB 배열), confidence(0~1), raw_output
- solutions: problem_id, query_log_id(→ mingyu.query_logs, SET NULL), question_text, model, answer, explanation, path(fast/retry), confidence_label(high/medium/low/unanswerable), constraint_preset_id(→ mingyu.constraint_presets, SET NULL), preset_snapshot, latency/token/cost
- solution_evidence: source_schema, source_kind(theory/visual/table/formula), source_id, rank(solution별 UNIQUE), score, quoted_text(스냅샷)
- judgments: solution_id/problem_id, provider, question_key(can_answer/classify/choose/verify), answer(JSONB), confidence, latency, cost
- 요약 로그는 팀 규격 query_logs에도 기록한다.

## 자료 적재 흐름 (업로드 → 백그라운드 처리)
업로드 API가 파일을 저장소(local 또는 S3)에 저장하고 pages 행과 processing_runs 1건을 만든 뒤 백그라운드 작업(FastAPI BackgroundTasks)을 시작한다.

### 구현 상태 (뼈대, 2026-09-29)
- 저장: `local://books/{book_id}/{page_id}.{ext}` (LOCAL_STORAGE_DIR 기준). 원본 바이트 그대로, 원본 파일명은 page_metadata.original_filename
- 페이지 순서: page_metadata.upload_index (book 단위로 이어 붙임)
- 단계와 상태 매핑 (D-012): extract_text → EXTRACTED / detect_visuals, chunk_theory → VERIFIED / embed → EMBEDDED
  - 단계가 `NeedsReview`를 던지면 REVIEW_REQUIRED(review_required=true) 후 그 페이지 중단, 그 밖의 예외는 FAILED
  - 현재 단계·오류·사유·갱신 시각은 page_metadata.pipeline에 기록
  - run 집계: 전부 성공 SUCCESS / 전부 실패 FAILED / 그 외 PARTIAL
- 구현된 단계: extract_text(인쇄체 PaddleOCR, D-013). 나머지 단계는 `StageNotImplemented` → 페이지는 EXTRACTED에서 멈추고 `pipeline.stopped="not_implemented"`, run은 PARTIAL. 아래 2~5를 하나씩 채운다.
- extract_text: books.material_type 확인 → personal_note는 REVIEW_REQUIRED("손필기 추출 미구현") / 그 외는 저장소 원본 바이트 → `cv2.imdecode` → OCR → 전체 결과 `books/{book_id}/{page_id}.ocr.json`(engine + lines[text, confidence, bbox]) 저장, `page_metadata.ocr`에 요약(uri, line_count, mean_confidence, 엔진·모델)
- OCR 엔진은 프로세스당 1개(첫 호출 시 로드), 추론은 잠금으로 직렬화. 모델 캐시는 `OCR_MODEL_DIR`(→ PADDLE_PDX_CACHE_HOME)
- 테스트: 기본 `uv run pytest`는 가짜 OCR 엔진 사용, 실제 모델은 `uv run pytest -m ocr_model`(맑은 고딕 없으면 skip)
- 단계 목록은 `app.state.pipeline_stages`로 주입(테스트에서 가짜 단계 사용)

### 목표 단계
1. 텍스트 추출: 교재·강의노트(인쇄체) → PaddleOCR / 개인노트(손필기) → 비전 LLM
2. 기울기 보정, 시각자료 자동 crop(OpenCV/Pillow), 세트 그림 묶기(visual_groups), 표 구조화
3. 이론 청킹(sort_order 부여), 수식 구조화, 제외 영역(예제/기출/코드) 분리
4. 시각자료 설명문 + embedding_text 생성: crop + 관련 이론 문장 2~5개 → GEMINI_MODEL_LITE, 품질 낮은 것만 GEMINI_MODEL_STRONG 재처리
5. 로컬 임베딩(BGE-M3, 1024) → 저장, 링크 테이블 채우기

## 질의 흐름
1. 입력: 질문 텍스트 또는 문제 이미지(비전 LLM으로 문제문·보기·수식 추출)
2. 검색: 선택 과목 범위에서 하이브리드 검색(벡터 + trgm), 이론 → 연결된 시각자료·같은 페이지 표/수식 확장
3. 답변 가능 판정(판정기): 근거로 답할 수 없으면 LLM 호출 없이 "자료에서 확인 불가"
4. 답변 생성: 기본 시험모드 + 선택한 제약 프리셋, 근거 번호 인용 강제
5. 근거 일치 판정(판정기): 낮으면 강한 모델 재생성 또는 "확신 낮음" 표시
6. 저장: mingyu_app 상세 + query_logs 요약

## 판정기 (교체 가능 모듈)
- 인터페이스: `can_answer`(근거로 답 가능?), `classify`(단원·유형 선택), `choose`(객관식 후보), `verify`(답이 근거와 일치?)
- 구현체: `jev_typesafe`, `jev_cloudflare`, `llm`(Gemini 구조화 출력), `none`(판정 생략)
- `JUDGE_PROVIDER`로 선택. 신뢰도 임계값은 제공자별로 따로 둔다.

## 화면 (React + Vite)
- A. 자료 업로드: 과목 선택/생성, 자료 유형, 다중 업로드, 처리 상태
- B. 공부: 과목, 질문 또는 문제 사진, 제약 프리셋, 답변 + 근거 청크 + 출처
- C. 관리: 과목·자료 목록, 삭제/재임베딩, 사용 로그