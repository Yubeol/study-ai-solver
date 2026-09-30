# PROGRESS

## 현재 상태 (2026-09-30 청킹·임베딩 세션 기준)
- 환경·문서: 저장소(E:\자료실\adsp-study-rag), 루트 uv 환경(Python 3.12), GitHub 원격(Yubeol/study-ai-solver, private, main), CLAUDE.md, docs, /start·/wrap 명령
  - uv 캐시는 사용자 환경변수 `UV_CACHE_DIR=E:\uv-cache`(C 여유 부족). 새 터미널부터 적용
- 외부 접근: Gemini 완료(LITE=gemini-3.5-flash-lite 확정, STRONG=gemini-3.7-flash 잠정, D-006). Jev 키는 사용자가 .env에 넣음(TYPESAFE_API_KEY, JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS — 코드에서는 아직 안 씀, 값 미확인). S3 미확인 → STORAGE_BACKEND=local
- DB: 마이그레이션 001, 002 적용 완료(DDL 변경 없음). **팀 교재 3권 반입 완료**: books 3행(subject=ADsP, source_name=`team_import:N과목.pdf`), pages 324행(1과목 50 / 2과목 64 / 3과목 210) 전부 EXTRACTED, processing_runs 3건(PARTIAL). 저장소 `data/storage/books/` 약 562MB
- 백엔드 (FastAPI, `cd backend; uv run uvicorn app.main:app --reload`, 문서는 /docs)
  - /health, /health/db, 과목/자료(`GET /subjects`, `POST /books`, `GET /books?subject=`, `GET /books/{id}`), 업로드(`POST /books/{id}/pages`), 상태(`GET /books/{id}/pages`, `GET /processing-runs/{run_id}`)
  - **extract_text 구현 완료(D-013)**: 인쇄체 → PaddleOCR(`app/ingestion/ocr.py`, PP-OCRv5_mobile_det + korean_PP-OCRv5_mobile_rec, CPU, oneDNN 끔). 결과 JSON은 저장소 `books/{book_id}/{page_id}.ocr.json`, 요약은 page_metadata.ocr. personal_note는 REVIEW_REQUIRED("손필기 추출 미구현")
  - **팀 교재 반입(D-014, D-018)**: `app/ingestion/team_import.py` (`--dry-run` 기본 / `--preview` / `--apply --subject`). 매핑은 `data/raw/adsp/page_map.json`, 텍스트는 저장소 `books/{book_id}/{page_id}.text.json`(engine=team_text, 원문 그대로), 요약은 page_metadata.text, 리포트는 `data/reports/team_import/`
  - **청킹 완료(D-019)**: `app/ingestion/chunking.py` + `stages.chunk_theory`. 팀 교재 324쪽 전부 VERIFIED(`pipeline.skipped=["detect_visuals"]`). theory_chunks 1과목 92 / 2과목 122 / 3과목 402(needs_review 11: R 출력·그림 조각), excluded_sections(exam_question, 원문 위치 포함) 24 / 21 / 42
  - **임베딩 구현(D-020)**: `app/ingestion/embedding.py`(BGE-M3, sentence-transformers 6.1.0, torch CPU, 정규화, 캐시 `E:\hf_models` 4.3GB) + `stages.embed`. **시험으로 1과목 14~20쪽(7쪽)만 EMBEDDED**(36초, 모델 로딩 포함). 나머지 317쪽은 VERIFIED
  - 실행 진입점: `python -m app.ingestion.run_stages`(dry-run 기본, `--apply --subject`, `--stages chunk|embed|chunk,embed`, `--pages`). 검색 확인: `python -m app.retrieval.search "질문"`(v_searchable_theory)
  - detect_visuals는 `StageNotImplemented` → 업로드 경로 기본 파이프라인은 여전히 **EXTRACTED에서 멈춤**
  - 모델 캐시: `OCR_MODEL_DIR=E:\paddle_models` (현재 19MB, 쓰는 모델 2개만)
  - 속도(맑은 고딕으로 만든 A4 30줄): 1장 약 16초, 평균 신뢰도 0.994. **실제 교재 스캔으로는 아직 미측정**
- 테스트: `uv run pytest` 68개 통과(가짜 OCR·가짜 임베더, 청킹 규칙 10개 포함), `-m ocr_model` 1개, `-m embedding_model` 1개(실제 BGE-M3) 통과
- 프론트엔드: 미생성
- 문서: 설계 보완(오답노트·검수 도구·시각자료 표시 원칙·팀 교재 반입·crop 계획, D-014~D-017). 사용자용 문서 `docs/sessions/`(세션별 설명), `docs/MODIFY_GUIDE.md`(수정 위치 표) — 세션 시작 시 읽지 않음
- 규칙 추가(CLAUDE.md): 조정 가능한 값은 `.env`/`config.py` 한 곳, LLM 프롬프트는 `backend/app/prompts/` 텍스트 파일. /wrap은 세션 설명 파일까지 작성

