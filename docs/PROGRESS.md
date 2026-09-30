# PROGRESS

## 현재 상태 (2026-09-30 전체 임베딩 확인·검색 평가 스크립트 세션 기준)
- 환경·문서: 저장소(E:\자료실\adsp-study-rag), 루트 uv 환경(Python 3.12), GitHub 원격(Yubeol/study-ai-solver, private, main), CLAUDE.md, docs, /start·/wrap 명령
  - uv 캐시는 사용자 환경변수 `UV_CACHE_DIR=E:\uv-cache`(C 여유 부족). 새 터미널부터 적용
- 외부 접근: Gemini 완료(LITE=gemini-3.5-flash-lite 확정, STRONG=gemini-3.7-flash 잠정, D-006). Jev 키는 사용자가 .env에 넣음(TYPESAFE_API_KEY, JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS — 코드에서는 아직 안 씀, 값 미확인). S3 미확인 → STORAGE_BACKEND=local
- DB: 마이그레이션 001, 002 적용 완료(DDL 변경 없음). **팀 교재 3권 반입 완료**: books 3행(subject=ADsP, source_name=`team_import:N과목.pdf`), pages 324행(1과목 50 / 2과목 64 / 3과목 210) 전부 EXTRACTED, processing_runs 3건(PARTIAL). 저장소 `data/storage/books/` 약 562MB
- 백엔드 (FastAPI, `cd backend; uv run uvicorn app.main:app --reload`, 문서는 /docs)
  - /health, /health/db, 과목/자료(`GET /subjects`, `POST /books`, `GET /books?subject=`, `GET /books/{id}`), 업로드(`POST /books/{id}/pages`), 상태(`GET /books/{id}/pages`, `GET /processing-runs/{run_id}`)
  - **extract_text 구현 완료(D-013)**: 인쇄체 → PaddleOCR(`app/ingestion/ocr.py`, PP-OCRv5_mobile_det + korean_PP-OCRv5_mobile_rec, CPU, oneDNN 끔). 결과 JSON은 저장소 `books/{book_id}/{page_id}.ocr.json`, 요약은 page_metadata.ocr. personal_note는 REVIEW_REQUIRED("손필기 추출 미구현")
  - **팀 교재 반입(D-014, D-018)**: `app/ingestion/team_import.py` (`--dry-run` 기본 / `--preview` / `--apply --subject`). 매핑은 `data/raw/adsp/page_map.json`, 텍스트는 저장소 `books/{book_id}/{page_id}.text.json`(engine=team_text, 원문 그대로), 요약은 page_metadata.text, 리포트는 `data/reports/team_import/`
  - **청킹 완료(D-019)**: `app/ingestion/chunking.py` + `stages.chunk_theory`. 팀 교재 324쪽 전부 VERIFIED(`pipeline.skipped=["detect_visuals"]`). theory_chunks 1과목 92 / 2과목 122 / 3과목 402(needs_review 11: R 출력·그림 조각), excluded_sections(exam_question, 원문 위치 포함) 24 / 21 / 42
  - **임베딩 완료(D-020)**: `app/ingestion/embedding.py`(BGE-M3, sentence-transformers 6.1.0, torch CPU, 정규화, 캐시 `E:\hf_models` 4.3GB) + `stages.embed`. **팀 교재 324쪽 전부 EMBEDDED**, v_searchable_theory 605행, 검색 대상인데 임베딩 없는 청크 0. 전체 실행 시간(processing_runs started_at~finished_at, 1과목에 모델 로딩 포함) 1과목 1분49초 / 2과목 2분35초 / 3과목 7분45초
  - 실행 진입점: `python -m app.ingestion.run_stages`(dry-run 기본, `--apply --subject`, `--stages chunk|embed|chunk,embed`, `--pages`). Ctrl+C 등으로 끊기면 run을 FAILED로 닫음(창 닫기·kill은 RUNNING으로 남을 수 있음). 검색 확인: `python -m app.retrieval.search "질문"`(v_searchable_theory)
  - **검색 평가 스크립트(D-022)**: `python -m app.retrieval.evaluate`(`--questions`, `--k`, `--check`). hit@1/3/K·MRR(과목별·전체) + 임계값별 통과·차단 → `data/reports/eval/`. 예시 6문항(`data/eval/questions.sample.csv`)으로 동작 확인, **실제 질문 세트(`data/eval/questions.csv`)는 사용자 작성 대기**
  - detect_visuals는 `StageNotImplemented` → 업로드 경로 기본 파이프라인은 여전히 **EXTRACTED에서 멈춤**
  - 모델 캐시: `OCR_MODEL_DIR=E:\paddle_models` (현재 19MB, 쓰는 모델 2개만)
  - 속도(맑은 고딕으로 만든 A4 30줄): 1장 약 16초, 평균 신뢰도 0.994. **실제 교재 스캔으로는 아직 미측정**
