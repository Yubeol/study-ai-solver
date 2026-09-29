# PROGRESS

## 현재 상태 (2026-09-29 세션 종료 기준)
- 환경·문서: 저장소(E:\자료실dsp-study-rag), 루트 uv 환경(Python 3.12), GitHub 원격(Yubeol/study-ai-solver, private, main), CLAUDE.md, docs, /start·/wrap 명령
- 외부 접근: Gemini 완료(LITE=gemini-3.5-flash-lite 확정, STRONG=gemini-3.7-flash 잠정, D-006). Jev는 사용자가 나중에 직접 확인. S3 미확인 → 당분간 STORAGE_BACKEND=local
- DB: 마이그레이션 001(mingyu 보완), 002(mingyu_app 6개 테이블) 적용 완료. 이번 세션에서 DDL 변경 없음
- 백엔드 (FastAPI, `cd backend; uv run uvicorn app.main:app --reload`, 문서는 /docs)
  - /health, /health/db
  - 과목/자료: `GET /subjects`, `POST /books`, `GET /books?subject=`, `GET /books/{id}`
  - 업로드: `POST /books/{id}/pages` (multipart `files`, PNG/JPEG/WEBP, 장당 MAX_UPLOAD_MB) → 202 {run_id, pages}
  - 상태: `GET /books/{id}/pages`, `GET /processing-runs/{run_id}`
  - 저장소 모듈(`app/storage`, local 구현, s3는 NotImplementedError), 파이프라인(`app/ingestion/pipeline.py`, 상태 매핑 D-012)
  - **처리 단계 4개(`app/ingestion/stages.py`)는 모두 빈 함수** → 지금은 업로드하면 페이지가 바로 EMBEDDED로 표시됨(실제 처리 없음)
- 테스트: `uv run pytest` 35개 통과(DB 테스트는 테스트 데이터 자동 삭제, 접속 불가 시 skip). 공유 DB의 mingyu books/pages/processing_runs는 현재 0행
- 프론트엔드: 미생성

## 다음 작업
1. **[다음 세션] 4-1. extract_text 구현 — 인쇄체(textbook/lecture_note) PaddleOCR**
   - 할 일
     1. PaddleOCR 설치 가능 여부를 공식 문서로 확인(Windows + Python 3.12 + CPU, 한국어 모델). 버전·설치 명령·확인 날짜·출처 URL을 DECISIONS에 기록 후 `uv add`. 추측 금지
     2. `stages.extract_text(ctx)`: `ctx.read_source()` 바이트 → `np.frombuffer` + `cv2.imdecode`(cv2.imread 금지) → OCR → 줄 단위 결과(text, bbox, confidence)
     3. OCR 결과 저장 위치 결정: 추천은 저장소 JSON(`books/{book_id}/{page_id}.ocr.json`, `ctx.storage.save`) + page_metadata에는 요약(줄 수, 평균 신뢰도, 엔진·버전)만. theory_chunks는 clean_text·embedding_text가 NOT NULL이라 4-3 청킹 단계에서 만든다
     4. 자료 유형 분기: 책의 material_type이 personal_note면 이번에는 NotImplemented 대신 NeedsReview("손필기 추출 미구현")로 처리(D-008, 비전 LLM은 별도 세션)
     5. OCR 모델은 프로세스당 1회 로드(지연 로딩 + 캐시). 모델 경로/언어 등은 .env 설정값으로
   - 관련 파일: `backend/app/ingestion/stages.py`, `pipeline.py`, `app/storage/`, `app/core/config.py`, `.env.example`, `backend/tests/test_ingestion_api.py`(가짜 단계 주입 방식 참고)
   - 주의
     - raw_text는 교재 원문 그대로. OCR 결과를 일반 지식으로 교정하지 않는다
     - 교재 이미지는 `data/`에만 둔다. 테스트용 이미지는 코드로 생성(Pillow로 글자 그리기)하고 저장소에 커밋하지 않는다
     - OCR 실제 모델 테스트는 느리므로 mark를 달아 기본 테스트와 분리 검토
     - BackgroundTasks는 스레드풀에서 돌므로 OCR 객체의 스레드 안전성 확인
2. 4-2. detect_visuals: 기울기 보정, 시각자료 crop(visual_assets.crop_s3_uri NOT NULL → 저장소 URI), 세트 그림, 표 구조화
3. 4-3. chunk_theory: 청킹(sort_order), 수식, 제외 영역(excluded_sections), 품질 판정(`NeedsReview`) → theory_chunks 적재
4. 4-4. embed: 시각자료 설명문(Gemini, 재시도·폴백 D-010) + BGE-M3 임베딩
5. 재처리 API(FAILED/REVIEW_REQUIRED/서버 재시작으로 중단된 페이지), 자료 삭제 시 저장 파일 정리
6. (사용자) Jev 확인: Cloudflare Workers AI 토큰 → typesafe/jev REST 호출 테스트 → D-007에 기록
7. (사용자) S3: 팀 버킷 유무 문의

## 막힌 것 / 확인 필요
- S3 사용 가능 여부 미확인 (pages.source_s3_uri, visual_assets.crop_s3_uri가 NOT NULL)
- Jev Cloudflare 경로의 무료 할당량 적용 여부 미확인
- gemini-3.7-flash는 503(일시적 과부하)만 확인, 정상 응답은 아직 못 받음
- 서버 재시작 시 진행 중이던 BackgroundTasks는 사라진다(페이지가 중간 상태로 남음) → 5번 재처리 API로 보완
- 테스트 시 경고: starlette TestClient가 httpx 대신 httpx2 사용을 권고(동작 문제 없음, 추후 교체 검토)

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
