# PROGRESS

## 현재 상태 (2026-09-29 세션 종료 기준)
- 환경·문서: 저장소(E:\자료실\adsp-study-rag), 루트 uv 환경(Python 3.12), GitHub 원격(Yubeol/study-ai-solver, private, main), CLAUDE.md, docs, /start·/wrap 명령
  - uv 캐시는 사용자 환경변수 `UV_CACHE_DIR=E:\uv-cache`(C 여유 부족). 새 터미널부터 적용
- 외부 접근: Gemini 완료(LITE=gemini-3.5-flash-lite 확정, STRONG=gemini-3.7-flash 잠정, D-006). Jev 키는 사용자가 .env에 넣음(TYPESAFE_API_KEY, JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS — 코드에서는 아직 안 씀, 값 미확인). S3 미확인 → STORAGE_BACKEND=local
- DB: 마이그레이션 001, 002 적용 완료. 이번 세션 DDL 변경 없음
- 백엔드 (FastAPI, `cd backend; uv run uvicorn app.main:app --reload`, 문서는 /docs)
  - /health, /health/db, 과목/자료(`GET /subjects`, `POST /books`, `GET /books?subject=`, `GET /books/{id}`), 업로드(`POST /books/{id}/pages`), 상태(`GET /books/{id}/pages`, `GET /processing-runs/{run_id}`)
  - **extract_text 구현 완료(D-013)**: 인쇄체 → PaddleOCR(`app/ingestion/ocr.py`, PP-OCRv5_mobile_det + korean_PP-OCRv5_mobile_rec, CPU, oneDNN 끔). 결과 JSON은 저장소 `books/{book_id}/{page_id}.ocr.json`, 요약은 page_metadata.ocr. personal_note는 REVIEW_REQUIRED("손필기 추출 미구현")
  - 나머지 3단계(detect_visuals, chunk_theory, embed)는 `StageNotImplemented` → 업로드하면 페이지는 **EXTRACTED에서 멈추고** run은 PARTIAL
  - 모델 캐시: `OCR_MODEL_DIR=E:\paddle_models` (현재 19MB, 쓰는 모델 2개만)
  - 속도(맑은 고딕으로 만든 A4 30줄): 1장 약 16초, 평균 신뢰도 0.994. **실제 교재 스캔으로는 아직 미측정**
- 테스트: `uv run pytest` 43개 통과(가짜 OCR 엔진), `uv run pytest -m ocr_model` 1개 통과(실제 모델, 맑은 고딕 없으면 skip)
- 프론트엔드: 미생성

## 다음 작업
1. **[다음 세션] 실제 교재로 OCR 확인 → 4-2. detect_visuals**
   - 0) 먼저 실제 교재 스캔 2~3장(`data/`에 둔 것)을 업로드해서 OCR 품질·속도 확인
      - 서버 실행 후 `POST /books`(material_type=textbook) → `POST /books/{id}/pages` → `GET /processing-runs/{run_id}` → 저장소 `data/storage/books/{book_id}/{page_id}.ocr.json` 확인
      - 확인할 것: 줄 누락, 표·그림 안 글자, 수식, 페이지당 시간. 결과를 DECISIONS D-013 실측에 추가
      - 품질이 많이 나쁘면 4-2로 가지 말고 사용자와 Gemini 추출 전환 여부를 먼저 정한다
   - 4-2 할 일
     1. 기울기 보정: OCR bbox 또는 OpenCV(Hough/minAreaRect)로 각도 추정. 원본 바이트는 바꾸지 않고, 보정 결과가 필요하면 별도 저장
     2. 시각자료 영역 검출·crop: 그림/표/도식 영역을 찾아 `ctx.storage.save("books/{book_id}/{page_id}/visual_{n}.png", ...)` → URI를 visual_assets.crop_s3_uri(NOT NULL)에. visual_type CHECK 값은 DB에서 먼저 확인
     3. 세트 그림 묶기(visual_groups), 표 구조화(visual_tables)는 범위가 크면 이번에는 crop까지만 하고 나머지는 다음으로 미룬다(사용자와 범위 확정)
     4. OCR 줄 중 시각자료 영역 안에 있는 줄 표시(4-3 청킹에서 본문과 분리하기 위함) → ocr.json 또는 page_metadata에 기록
   - 관련 파일: `backend/app/ingestion/stages.py`(detect_visuals), `images.py`(decode_bgr), `ocr.py`(OcrLine bbox), `pipeline.py`(detect_visuals 뒤 chunk_theory가 VERIFIED를 설정), `app/storage/`, `backend/tests/test_ingestion_api.py`(_FakeEngine, NOOP_STAGES)
   - 주의
     - 시각자료 테이블 적재 시 processing_run_id(001에서 추가)도 채운다. 기존 컬럼 변경 금지, 필요하면 컬럼 추가만(마이그레이션 → 사용자 확인)
     - OpenCV 파일 입출력은 imdecode/imencode만(한글 경로)
     - 테스트 이미지는 코드로 생성(Pillow 도형 + 맑은 고딕), 교재 이미지는 커밋 금지
     - detect_visuals를 구현하면 페이지는 chunk_theory(미구현)에서 멈추므로 상태는 여전히 EXTRACTED — 테스트 기대값 확인
