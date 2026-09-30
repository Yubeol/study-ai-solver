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
│   │   ├── ingestion/     # images(업로드 검증·decode_bgr), ocr(PaddleOCR 엔진), pipeline(단계 실행·상태 갱신), stages(단계 함수), chunking(청킹 규칙), embedding(BGE-M3), team_import, run_stages
│   │   └── retrieval/     # search(v_searchable_theory 벡터 검색)
│   │   # 이후 추가 예정: judge, llm
│   ├── migrations/   # 번호 붙은 SQL 파일 (DDL 변경 이력)
│   └── tests/        # DB 테스트는 접속 불가 시 skip
├── frontend/         # React + Vite, 개인 프론트 (미생성, 공용 프론트 없음 D-021)
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
- 팀 방향(D-021): 공용 프론트 없이 각자 개인 프로젝트. 공유 DB의 팀 규격 테이블은 **기존 컬럼 변경 금지·추가만** 유지, `mingyu_app`과 API는 개인 설계로 자유롭게 정한다.
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
- (설계만, 미적용) 오답노트용 wrong_notes / wrong_note_evidence / wrong_note_attempts → 아래 "오답노트" 절

### 설계에 쓰는 기존 컬럼 메모 (2026-09-30 DB에서 확인)
- `theory_chunks.exam_clues`, `theory_chunks.confusable_concepts`는 JSONB 컬럼(별도 테이블 아님)
- `pages.printed_page_number`: 인쇄 쪽번호 (팀 교재 반입 시 채움)
- `concept_relations.relation_type` CHECK: parent / child / synonym / compare / related
- `v_review_queue`: pages 중 `review_required = true OR quality_passed = false` (청크·시각자료 단위 검수 대상은 포함하지 않음)

## 자료 적재 흐름 (업로드 → 백그라운드 처리)
업로드 API가 파일을 저장소(local 또는 S3)에 저장하고 pages 행과 processing_runs 1건을 만든 뒤 백그라운드 작업(FastAPI BackgroundTasks)을 시작한다.

### 구현 상태 (뼈대, 2026-09-29)
- 저장: `local://books/{book_id}/{page_id}.{ext}` (LOCAL_STORAGE_DIR 기준). 원본 바이트 그대로, 원본 파일명은 page_metadata.original_filename
- 페이지 순서: page_metadata.upload_index (book 단위로 이어 붙임)
- 단계와 상태 매핑 (D-012): extract_text → EXTRACTED / detect_visuals, chunk_theory → VERIFIED / embed → EMBEDDED
  - 단계가 `NeedsReview`를 던지면 REVIEW_REQUIRED(review_required=true) 후 그 페이지 중단, 그 밖의 예외는 FAILED
  - 현재 단계·오류·사유·갱신 시각은 page_metadata.pipeline에 기록
  - run 집계: 전부 성공 SUCCESS / 전부 실패 FAILED / 그 외 PARTIAL