- 테스트: `uv run pytest` 75개 통과(가짜 OCR·가짜 임베더, 청킹 규칙 10개, 실행 중단 1개, 평가 계산 6개 포함), `-m ocr_model` 1개, `-m embedding_model` 1개(실제 BGE-M3) 통과
- 프론트엔드: 미생성
- 문서: 설계 보완(오답노트·검수 도구·시각자료 표시 원칙·팀 교재 반입·crop 계획, D-014~D-017). 사용자용 문서 `docs/sessions/`(세션별 설명), `docs/MODIFY_GUIDE.md`(수정 위치 표) — 세션 시작 시 읽지 않음
- 팀 방향(D-021): 공용 프론트 없이 각자 개인 프로젝트. 팀 규격 테이블 "기존 컬럼 변경 금지·추가만" 유지, mingyu_app·API는 자유
- 규칙 추가(CLAUDE.md): 조정 가능한 값은 `.env`/`config.py` 한 곳, LLM 프롬프트는 `backend/app/prompts/` 텍스트 파일. /wrap은 세션 설명 파일까지 작성

## 다음 작업 (2026-09-30 방향 조정: 텍스트 end-to-end 우선)
설계는 ARCHITECTURE의 "질의 흐름"(검색 단계 상세, 검색 평가), "이론 보충·수정", "팀 교재 반입 경로", "시각자료 crop 파이프라인", "품질 검수 도구", "오답노트" 절과 D-014~D-021 참고.
1. **[다음 세션] 검색 평가 실행** (스크립트 `backend/app/retrieval/evaluate.py`, 기준은 D-022, 결과 `data/reports/eval/`)
   - (사용자) `data/eval/questions.csv` 작성: 20~30개, 과목별 고르게, 자료에 없는 질문 몇 개 포함(ADsP와 가까운 주제도 넣기 — 예시에서 "트랜스포머 셀프 어텐션"이 0.524로 교재 질문 DIKW(0.515)보다 높았음). 형식 검사 `cd backend; uv run python -m app.retrieval.evaluate --check`
   - 평가 실행 → 결과를 아래 "자체 평가 메모"에 기록, 틀린 질문은 리포트 json의 `top`으로 원인 확인(청킹 문제인지, 질문 표현 문제인지)
   - 점수 하나로 확인 불가를 가르기 어려우면 2번의 답변 가능 판정(can_answer)·리랭커로 넘기는 것을 전제로 임계값은 느슨하게 잡는다
   - 필요하면 청킹 규칙 보완(2과목 101쪽 첫 줄 기출 조각 등, D-019 알려진 한계)
2. 질의 흐름 + 판정(Jev) + 리랭커 비교
   - 검색 → 답변 가능 판정 → 답변 생성(근거 인용) → 근거 일치 판정, `JUDGE_PROVIDER=none`에서도 끝까지 동작
   - Jev 키는 받았으나 **어느 경로(TypeSafe 직접 / Cloudflare) 키인지 확인 필요**. 새 키 이름(JEV_ENABLED, JEV_MODEL, JEV_TIMEOUT_SECONDS)을 config에 반영, 모델 이름은 공식 문서로 확인(추측 금지), D-007 갱신
   - 리랭커·키워드 검색·임베딩 대안 후보(ARCHITECTURE "검색 단계 상세")를 공식 자료로 확인 후 같은 평가 세트로 비교