2. 4-3. chunk_theory: 청킹(sort_order), 수식, 제외 영역(excluded_sections), 품질 판정(`NeedsReview`) → theory_chunks 적재(raw_text는 OCR 원문 그대로)
3. 4-4. embed: 시각자료 설명문(Gemini, 재시도·폴백 D-010) + BGE-M3 임베딩
4. 재처리 API(FAILED/REVIEW_REQUIRED/미구현 단계에서 멈춘 페이지/서버 재시작으로 중단된 페이지), 자료 삭제 시 저장 파일(원본, ocr.json, crop) 정리
5. 손필기(personal_note) 비전 LLM 추출 (D-008)
6. Jev 연동: .env에 키 들어옴 → 새 키 이름(JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS)을 config에 반영, REST 호출 테스트, D-007 갱신. 모델 이름은 공식 문서로 확인(추측 금지)
7. (사용자) S3: 팀 버킷 유무 문의

## 막힌 것 / 확인 필요
- S3 사용 가능 여부 미확인 (pages.source_s3_uri, visual_assets.crop_s3_uri가 NOT NULL)
- Jev Cloudflare 경로의 무료 할당량 적용 여부 미확인
- gemini-3.7-flash는 503(일시적 과부하)만 확인, 정상 응답은 아직 못 받음
- 서버 재시작 시 진행 중이던 BackgroundTasks는 사라진다(페이지가 중간 상태로 남음) → 다음 작업 4번 재처리 API로 보완
- 테스트 시 경고: starlette TestClient가 httpx 대신 httpx2 사용을 권고(동작 문제 없음, 추후 교체 검토)
- paddlepaddle 3.3.x oneDNN 버그로 enable_mkldnn=False(속도 손해). Paddle 업데이트 시 재확인(D-013)
- processing_runs.paddle_model 컬럼은 아직 채우지 않음(모델 정보는 page_metadata.ocr에 있음)

## 참고: 로컬 확인 방법 (Windows PowerShell)
- Gemini 호출 테스트는 헤더에 Content-Type을 넣지 말고 -ContentType 옵션을 쓴다 (PowerShell 5.1 이슈).
- 모델 목록에 보여도 호출이 막힐 수 있으므로 실제 generateContent 호출로 판단한다.

## 일정
- 1주차 (09-29 ~ 10-04): 기반 + 업로드/처리 파이프라인(텍스트, 시각자료, 임베딩) + 검색 품질 확인
- 2주차 (10-05 ~ 10-11): 질의 흐름(판정, 제약 프리셋, 근거 표시) + 문제 사진 입력 + 화면 3개 + 실사용
- 여유분 (10-12 ~ 10-15)

## 자체 평가 메모 (과제 성공 기준용, 실사용하며 기록)
- 실용성:
- 효율성:
- 미비점:
- 단점:

## 완료 기록
- 2026-09-29: 저장소 초기 구조, uv 환경, GitHub 연결, 운영 문서 5종, Gemini 모델 확인
- 2026-09-29: 기반 작업 — 마이그레이션 001/002 적용, FastAPI 골격, 설정 로딩, DB 연결, 스키마 고정 테스트
- 2026-09-29: 업로드·처리 파이프라인 뼈대 — books/업로드/상태 API, local 저장소, 단계별 상태 갱신 골격 (테스트 35개 통과, push 완료)
- 2026-09-29: 4-1 extract_text — PaddleOCR 설치(모델 캐시 E:, uv 캐시 E:), 인쇄체 OCR·결과 저장, 미구현 단계는 EXTRACTED에서 멈춤, 손필기 REVIEW_REQUIRED (테스트 43+1개 통과)