- 구현된 단계: extract_text(인쇄체 PaddleOCR, D-013), chunk_theory(D-019), embed(이론 청크만, D-020). detect_visuals는 `StageNotImplemented` → 업로드 경로의 기본 파이프라인은 여전히 EXTRACTED에서 멈추고 `pipeline.stopped="not_implemented"`, run은 PARTIAL.
- 이후 단계만 다시 돌리기(2026-09-30): `python -m app.ingestion.run_stages`(dry-run 기본, `--apply --subject KEY|all` / `--book-id`, `--stages chunk|embed|chunk,embed`, `--pages`). detect_visuals는 건너뛰고 `page_metadata.pipeline.skipped=["detect_visuals"]` 기록, chunk_theory 후 VERIFIED, embed 후 EMBEDDED(D-019). `run_pipeline`의 `pipeline_extra`로 기록.
- chunk_theory: 추출 결과(`.text.json`의 text 또는 `.ocr.json`의 lines) → `chunking.chunk_page`(순수 함수) → 페이지 단위 트랜잭션으로 theory_chunks·excluded_sections(exam_question) 삭제 후 재삽입, `page_metadata.chunking`(end_state = 다음 페이지가 이어받을 제목 경로). 앞 페이지 상태는 같은 book의 upload_index 직전 페이지에서 읽는다.
- embed: needs_review=false 청크의 embedding_text → BGE-M3(sentence-transformers, CPU, 정규화) → embedding, embedding_enabled=true. 모델은 프로세스당 1개, 캐시는 `EMBEDDING_MODEL_DIR`(→ HF_HOME).
- 검색: `app/retrieval/search.py`의 `search_theory`(v_searchable_theory, cosine `<=>`, Top-K). 확인용 CLI `python -m app.retrieval.search "질문"`.
- extract_text: books.material_type 확인 → personal_note는 REVIEW_REQUIRED("손필기 추출 미구현") / 그 외는 저장소 원본 바이트 → `cv2.imdecode` → OCR → 전체 결과 `books/{book_id}/{page_id}.ocr.json`(engine + lines[text, confidence, bbox]) 저장, `page_metadata.ocr`에 요약(uri, line_count, mean_confidence, 엔진·모델)
- OCR 엔진은 프로세스당 1개(첫 호출 시 로드), 추론은 잠금으로 직렬화. 모델 캐시는 `OCR_MODEL_DIR`(→ PADDLE_PDX_CACHE_HOME)
- 테스트: 기본 `uv run pytest`는 가짜 OCR 엔진 사용, 실제 모델은 `uv run pytest -m ocr_model`(맑은 고딕 없으면 skip)
- 단계 목록은 `app.state.pipeline_stages`로 주입(테스트에서 가짜 단계 사용)

### 목표 단계
1. 텍스트 추출: 교재·강의노트(인쇄체) → PaddleOCR / 개인노트(손필기) → 비전 LLM / 팀 교재 3권 → 팀 텍스트 반입(아래)
2. 원근·조명 보정, 시각자료 자동 crop(아래 "시각자료 crop 파이프라인"), 세트 그림 묶기(visual_groups), 표 구조화
3. 이론 청킹(sort_order 부여), 수식 구조화, 제외 영역(예제/기출/코드) 분리
4. 시각자료 설명문 + embedding_text 생성: crop + 관련 이론 문장 2~5개 → GEMINI_MODEL_LITE, 품질 낮은 것만 GEMINI_MODEL_STRONG 재처리
5. 로컬 임베딩(BGE-M3, 1024) → 저장, 링크 테이블 채우기

### 팀 교재 반입 경로 (구현 완료 2026-09-30, D-014, D-018)
팀 교재 3권(`data/raw/adsp/`)은 업로드 API를 거치지 않고 반입 스크립트로 넣는다. extract_text 단계만 "팀 텍스트 사용"으로 바꾸고, 이후 단계(시각자료, 청킹, 임베딩)는 업로드 경로와 같은 코드를 쓴다.
1. 파일명 정리: PDF → `subject1~3.pdf`, 텍스트 폴더 → `subject1~3/`, 깨진 파일명에서 인쇄 페이지 번호만 뽑아 `p{번호:03d}.txt`로 정리(원본 zip/폴더는 보존)
2. PDF 장 ↔ 인쇄 페이지 매핑 확인: PDF 장을 이미지로 렌더링하고 쪽번호(텍스트의 "… | 14" 머리말과 이미지)로 대조. 1·3과목은 PDF가 1장 많으므로 남는 장(표지·중복 촬영 등)을 찾는다. 결과는 매핑 파일(`data/raw/adsp/page_map.json` 등)로 남기고 사용자 확인
3. books/pages 생성: 과목당 books 1행(material_type=textbook, source_name에 팀 자료 표시), PDF 장마다 pages 1행. 렌더링한 페이지 이미지를 저장소에 두고 `source_s3_uri`, `printed_page_number`를 채운다. `page_metadata`에 `pdf_index`(PDF 장 번호), `text_source="team_text"`
4. 텍스트 저장: 팀 텍스트를 extract_text 결과로 저장(`books/{book_id}/{page_id}.text.json`, engine="team_text", 출처 파일명). OCR과 달리 줄 bbox가 없다 → 청크 `source_bbox`는 비워 두고 페이지 단위 출처만 표시
5. 머리말/쪽번호 줄("1과목 데이터 이해 | 14")은 청킹 시 제외. "(★기출)", "5년간 출제 횟수", "학습목표"는 해당 청크의 `exam_clues`(JSONB)로 옮긴다. `raw_text`는 팀 텍스트 원문 그대로
- 구현(D-018): `app/ingestion/team_import.py`. 1번 파일명 정리는 하지 않고 `page_map.json`이 원본 경로를 가리킨다(NFD 파일명은 NFC 비교로 찾음).
  - page_map: `segments`(PDF 장 범위 + offset), `skip_pdf`, `missing_printed`, `text_files`(여러 쪽 파일의 쪽 목록, `split_at_lines`로 줄 단위 분할)
  - 흐름: 계획(build_plan, DB·파일 접근 없음) → 이미지(`books/{book_id}/{page_id}.jpg`, TEAM_IMPORT_RENDER_DPI)·텍스트 JSON 저장 → book 단위 트랜잭션(books + processing_runs 1건 + pages + 상태) → 실패 시 저장 파일 삭제. 같은 subject·title·source_name book이 있으면 건너뜀
  - page_metadata: pdf_file, pdf_index, upload_index, text_source, render_dpi, text{uri, engine, source_file, covers_pages, lines, note, char_count}, missing_before, pipeline
  - 반입 결과: 3권 324페이지 EXTRACTED, run PARTIAL. 리포트 `data/reports/team_import/apply_{key}.json`
