# PROGRESS

## 현재 상태 (2026-09-29)
- 1단계 완료: 저장소(E:\자료실\adsp-study-rag), 루트 uv 환경(Python 3.12 고정), .gitignore, GitHub 원격(Yubeol/study-ai-solver, private, main)
- 2단계 완료: .env / .env.example, CLAUDE.md, docs 4종
- 3단계 진행 중: 외부 접근 확인
  - Gemini: 완료. LITE=gemini-3.5-flash-lite 확정, STRONG=gemini-3.7-flash 잠정 (DECISIONS D-006)
  - Jev: 미확인
  - S3: 미확인 (팀원에게 문의 필요)
- 기반 작업 완료 (2026-09-29)
  - 마이그레이션 001(mingyu 보완: 컬럼/인덱스 추가만), 002(mingyu_app 스키마 + 테이블 6개) 공유 DB에 적용 완료, 재실행 시 변경 없음 확인
  - FastAPI 골격(/health, /health/db), .env 설정 로딩(pydantic-settings), psycopg 풀, scoped_transaction(SET LOCAL)
  - 테스트 18개 통과 (설정 검증, 스키마 존재, search_path 고정·원복, 마이그레이션 체크섬, API)
- 업로드·처리 파이프라인 뼈대 완료 (2026-09-29)
  - 과목/자료 API(`/subjects`, `/books`), 이미지 다중 업로드(`POST /books/{id}/pages`), 처리 상태 조회(`/books/{id}/pages`, `/processing-runs/{id}`)
  - 저장소 모듈(local 구현, s3 자리만), BackgroundTasks 파이프라인(단계별 상태 갱신, D-012). 단계 함수는 빈 함수
  - 테스트 35개 통과 (저장소·한글 경로, 업로드→EMBEDDED, 검증 실패 시 미저장, REVIEW_REQUIRED/PARTIAL, FAILED). 테스트가 만든 DB 행은 자동 삭제

## 다음 작업
1. Jev 확인 (사용자가 직접)
   - typesafe.ai 얼리 액세스 대기자 명단 신청
   - Cloudflare 무료 계정 + Workers AI 토큰 생성 → .env에 CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN
   - REST로 typesafe/jev 호출 테스트: POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run, body {"model":"typesafe/jev","input":{"state":..., "questions":{...}}}
   - 결과(성공/결제 필요 에러)를 DECISIONS D-007에 기록
2. S3: 팀 버킷 유무 문의. 없으면 STORAGE_BACKEND=local로 진행
3. ~~기반 작업~~ (완료)
4. 처리 단계 구현 (한 세션에 하나씩, `backend/app/ingestion/stages.py`)
   - 4-1. extract_text: 인쇄체 PaddleOCR → theory 원문 추출 (다음 세션)
   - 4-2. detect_visuals: 기울기 보정, 시각자료 crop, 표 구조화
   - 4-3. chunk_theory: 청킹(sort_order), 수식, 제외 영역, 품질 판정(NeedsReview)
   - 4-4. embed: 시각자료 설명문(Gemini) + BGE-M3 임베딩
5. 재처리 API (FAILED/REVIEW_REQUIRED/중단된 페이지 다시 돌리기), 자료 삭제 시 저장 파일 정리

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
- 2026-09-29: 업로드·처리 파이프라인 뼈대 — books/업로드/상태 API, local 저장소, 단계별 상태 갱신 골격
