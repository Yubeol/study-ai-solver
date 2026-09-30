# PROGRESS

## 현재 상태 (2026-09-30 세션 종료 기준, 이번 세션은 docs만 변경)
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
- 문서: 설계 보완(오답노트·검수 도구·시각자료 표시 원칙·팀 교재 반입·crop 계획, D-014~D-017). 사용자용 문서 `docs/sessions/`(세션별 설명), `docs/MODIFY_GUIDE.md`(수정 위치 표) — 세션 시작 시 읽지 않음
- 규칙 추가(CLAUDE.md): 조정 가능한 값은 `.env`/`config.py` 한 곳, LLM 프롬프트는 `backend/app/prompts/` 텍스트 파일. /wrap은 세션 설명 파일까지 작성

## 다음 작업 (2026-09-30 재정리)
설계는 ARCHITECTURE의 "팀 교재 반입 경로", "시각자료 crop 파이프라인", "품질 검수 도구", "오답노트" 절과 D-014~D-017 참고.
1. **[다음 세션] 팀 교재 데이터 반입** (D-014)
   - 파일명 정리: `pdf/1과목.pdf`→`subject1.pdf` 등, `team_text/과1~과3`→`subject1~3/`, 깨진 텍스트 파일명에서 인쇄 페이지 번호 추출
   - PDF 장 ↔ 인쇄 페이지 매핑 실제 확인(1·3과목은 PDF가 1장 많음, 3과목 94~96장 = 226~228쪽). 매핑 파일을 만들어 사용자에게 보여준다
   - books/pages 생성(printed_page_number, page_metadata.pdf_index), 팀 텍스트를 extract_text 결과로 저장(engine="team_text", 출처 파일명)
   - **DB 적재는 매핑·계획을 사용자에게 확인받은 뒤**
   - 현재 실제 파일: `data/raw/adsp/pdf/{1,2,3}과목.pdf`(120MB/104MB/370MB), `data/raw/adsp/team_text/과1`(49개), `과2`(64개), `과3`(210개). 원본은 지우지 말고 정리본을 따로 만든다
   - 권장 순서: ① 텍스트 파일명 → 쪽번호 목록 뽑아 빠진 쪽 확인(1과목·3과목 1개씩 부족) ② PDF 장별 저해상도 이미지로 쪽번호 대조 → `page_map.json` 초안 ③ 사용자 확인 ④ 페이지 이미지 렌더링·저장 + books/pages INSERT + 텍스트 결과 저장
   - 관련 파일: 반입 스크립트는 새로 작성(예: `backend/app/ingestion/team_import.py` + `python -m` 실행). 재사용할 것 — `repositories/books.create_book`, `repositories/pages.insert_pages`(printed_page_number는 현재 INSERT에 없음 → 함수 추가 필요), `repositories/runs.create_run/finish_run`, `storage.get_storage().save`, `stages.ocr_key` 형식 참고
   - 반입한 페이지 상태: 텍스트가 저장되면 EXTRACTED. 이후 단계는 기존 파이프라인(`pipeline.process_page`)에서 extract_text를 뺀 단계 목록으로 돌릴 수 있게 설계(chunk_theory 구현 전까지는 EXTRACTED에서 멈춤)
   - 주의: PDF 렌더링 라이브러리가 필요하면 공식 자료로 확인 후 `uv add`, DECISIONS에 기록. 교재 이미지·텍스트는 커밋 금지. 조정 값(렌더링 DPI 등)은 config에(CLAUDE.md 규칙). 깨진 파일명은 zip 인코딩(cp949 추정, 미확인) → 쪽번호 숫자만 뽑으면 되므로 복원은 필수 아님
2. 청킹 + 로컬 임베딩(BGE-M3) → 검색 동작 확인 (머리말/쪽번호 제외, 기출 표시 → exam_clues, raw_text 원문 그대로)
3. 검수 HTML 보고서 + 3과목 crop 시범(224~230쪽) (D-016, 레이아웃 모델 Windows+CPU 지원 여부 공식 문서 확인부터)
4. 그래프 포함 문제 10개로 추출 정확도 확인 (비전 LLM 텍스트화, D-015)
5. crop 전체 확장 + 시각자료 설명문 생성 (Gemini, 재시도·폴백 D-010)
6. 질의 흐름 + Jev 호출 테스트 — Jev 키는 받았으나 **어느 경로(TypeSafe 직접 / Cloudflare) 키인지 확인 필요**. 새 키 이름(JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS)을 config에 반영, 모델 이름은 공식 문서로 확인(추측 금지), D-007 갱신
7. 오답노트 구현 (D-017, mingyu_app 마이그레이션은 사용자 확인 후)
8. PaddleOCR(새 캡처용) 실제 교재 품질·속도 측정, 손필기(personal_note) 비전 LLM 추출
9. 프론트 화면 3개 + 검수 탭
- 틈틈이: 재처리 API(FAILED/REVIEW_REQUIRED/멈춘 페이지), 자료 삭제 시 저장 파일 정리, (사용자) S3 팀 버킷 유무 문의

## 막힌 것 / 확인 필요
- 팀 텍스트 파일 수가 표기 범위와 1개씩 어긋남: 1과목 14~63p(50쪽)인데 49개, 3과목 132~342p(211쪽)인데 210개 → 빠진 쪽이 있는지 반입 세션에서 확인
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
- 2026-09-30: 사용자용 문서 — docs/sessions/00-overview.md(백엔드 개요), docs/MODIFY_GUIDE.md(수정 위치 표), CLAUDE.md 규칙 추가(조정 값은 .env/config.py, 프롬프트는 backend/app/prompts/), /wrap 명령 갱신(세션 설명 파일 작성)