- PaddleOCR 경로는 새로 업로드하는 캡처용으로 유지한다(우선순위만 뒤로).

### 시각자료 crop 파이프라인 (설계, 2026-09-30, D-016)
대상 유형(3과목에서 확인): 테두리 없는 선 그래프 세트(226쪽 λ 그래프 3개), 도식(227쪽 라쏘/릿지), 색 머리행 비교표(227쪽), 표 틀 안의 산점도 복합 그림(228쪽). 캡션은 그림 **아래**에 `<...>` 형태로 있고 팀 텍스트 3과목에 36개, 꺾쇠 없는 캡션도 있다(228쪽 "상관분석").
1. 원근·조명 보정(OpenCV): 페이지 윤곽 검출 → 원근 변환, 그림자·조명 불균일 보정. 원본 바이트는 바꾸지 않고 보정본을 별도 저장(`books/{book_id}/{page_id}.rectified.png`)
2. 레이아웃 분석 모델로 그림/표/수식/캡션 영역 검출. 후보는 PaddleOCR 계열 레이아웃 기능 — **Windows + CPU에서 동작하는지 공식 문서로 확인 전(미확인)**. 안 되면 OpenCV 윤곽·여백 기반 규칙으로 대체
3. 그룹핑·crop: 캡션 기준으로 위쪽 그림 영역을 묶고(세트 그림은 visual_groups), 제목·캡션을 포함하도록 여백을 확장해 crop. 검출 bbox는 `source_bbox`, 확장 bbox는 `expanded_crop_bbox`
4. 저장: 표 → visual_tables, 그림 → visual_assets(visual_type CHECK: graph/diagram/flowchart/tree/network/venn/matrix/plot/image/multi_panel/other). crop 이미지 URI → `crop_s3_uri`
5. 설명문: Gemini에는 **crop 이미지 + 관련 이론 문장 2~5개만** 보낸다(페이지 전체 전송 안 함). 검출이 애매한 페이지만 Gemini에 영역 좌표 보조 요청
6. 시범 구간: 3과목 224~230쪽을 먼저 돌려 검수 보고서로 확인한 뒤 전체로 확장

### 품질 검수 도구 (설계, 2026-09-30)
- 1단계: 정적 HTML 보고서(스크립트로 생성, `data/reports/` 아래, gitignore). 페이지마다
  - 원본(또는 보정본) 이미지 위에 crop 영역·텍스트 영역 bbox를 색으로 구분해 그림
  - 옆에 crop 이미지 / 추출 텍스트 / 설명문을 나란히 배치, 검출 신뢰도·review_reasons 표시
  - 교재 이미지가 들어가므로 외부 공유 금지(개인 확인용)
- 2단계: 관리 화면(C)의 검수 탭으로 확장. 대상 목록은 `v_review_queue`(pages 중 review_required 또는 quality_passed=false) + needs_review인 theory_chunks/visual_assets. 승인/수정 시 needs_review를 풀고 재임베딩