## 다음 작업 (2026-09-30 청킹·임베딩 후 갱신)
설계는 ARCHITECTURE의 "팀 교재 반입 경로", "시각자료 crop 파이프라인", "품질 검수 도구", "오답노트" 절과 D-014~D-020 참고.
1. **[다음 세션] 전체 임베딩 실행 + 검색 품질 확인**
   - 사용자가 실행: `cd backend; uv run python -m app.ingestion.run_stages --apply --subject all --stages embed` (EMBEDDED 7쪽은 다시 덮어씀. 속도는 7쪽 36초 기준 전체 수 분~십수 분 예상, 실측 필요)
   - 질문 10~20개(과목별)로 `python -m app.retrieval.search` → 1위 적중 여부, 점수 분포 기록 → "자료에서 확인 불가" 임계값 후보(시험 7쪽: 관련 0.53~0.75, 없는 주제 최고 0.42)
   - 필요하면 하이브리드(clean_text trgm) 검토, 청킹 규칙 보완(2과목 101쪽 첫 줄 기출 조각 등, D-019 알려진 한계)
2. 검수 HTML 보고서 + 3과목 crop 시범(224~230쪽) (D-016, 레이아웃 모델 Windows+CPU 지원 여부 공식 문서 확인부터)
3. 그래프 포함 문제 10개로 추출 정확도 확인 (비전 LLM 텍스트화, D-015)
4. crop 전체 확장 + 시각자료 설명문 생성 (Gemini, 재시도·폴백 D-010)
5. 질의 흐름 + Jev 호출 테스트 — Jev 키는 받았으나 **어느 경로(TypeSafe 직접 / Cloudflare) 키인지 확인 필요**. 새 키 이름(JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS)을 config에 반영, 모델 이름은 공식 문서로 확인(추측 금지), D-007 갱신
6. 오답노트 구현 (D-017, mingyu_app 마이그레이션은 사용자 확인 후)
7. PaddleOCR(새 캡처용) 실제 교재 품질·속도 측정, 손필기(personal_note) 비전 LLM 추출
8. 프론트 화면 3개 + 검수 탭
- 틈틈이: 재처리 API(FAILED/REVIEW_REQUIRED/멈춘 페이지), 자료 삭제 시 저장 파일 정리, (사용자) S3 팀 버킷 유무 문의

## 막힌 것 / 확인 필요
- 3과목 216쪽은 원본 PDF·팀 텍스트 모두 없음(D-018). 필요하면 교재에서 직접 캡처해 업로드 경로로 추가
- 받은 Jev 키가 TypeSafe 직접 API용인지 Cloudflare Workers AI용인지 미확인
- 레이아웃 분석 모델(PaddleOCR 계열)의 Windows + CPU 동작 여부 미확인 (D-016)
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
- 2026-09-30: 설계 문서 보완(코드 변경 없음) — 오답노트·품질 검수 도구·시각자료 표시 원칙, 팀 교재 데이터 반입 경로, 3과목 crop 계획, 다음 작업 순서 재정리 (D-014~D-017)
- 2026-09-30: 팀 교재 반입 — pypdfium2(BSD-3/Apache-2.0), page_map.json 매핑(3과목 216쪽 누락·252쪽 중복 촬영 확인), 58/59쪽 합본 텍스트 줄 분할, 3권 324페이지 EXTRACTED 반입 (D-018, 테스트 56개 통과)
- 2026-09-30: 사용자용 문서 — docs/sessions/00-overview.md(백엔드 개요), docs/MODIFY_GUIDE.md(수정 위치 표), CLAUDE.md 규칙 추가(조정 값은 .env/config.py, 프롬프트는 backend/app/prompts/), /wrap 명령 갱신(세션 설명 파일 작성)
- 2026-09-30: 청킹·임베딩 — chunk_theory(머리말/쪽번호 제외, 제목 경로 이어받기, exam_clues, 기출 문제 블록 제외, 짧은 비한글 조각 needs_review), run_stages 진입점, 팀 교재 324쪽 청킹(VERIFIED), BGE-M3 임베딩(sentence-transformers, E: 캐시) + 1과목 7쪽 시험 임베딩·검색 확인 (D-019, D-020, 테스트 68+2개)