3. 이론 보충·수정 (ARCHITECTURE "이론 보충·수정", material_type user_supplement·mingyu_app.chunk_corrections 마이그레이션은 사용자 확인 후)
4. 간단한 프론트로 실사용 (공부 화면 B 중심 + 검수 탭 최소: 답변 피드백, 보충·수정 목록)
5. 팀 텍스트 품질 비교: 몇 쪽(1과목 14쪽, 3과목 226쪽 등)을 팀 텍스트 / PaddleOCR mobile / Gemini 비전으로 뽑아 원본 이미지와 비교(정확도·누락·표/수식 처리, 속도·비용). 기존 "PaddleOCR 실제 교재 품질 측정"을 대체
6. crop / 시각자료: 검수 HTML 보고서 + 3과목 crop 시범(224~230쪽, D-016, 레이아웃 모델 Windows+CPU 지원 여부 공식 문서 확인부터) → 그래프 포함 문제 10개로 추출 정확도 확인(D-015) → crop 전체 확장 + 설명문 생성(Gemini, 재시도·폴백 D-010)
7. 오답노트 (D-017, mingyu_app 마이그레이션은 사용자 확인 후)
8. 손필기(personal_note) 비전 LLM 추출
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
- 검색 평가(hit@K, "확인 불가" 임계값): 2026-09-30 예시 6문항(답 가능 4, 자료 없음 2) 동작 확인용 — BGE-M3, 리랭커·키워드 없음, K=5: hit@1 3/4, hit@3·@5 4/4, 1위 점수 답 가능 0.515~0.794 / 자료 없음 0.338, 0.524(겹침). 표본이 작아 결론 아님, 실제 세트로 다시 기록. 형식: 날짜 / 설정(임베딩 모델, 리랭커, 키워드 검색, N/K) / 질문 수 / hit@1·3·K / 임계값별 통과·차단

## 완료 기록
- 2026-09-29: 저장소 초기 구조, uv 환경, GitHub 연결, 운영 문서 5종, Gemini 모델 확인
- 2026-09-29: 기반 작업 — 마이그레이션 001/002 적용, FastAPI 골격, 설정 로딩, DB 연결, 스키마 고정 테스트
- 2026-09-29: 업로드·처리 파이프라인 뼈대 — books/업로드/상태 API, local 저장소, 단계별 상태 갱신 골격 (테스트 35개 통과, push 완료)
- 2026-09-29: 4-1 extract_text — PaddleOCR 설치(모델 캐시 E:, uv 캐시 E:), 인쇄체 OCR·결과 저장, 미구현 단계는 EXTRACTED에서 멈춤, 손필기 REVIEW_REQUIRED (테스트 43+1개 통과)
- 2026-09-30: 설계 문서 보완(코드 변경 없음) — 오답노트·품질 검수 도구·시각자료 표시 원칙, 팀 교재 데이터 반입 경로, 3과목 crop 계획, 다음 작업 순서 재정리 (D-014~D-017)
- 2026-09-30: 팀 교재 반입 — pypdfium2(BSD-3/Apache-2.0), page_map.json 매핑(3과목 216쪽 누락·252쪽 중복 촬영 확인), 58/59쪽 합본 텍스트 줄 분할, 3권 324페이지 EXTRACTED 반입 (D-018, 테스트 56개 통과)
- 2026-09-30: 사용자용 문서 — docs/sessions/00-overview.md(백엔드 개요), docs/MODIFY_GUIDE.md(수정 위치 표), CLAUDE.md 규칙 추가(조정 값은 .env/config.py, 프롬프트는 backend/app/prompts/), /wrap 명령 갱신(세션 설명 파일 작성)
- 2026-09-30: 청킹·임베딩 — chunk_theory(머리말/쪽번호 제외, 제목 경로 이어받기, exam_clues, 기출 문제 블록 제외, 짧은 비한글 조각 needs_review), run_stages 진입점, 팀 교재 324쪽 청킹(VERIFIED), BGE-M3 임베딩(sentence-transformers, E: 캐시) + 1과목 7쪽 시험 임베딩·검색 확인 (D-019, D-020, 테스트 68+2개)
- 2026-09-30: 설계 보완(코드 변경 없음) — 팀 방향 변경(D-021, 공용 프론트 없음), 이론 보충·수정 설계, 검색 단계 리랭커·키워드 후보(미검증), 검색 평가 세트 형식, 다음 작업 순서 재조정(텍스트 end-to-end 우선). 전체 임베딩은 세션 종료 시점 실행 중
- 2026-09-30: 전체 임베딩 완료 확인(324쪽 EMBEDDED, 검색 가능 605), 실행 중단 시 run FAILED로 닫기, 검색 평가 스크립트(hit@K·MRR·임계값별 통과/차단) + 예시 6문항 검증, /start에서 RUNNING run은 "실행 중일 수 있음"으로 보고 (테스트 75+2개)