### 시각자료 표시 원칙 (D-015)
- 화면에서는 그래프를 다시 그리지 않는다. 근거가 시각자료이면 **원본 crop 이미지 + 설명문**을 보여준다(`reconstructability` 등 구조 JSONB는 검색·설명용).

## 질의 흐름
1. 입력: 질문 텍스트 또는 문제 이미지(비전 LLM으로 문제문·보기·수식 추출). 문제 속 그래프·표는 비전 LLM이 텍스트(축, 추세, 수치, 보기와의 관계)로 풀어내고, 이후 검색·판정은 이 텍스트로 한다(Jev는 이미지 입력 불가)
2. 검색: 선택 과목 범위에서 후보 N개(벡터 + 키워드) → 리랭커 → 상위 K개(아래 "검색 단계 상세"). 이론 → 연결된 시각자료·같은 페이지 표/수식 확장
3. 답변 가능 판정(판정기): 근거로 답할 수 없으면 LLM 호출 없이 "자료에서 확인 불가"
4. 답변 생성: 기본 시험모드 + 선택한 제약 프리셋, 근거 번호 인용 강제
5. 근거 일치 판정(판정기): 낮으면 강한 모델 재생성 또는 "확신 낮음" 표시
6. 저장: mingyu_app 상세 + query_logs 요약
7. "자료에서 확인 불가"이면 이론 보충 입력으로 연결(아래 "이론 보충·수정")

### 검색 단계 상세 (설계, 후보·미검증, 2026-09-30)
- 현재 구현: 벡터 검색만(`app/retrieval/search.py`, v_searchable_theory, cosine, `SEARCH_TOP_K`).
- 목표 구조: 벡터(+키워드) 후보 **N개** → 리랭커 → 상위 **K개**. N, K, 리랭커 모델 이름은 `.env` 설정값(이름 예: `SEARCH_CANDIDATE_N`, `SEARCH_TOP_K`, `RERANKER_MODEL`(비우면 리랭커 생략), `RERANKER_MAX_LENGTH`).
- 리랭커 후보: `BAAI/bge-reranker-v2-m3`, `dragonkue/bge-reranker-v2-m3-ko`(한국어 미세조정, Apache-2.0로 알려짐). `max_length` 1024 권장.
- 임베딩 대안 후보: `dragonkue/BGE-m3-ko` — 차원이 1024인지 확인 필요. 같으면 `EMBEDDING_MODEL` 교체 + 재임베딩만으로 비교 가능(DB 컬럼 vector(1024)는 그대로).
- 키워드 검색 보강 후보: Kiwi(kiwipiepy) 형태소 기반, 또는 BGE-M3 sparse(lexical) 출력. 현재 인덱스인 trgm(clean_text)과 비교.
- 위 후보는 **모두 미검증**이다. 채택·버전·라이선스·차원은 해당 구현 세션에서 공식 자료(모델 카드, PyPI)로 확인한 뒤 DECISIONS에 기록한다. 비교는 아래 "검색 평가"의 같은 질문 세트로 한다.

### 검색 평가 (설계, 2026-09-30)
- 질문 세트 파일: `data/eval/questions.csv` (data/는 gitignore, 커밋 안 함). 질문은 사용자가 20~30개 작성.
  - 형식: UTF-8 CSV(엑셀은 "CSV UTF-8"로 저장), 머리행 `id,question,subject,pages,note`
    - `subject`: 정답 과목(page_map key `subject1`~`subject3`)
    - `pages`: 정답 인쇄 쪽번호, 여러 개는 `|`로 구분(예: `18|19`). **비워 두면 "자료에 없는 질문"**(확인 불가 임계값 평가용)
    - `note`: 메모(선택)
  - 예: `q01,DIKW 피라미드에서 지혜란?,subject1,18,`
- 평가 스크립트(구현 예정): 질문마다 검색 → 상위 K개 청크 중 정답 과목 book의 정답 쪽 청크가 있으면 적중.
  - hit@1 / hit@3 / hit@K(과목별·전체), 정답 청크 순위
  - "확인 불가" 임계값 후보별(예: 1위 점수 0.40~0.60): 답할 수 있는 질문 중 통과 비율, 자료에 없는 질문 중 차단 비율
  - 결과는 `data/reports/eval/`에 저장하고, 설정(임베딩 모델·리랭커·키워드 검색·N/K) + 요약 수치를 PROGRESS "자체 평가 메모"에 기록
- 임베딩 모델·리랭커·키워드 검색을 바꿀 때마다 같은 세트로 다시 돌려 비교한다.

## 판정기 (교체 가능 모듈)
- 인터페이스: `can_answer`(근거로 답 가능?), `classify`(단원·유형 선택), `choose`(객관식 후보), `verify`(답이 근거와 일치?)
  - 오답노트용 추가(설계): `reason_match`(내 이유가 근거와 일치?, 예/아니오 + 신뢰도), `error_type`(틀린 유형 선택: concept_confusion / misread / calculation / memorization)
- 구현체: `jev_typesafe`, `jev_cloudflare`, `llm`(Gemini 구조화 출력), `none`(판정 생략)
- `JUDGE_PROVIDER`로 선택. 신뢰도 임계값은 제공자별로 따로 둔다.
- `none`일 때 오답노트는 LLM 설명만 저장하고 틀린 유형은 LLM 구조화 출력 값(또는 비워 둠)을 쓴다. 판정 없이도 흐름은 끝까지 간다.
- `mingyu_app.judgments.question_key` CHECK는 현재 4개 값 → 오답노트 구현 시 새 마이그레이션으로 `reason_match`, `error_type` 추가(내 스키마이므로 제약 교체 가능)

## 오답노트 (설계, 2026-09-30, D-017 — 마이그레이션은 구현 세션에서)
### 흐름
1. 입력: 문제(텍스트 또는 사진) + **내 답** + **내 이유**(자유 서술)
2. 문제 추출(사진이면 비전 LLM, 그래프 포함 시 텍스트화) → 근거 검색 → 정답 풀이(기존 질의 흐름, 근거 인용)
3. 비교: 내 이유 ↔ 근거 문장. `reason_match` 판정 + LLM이 "어느 근거 문장과 어긋나는지"를 근거 번호로 설명
4. 틀린 유형 분류(`error_type`): 개념 혼동 / 문제 오독 / 계산 실수 / 암기 부족
   - 개념 혼동이면 근거 청크의 `confusable_concepts`(theory_chunks JSONB)와 `concept_relations`(relation_type='compare')에서 헷갈린 상대 개념을 찾아 함께 보여준다
5. 오답노트 저장
6. 재질문: 같은 개념(concept_id / 근거 청크)으로 새 문제를 LLM이 생성(근거 청크만 사용) → 풀면 결과를 시도 기록에 남긴다
- 내 답이 정답이어도 이유가 근거와 어긋나면 "정답이지만 이유 불일치"로 기록한다.

### mingyu_app 테이블 (초안)
- `wrong_notes`: id, problem_id(→ problems), solution_id(→ solutions, SET NULL), subject, my_answer, my_reason, correct_answer, is_correct, reason_match(boolean NULL), reason_match_confidence, error_type(CHECK concept_confusion/misread/calculation/memorization, NULL 허용), mismatch_explanation(어디서 틀렸는지), confused_with(JSONB: 개념 이름·concept_id 목록), concept_ids(JSONB 또는 uuid[]), status(CHECK open/reviewing/resolved), created_at, updated_at
- `wrong_note_evidence`: wrong_note_id, source_kind(theory/visual/table/formula), source_id, role(CHECK correct_basis/my_reason_conflict), quoted_text(스냅샷)
  - solution_evidence와 겹치면 solution_evidence 참조만 하고 이 테이블은 role 표시용으로만 쓸지 구현 시 결정
- `wrong_note_attempts`: wrong_note_id, question_text(재질문 문제), generated_from(JSONB: 근거 청크 id), my_answer, is_correct, created_at
- 판정 기록은 기존 `judgments`(question_key 추가)에 남기고 wrong_note_id로 연결(컬럼 추가)
- 팀 규격 테이블은 변경하지 않는다.

## 이론 보충·수정 (설계, 2026-09-30 — 마이그레이션·세부 결정은 구현 세션에서)
### 보충: 자료에 없는 내용 추가
1. 트리거: 답변이 "자료에서 확인 불가"일 때 화면에서 **텍스트 입력** 또는 **사진 업로드**로 보충(관리 화면에서 직접 추가도 가능).
2. 저장: 과목별 "사용자 보충" book(과목당 1개, 없으면 생성, `material_type=user_supplement`)에 page 1행 추가.
   - 텍스트: 입력을 저장소에 `books/{book_id}/{page_id}.txt`(UTF-8)로 저장해 `source_s3_uri`(NOT NULL)를 채운다. extract_text 결과는 `.text.json`에 `engine="user_text"`로 **입력 그대로**(교정 없음).
   - 사진: 기존 업로드 경로와 같다(인쇄체 PaddleOCR, 손필기는 비전 LLM).
3. 처리: extract_text → chunk_theory → embed를 **요청 안에서 동기 처리**(보충은 보통 1쪽). detect_visuals는 건너뛰고 skipped 기록(D-019).
   - 보충 page는 서로 독립이므로 앞 페이지 제목 경로를 이어받지 않게 하는 옵션이 필요(구현 시 결정). embedding_text 앞에 원래 질문이나 사용자가 붙인 제목을 넣는 방안 검토.
4. 원래 질문을 다시 실행해 보충 청크가 근거로 잡히는지 보여준다.
- DB: `books.material_type` CHECK(001에서 추가한 내 컬럼, 현재 textbook/lecture_note/personal_note)에 `user_supplement` 추가는 구현 세션에서 새 마이그레이션으로(사용자 확인 후).

### 수정: 교재 청크의 오류 정정
- `raw_text` 원문은 **덮어쓰지 않는다**(팀 규격 주석 "교재 원문 그대로. 일반지식으로 자동 교정 금지").
- `mingyu_app.chunk_corrections`(초안): id, original_chunk_id(원본 청크), corrected_text(수정 텍스트), reason(사유), is_active(활성), corrected_chunk_id(새로 만든 청크), created_at, updated_at. 재청킹에 대비해 원본 page_id·raw_text 스냅샷·line_range도 남긴다.
- 적용: 수정 텍스트로 **보충 book에 새 page·청크를 만들어 연결**(원본 페이지·쪽번호는 page_metadata에 기록)하고, 원본 청크는 `embedding_enabled=false` → v_searchable_theory에서 빠진다.
- 되돌리기 = 원복: is_active=false, 수정 청크 embedding_enabled=false(또는 삭제), 원본 청크 embedding_enabled=true.
- 주의: `run_stages` 재청킹은 페이지 청크를 지우고 다시 만들어 청크 id가 바뀐다 → 활성 수정이 있는 페이지는 재청킹 후 스냅샷으로 새 청크를 찾아 다시 연결하고 embedding_enabled=false를 재적용해야 한다(구현 시 방식 결정).

### 출처 표시와 관리
- 답변 근거마다 **출처 유형**을 표시한다: 교재 / 사용자 보충 / 수정본. solution_evidence 스냅샷에 출처 유형을 남기는 방식(mingyu_app 컬럼 추가 등)은 구현 시 결정.
- **답변 피드백**(좋음/나쁨 + 메모)과 **보충·수정 목록(삭제·복구)**은 관리 화면 검수 탭에 포함한다.

## 화면 (React + Vite, 개인 프론트 — D-021)
- A. 자료 업로드: 과목 선택/생성, 자료 유형, 다중 업로드, 처리 상태
- B. 공부: 과목, 질문 또는 문제 사진, 제약 프리셋, 답변 + 근거 청크 + 출처(출처 유형: 교재/사용자 보충/수정본, 시각자료 근거는 원본 crop 이미지 + 설명문). "확인 불가"면 이론 보충 입력. 답변 피드백. 오답 입력(내 답·내 이유) 모드, 오답노트 목록·재질문
- C. 관리: 과목·자료 목록, 삭제/재임베딩, 사용 로그, 검수 탭(v_review_queue 기반 + needs_review 청크, 위 "품질 검수 도구" 2단계, 답변 피드백, 보충·수정 목록 삭제·복구)