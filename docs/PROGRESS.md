# PROGRESS

## 현재 상태 (2026-10-01 질의 흐름 + 청킹 보완 설계 세션 기준)
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
  - **검색 평가 스크립트(D-022)**: `python -m app.retrieval.evaluate`(`--questions`, `--k`, `--check`). hit@1/3/K·MRR(과목별·전체) + 임계값별 통과·차단 → `data/reports/eval/`. **실제 세트 33문항(`data/eval/questions.csv`)으로 평가 완료** — 결과는 아래 "자체 평가 메모". 실행하면 HTML 보고서(`app/retrieval/eval_report.py`, 질문별 정답 쪽·상위 K개 청크·페이지 썸네일, `data/reports/eval/{시각}.html` + `thumbs/`)도 자동 생성, 기존 json으로 다시 만들기 `python -m app.retrieval.eval_report [json]`
  - **리랭커(D-024)**: `app/retrieval/rerank.py`(sentence-transformers CrossEncoder, sigmoid 0~1). 채택 `BAAI/bge-reranker-v2-m3`, 벡터 후보 N=10, 입력 embedding_text, 캐시 `E:\hf_models`(bge-m3 + 리랭커 2개 = 8.51GB). `search.py`는 `RERANKER_MODEL`이 있으면 리랭크하고 "확인 불가" 2단계 판단 `is_answerable`(1단계 벡터 1위 ≥ 0.45, 2단계 리랭커 1위 ≥ 0.15, **33문항 기준 잠정값**). 평가는 `evaluate --reranker <모델|none> --n --rerank-input`. CPU에서 질문당 리랭크 평균 6.0초·최대 10.2초
  - **"확인 불가" 3구간(구현 2026-10-01)**: `is_answerable` → (reject/gray/answer, 이유). 벡터 하한 0.45, 리랭커 하한 `ANSWERABLE_MIN_RERANK_SCORE`=0.03, 상한 `ANSWERABLE_CONFIDENT_RERANK_SCORE`=0.15(33문항 기준 잠정값)
  - **질의 API `POST /qa`(D-025)**: `app/qa/service.py` — 검색(N=10 → 리랭크 → K=5) → 3구간 → Gemini JSON 답변(`app/llm/gemini.py`, generateContent + responseJsonSchema, 재시도·폴백) → 인용 번호 검증(범위 밖 제거·기록) → `query_logs`(metadata에 판정·단계별 시간). 프롬프트 `backend/app/prompts/answer_*`. LLM 입력은 clean_text+제목 경로+과목·쪽, 응답 근거는 raw_text. 서버 시작 시 임베딩·리랭커 로드+워밍업(약 1분, RSS 약 4.6GB). 판정기는 none만(`app/judge`). 샘플 실행 `python -m app.qa.sample_run --ids …`(최대 12개) → `data/reports/answers/`
  - 서버 메모리·시간(D-024 추가): 두 모델 동시 RSS 최대 4.66GB, 질문당 임베딩 0.1초·벡터 0.4초·리랭크 약 4초·LLM 약 1.7초 → 전체 약 6~7초. `RERANKER_MAX_LENGTH` 512는 1024와 결과·시간 같아 1024 유지
  - detect_visuals는 `StageNotImplemented` → 업로드 경로 기본 파이프라인은 여전히 **EXTRACTED에서 멈춤**
  - 모델 캐시: `OCR_MODEL_DIR=E:\paddle_models` (현재 19MB, 쓰는 모델 2개만)
  - 속도(맑은 고딕으로 만든 A4 30줄): 1장 약 16초, 평균 신뢰도 0.994. **실제 교재 스캔으로는 아직 미측정**
- 테스트: `uv run pytest` 95개 통과(가짜 OCR·가짜 임베더·가짜 리랭커·가짜 LLM, 청킹 규칙 10개, 실행 중단 1개, 평가 계산 6개, 평가 보고서 2개, 리랭크·3구간 6개, 질의 흐름·Gemini 재시도·query_logs·/qa 12개 포함), `-m ocr_model` 1개, `-m embedding_model` 1개(실제 BGE-M3), `-m reranker_model` 1개(실제 v2-m3) 통과
- 프론트엔드: 미생성
- 문서: 설계 보완(오답노트·검수 도구·시각자료 표시 원칙·팀 교재 반입·crop 계획, D-014~D-017). 사용자용 문서 `docs/sessions/`(세션별 설명), `docs/MODIFY_GUIDE.md`(수정 위치 표) — 세션 시작 시 읽지 않음. 팀 공유 문서 `docs/team/`(교재 원문·내 스키마·.env 값 없이 원리 + 독립 함수 예시): `paddleocr-windows-cpu.md`(검증 완료), `cross-page-code.md`(설계 초안, 검증 전)
- 팀 방향(D-021): 공용 프론트 없이 각자 개인 프로젝트. 팀 규격 테이블 "기존 컬럼 변경 금지·추가만" 유지, mingyu_app·API는 자유
- 규칙 추가(CLAUDE.md): 조정 가능한 값은 `.env`/`config.py` 한 곳, LLM 프롬프트는 `backend/app/prompts/` 텍스트 파일. /wrap은 세션 설명 파일까지 작성

## 다음 작업 (2026-09-30 방향 조정: 텍스트 end-to-end 우선)
설계는 ARCHITECTURE의 "질의 흐름"(검색 단계 상세, 검색 평가), "이론 보충·수정", "팀 교재 반입 경로", "시각자료 crop 파이프라인", "품질 검수 도구", "오답노트" 절과 D-014~D-021 참고.
- (완료 2026-09-30) 검색 평가 실행 — 결과·틀린 질문 분류는 "자체 평가 메모". 확인 불가 임계값은 **확정하지 않음**(리랭커 점수로 다시 평가 후 결정). 정답 쪽 기준 확정(D-023: 그 쪽만 보고 답할 수 있으면 정답) → a06·c07 검토 결과 변경 없음. "확인 불가" 2단계 판단 설계(ARCHITECTURE)
- (완료 2026-09-30) 1-a 리랭커 비교 — `BAAI/bge-reranker-v2-m3` 채택, N=10, "확인 불가" 2단계 잠정값(0.45 / 0.15). 결과는 "자체 평가 메모"와 D-024
- (완료 2026-10-01) 1-b 질의 흐름 — 서버 메모리·시간 측정, max_length 512 비교(1024 유지), "확인 불가" 3구간, `POST /qa`(Gemini JSON·인용 검증·query_logs), 샘플 10문항(D-024, D-025)
1. **[다음 세션] 1-c 판정기(Jev)** — 회색 구간(리랭커 1위 0.03~0.15)에서 can_answer를 불러 답변/확인 불가를 정하는 역할
   - 시작 전 사용자 확인: 받은 키가 TypeSafe 직접 API(`api.typesafe.ai`, 대기자 명단)용인지 Cloudflare Workers AI(`typesafe/jev`)용인지. `.env`에는 `TYPESAFE_API_KEY`, `JEV_ENABLED`, `JEV_MODEL`, `JEV_TIMEOUT_SECONDS`가 있음(값은 코드·로그·출력에 내지 않기). Cloudflare 경로면 `CLOUDFLARE_ACCOUNT_ID`·`CLOUDFLARE_API_TOKEN` 필요
   - 공식 문서로 요청·응답 형식 확인(추측 금지, D-007의 출처부터): 입력은 텍스트/JSON만, choice/score 응답은 confidence+probabilities. 확인 날짜·URL을 D-007에 추가
   - 구현 위치: `backend/app/judge/__init__.py`(`Judge` Protocol의 `can_answer(question, evidence) -> (bool, 신뢰도)`, `get_judge`가 지금 none 외에는 NotImplementedError) → 구현체 파일 추가(예: `app/judge/jev.py`, httpx, 시간 초과·재시도). 프롬프트·질문 문장은 `backend/app/prompts/`. 설정은 `config.py`·`.env.example`·MODIFY_GUIDE(신뢰도 임계값 포함)
   - 연결: `app/qa/service.py`의 `answer_question`이 이미 gray 구간에서 `models.judge.can_answer`를 부르고 `judge_info`를 query_logs.metadata.judge에 남김 → 판정기가 False면 "확인 불가", True면 답변(확신 낮음 해제 여부는 신뢰도 기준으로 결정). 판정기 오류·시간 초과 시 none과 같은 동작(답변 + 확신 낮음)으로 떨어지게. `mingyu_app.judgments`(question_key=can_answer) 기록은 solution 행이 없어 problem_id/solution_id가 비는데 CHECK 확인 필요
   - 테스트: 가짜 판정기로 gray 분기(True/False/오류) — `backend/tests/test_qa.py`에 추가. 실제 호출은 샘플 몇 개만(c06·c09·n08 회색 3개)
   - 주의: 서버는 시작 시 모델 로딩 약 1분(RSS 약 4.6GB). 샘플 실행은 `python -m app.qa.sample_run --ids c06,c09,n08`(서버 켠 상태, Gemini 무료 한도 — 전체 33개 금지)
   - 같이 볼 것: 근거 일치 판정(verify, ARCHITECTURE 질의 흐름 5단계)은 판정기 붙인 뒤. mingyu_app.solutions/solution_evidence 상세 저장은 화면(3번) 만들 때 필요하면
   - 프롬프트 조정 후보(2026-10-01 샘플): a01 confusions처럼 [n] 인용 없이 쓰는 문장, c07 설명이 근거 문장을 어색하게 이어 붙임(F1 설명을 민감도에 섞음) → `backend/app/prompts/answer_system.txt`
2. **청킹 보완: 표·수식 뭉침 + 페이지를 넘는 코드 블록**(질의 흐름 뒤, 시각자료 전): 팀 텍스트에서 표·계산식이 한 줄로 이어진 청크가 리랭커 점수·검색 순위가 낮음 — c06(3과목 p245~247 시계열 정상화, 리랭커 0.043), c07(p268 오분류표 평가지표, 0.208), c09(p339 연관규칙 측정 지표 표, 0.066). 할 일: 이런 청크를 찾는 기준(예: 숫자·기호 비율, 줄바꿈 없는 긴 문단) → 행 단위 분리나 표 제목·지표명 앞세우기 등 방식 결정(`backend/app/ingestion/chunking.py`, D-019) → 해당 쪽만 재청킹·재임베딩(`run_stages --stages chunk,embed --pages`) → 같은 33문항으로 재평가해 세 질문 순위·리랭커 점수 확인. `theory_chunks.raw_text`는 원문 그대로 유지(CLAUDE.md)
   - (2026-10-01 추가, 설계 D-026·ARCHITECTURE "이론 청킹 보완: 페이지를 넘는 코드 블록") 페이지를 넘어 이어지는 R 코드: 코드 블록 인식 규칙 + 이어짐 판단(앞 페이지 마지막 본문 줄·다음 첫 본문 줄이 코드, 사이 제목 없음) → 이어진 코드 블록만 한 청크로(page_id=시작 페이지, `source_alignment.spans`에 전체 페이지, 출처 "226~227쪽"), 코드+출력은 같은 청크, 코드 청크 embedding_text = 제목 경로 + 앞 설명 문장 + 코드(부족하면 Gemini 설명문). 재청킹은 이어진 앞뒤 페이지를 함께. 질의 API·평가 보고서의 쪽 표시와 정답 쪽 판정도 spans를 읽게 고침
   - 확인: 135·142·143쪽 첫 청크(지금 needs_review)가 앞 페이지 코드와 합쳐지는지, 조사 오검출(그래프 축 글자 272→273·303→304·337→338 등)이 코드로 묶이지 않는지 → 33문항 재평가
   - 마지막 단계: 구현 후 팀 공유 문서 `docs/team/cross-page-code.md` 완성("구현 후 채울 칸": 실제 코드 위치, 적용 전후 건수·검색 결과 비교, 상태를 "검증 완료"로)
3. 간단한 프론트로 실사용 — 최소 화면, 질의 흐름 바로 뒤(공부 화면 B 중심 + 검수 탭 최소: 답변 피드백, 보충·수정 목록)
4. 이론 보충·수정 (ARCHITECTURE "이론 보충·수정", material_type user_supplement·mingyu_app.chunk_corrections 마이그레이션은 사용자 확인 후)
5. 팀 텍스트 품질 비교: 몇 쪽(1과목 14쪽, 3과목 226쪽 등)을 팀 텍스트 / PaddleOCR mobile / Gemini 비전으로 뽑아 원본 이미지와 비교(정확도·누락·표/수식 처리, 속도·비용). 기존 "PaddleOCR 실제 교재 품질 측정"을 대체
6. crop / 시각자료: 검수 HTML 보고서 + 3과목 crop 시범(224~230쪽, D-016, 레이아웃 모델 Windows+CPU 지원 여부 공식 문서 확인부터) → 그래프 포함 문제 10개로 추출 정확도 확인(D-015) → crop 전체 확장 + 설명문 생성(Gemini, 재시도·폴백 D-010)
7. 오답노트 (D-017, mingyu_app 마이그레이션은 사용자 확인 후)
8. 손필기(personal_note) 비전 LLM 추출
- 틈틈이: 재처리 API(FAILED/REVIEW_REQUIRED/멈춘 페이지), 자료 삭제 시 저장 파일 정리, (사용자) S3 팀 버킷 유무 문의

## 막힌 것 / 확인 필요
- 리랭커 점수가 낮은 정답 청크(D-024): c06·c09는 3구간 구현으로 회색 구간 → 답변 + "근거 확신 낮음"(2026-10-01 샘플에서 확인). 청킹 보완은 다음 작업 2번. 값은 33문항 기준 잠정값 → 실사용 질문으로 다시 재야 함
- 리랭크 속도: CPU에서 질문당 약 4~6초(N=10, PC 부하에 따라 다름)로 /qa 전체 시간의 약 2/3. ONNX 백엔드 등은 필요해지면 검토
- 표가 한 줄로 뭉친 청크: 3과목 p268 "오분류표를 활용한 평가지표" 표가 계산식·지표명·설명이 섞인 한 덩어리 텍스트라(팀 텍스트 원문 형태) 검색 순위가 낮음(c07). 표 청킹 방식(행 단위 분리 등)은 다음 작업 2번에서 결정
- 3과목 216쪽은 원본 PDF·팀 텍스트 모두 없음(D-018). 필요하면 교재에서 직접 캡처해 업로드 경로로 추가
- 받은 Jev 키가 TypeSafe 직접 API용인지 Cloudflare Workers AI용인지 미확인
- (사용자) 2026-10-01 세션 중 GEMINI_API_KEY 값이 작업 출력(대화 기록)에 한 번 노출됨(파일·커밋에는 없음) → 필요하면 키 재발급 후 `.env` 교체
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
- 검색 평가(hit@K, "확인 불가" 임계값): 형식: 날짜 / 설정(임베딩 모델, 리랭커, 키워드 검색, N/K) / 질문 수 / hit@1·3·K / 임계값별 통과·차단
  - 2026-09-30 예시 6문항: 동작 확인용(결론 아님). hit@1 3/4, hit@3·@5 4/4
  - **2026-09-30 실제 세트 / BGE-M3, 리랭커·키워드 없음, K=5, 깊이 20 / 33문항(답 가능 26: 1과목 8·2과목 8·3과목 10, 자료 없음 7: 먼 주제 4 + 경계 사례 3) / 질문은 Claude 초안(교재를 보고 작성, 수험생 말투로 바꿈)이라 실제보다 유리할 수 있음**
    - 전체 hit@1 21/26(81%), hit@3 25/26(96%), hit@5 26/26(100%), MRR 0.881. 과목별 hit@1: 1과목 7/8, 2과목 8/8, 3과목 6/10(MRR 0.742)
    - 1위 점수: 답 가능 0.516~0.709(중앙 0.619) / 자료 없음 0.419~0.608(중앙 0.518). 경계 사례 n08(Mean Shift→k-평균·DBSCAN 청크) 0.608, n07(XGBoost 규제→릿지 p226) 0.537, n06(LSTM→신경망 종류 p287) 0.518. 먼 주제는 CNN 0.419, S3 0.468, 트랜스포머 0.508, Kafka 0.537
    - 임계값(1위 점수 ≥ t 통과): 0.50 → 답 가능 26/26 통과, 자료 없음 2/7 차단 / 0.55 → 22/26 통과, 6/7 차단 / 0.60 → 17/26, 6/7. **점수 하나로는 못 가름**(두 분포가 0.52~0.61에서 겹침) → 확정 안 함, 리랭커 점수로 재평가
    - 1위가 아닌 5문항 분류:
      - 의미가 가까운 다른 쪽 1: a06(2위, 1위 p45 "데이터의 오용"에 "피해자를 구제할 전문가" 설명은 있으나 이름이 없음 → D-023 기준으로 정답 아님)
      - 질문 표현(용어 중의성) 3: c01(4위, "군집추출"이 계층적 군집 p320~322로 끌림), c02(3위, "5단계"·"매우 불만~매우 만족"이 디자인 씽킹 5단계·STRESS 적합도 표로 끌림), c09(2위, "lift"가 향상도 곡선 p274로 끌림). 키워드 검색·리랭커로 개선 여지
      - 청킹 문제 1: c07(3위, 1위 p271은 민감도·특이도 정의만 있고 recall 언급이 없어 D-023 기준으로 정답 아님). recall=sensitivity 답이 있는 p268 평가지표 표가 한 줄로 뭉친 청크라 상위 5에 못 듦("막힌 것" 참고)
    - HTML 보고서: `data/reports/eval/20260930-195048.html`
  - **2026-09-30 리랭커 비교 / BGE-M3 + 리랭커, 키워드 없음, K=5 / 같은 33문항 (D-024에 전체 표)**
    - 벡터만: hit@1 21/26(81%), hit@3 25, hit@5 26, MRR 0.881 / 과목별 hit@1 7/8·8/8·6/10
    - `BAAI/bge-reranker-v2-m3` N=10 embedding_text(**채택**): hit@1 22/26(85%), hit@3 26, hit@5 26, MRR 0.917 / 과목별 hit@1 6/8·7/8·9/10 / 리랭크 평균 6.0초·최대 10.2초. N=20: hit@1 22·hit@5 25·MRR 0.910·12.6/20.1초, N=30: 같은 순위·14.6/26.9초, clean_text(N=20): hit@1 21·MRR 0.886
    - `dragonkue/bge-reranker-v2-m3-ko` N=20 embedding_text: hit@1 24/26(92%), hit@3·5 26, MRR 0.962 / 과목별 6/8·8/8·10/10 / 10.3·18.1초. clean_text: hit@1 23, MRR 0.929
    - 순위 변화(벡터 → v2-m3 N=10 / -ko N=20): c01 4→1/1, c02 3→1/1, c09 2→1/1, c07 3→1/1, a06 2→2/2(p45가 계속 1위). 나빠진 것(v2-m3): a02·b02 1→2, c06 1→3
    - 리랭커 1위 점수 분포: v2-m3 N=10 답 가능 0.043~0.993(중앙 0.732) / 자료 없음 0.000~0.131(n08 0.131, 나머지 ≤0.005) → 거의 분리. N=20/30은 n08이 0.622(벡터 13위 DBSCAN 청크)라 겹침. -ko는 답 가능 최저 0.000(정답 1위인데 <0.01인 질문 6개) / 자료 없음 최고 0.512 → 겹쳐서 임계값에 못 씀
    - 2단계 잠정값(v2-m3 N=10): 벡터 하한 0.45 + 리랭커 0.15 → 답 가능 24/26 통과(c06 0.043·c09 0.066 차단), 자료 없음 7/7 차단. 벡터 1위 점수만 쓸 때(0.55: 22/26 통과·6/7 차단)보다 나음
    - 3구간 설계(사용자 결정, 구현은 1-b): 하한 0.03 미만 바로 확인 불가(자료 없음 6/7, 답 가능 0/26) / 0.03~0.15 회색(c06·c09·n08) / 0.15 이상 답변(답 가능 24/26)
    - HTML 보고서: `data/reports/eval/20260930-205236.html`(채택 설정, 리랭크 전 벡터 순위 함께 표시)
- 페이지를 넘는 R 코드 조사(2026-10-01, DB 읽기 전용, 팀 텍스트 줄 + 청킹의 머리말·제목 규칙 사용, 설계는 D-026)
  - 엄격 기준(앞 페이지 마지막 본문 줄과 다음 페이지 첫 본문 줄이 모두 코드, 다음 첫 줄이 제목 아님): 1과목 0 / 2과목 0 / **3과목 9건**. 실제 코드 이어짐 6(134→135, 149→150, 206→207, 222→223, 280→281, 295→296), 그래프 글자 오검출 3(272→273 ROC, 303→304 plotcp, 337→338 축 눈금)
  - 완화 기준(앞뒤 3줄 안, `#` 주석 한글 무시, 열 이름 줄 포함): 2과목 1(도식, 오검출) / 3과목 40건 — 눈으로 본 잠정 분류: 코드·출력 이어짐 약 18(예: 141→142 데이터프레임 출력, 142→143 리스트 출력, 145→146 median→[1] 5.5, 284→285 glm 출력→anova, 314→315 naiveBayes 출력), 앞 예제 끝·다음 예제 시작 4, 그래프·수식 글자 19
  - 뒷부분 첫 청크가 needs_review(검색 제외): **3건 — 135쪽(">x=1 >y=2 > x+y [1] 3"), 142쪽(데이터프레임 출력), 143쪽(`[1] "kimDoHyune" $height [1] 182`)**. 엄격 기준으로는 135쪽만 잡힘(142·143은 열 이름 줄·OCR 조각 "a"·한글 주석 때문에 놓침). 전체 needs_review 11개 중 3개
- 질의 답변(`POST /qa`): 형식: 날짜 / 설정 / 질문 / 판정·인용·시간
  - **2026-10-01 첫 샘플 10문항 / bge-m3 + v2-m3 N=10 K=5, 3구간 0.45·0.03·0.15, JUDGE_PROVIDER=none, gemini-3.5-flash-lite** (`data/reports/answers/20261001-091851.md`)
    - 답변 구간 6(a01·a06·b05·c01·c07 answered high), 회색 3(c06·c09 answered + 확신 낮음, n08은 LLM이 unanswerable), reject 2(n01 벡터 하한, n07 리랭커 하한 — LLM 호출 없음)
    - 자료 없음 3개(n01·n07·n08) 모두 "확인 불가", 답 가능 7개 모두 정답 쪽 인용(a06은 리랭커 1위가 오답 쪽 p45였지만 LLM이 [2] p52에서 "알고리즈미스트"를 찾음). 범위 밖 인용 0
    - 시간: 답변 5.7~7.4초(리랭크 3.4~5.1, LLM 1.5~2.0), reject 0.5초(벡터 하한)·4.4초(리랭커 하한). 토큰 약 2,000~2,750/질문

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
- 2026-09-30: 검색 평가 실행 — 질문 세트 33문항(Claude 초안, 경계 사례 3 포함), 평가 HTML 보고서(썸네일), 결과 기록(hit@5 100%, hit@1 81%, 확인 불가 임계값은 미확정), 다음 작업 순서 조정(질의 흐름 → 최소 화면 → 이론 보충·수정), 정답 쪽 기준(D-023)·"확인 불가" 2단계 판단 설계 (테스트 77+2개)
- 2026-09-30: 리랭커 비교 — `rerank.py`(CrossEncoder), 검색·평가에 리랭크 단계(`--reranker/--n/--rerank-input`, 리랭커 점수 임계값·2단계 표·리랭크 시간), 3개 설정 × N·입력 비교 → `BAAI/bge-reranker-v2-m3` N=10 채택, "확인 불가" 2단계 잠정값 0.45/0.15 (D-024, 테스트 82+3개)
- 2026-10-01: 질의 흐름(1-b) — 서버 메모리·단계별 시간 측정(RSS 최대 4.66GB, 첫 질문 임베딩 26초 → 시작 시 워밍업), RERANKER_MAX_LENGTH 512 비교(1024 유지), "확인 불가" 3구간(0.45 / 0.03 / 0.15), `POST /qa`(Gemini JSON 구조화 출력, 인용 검증, query_logs.metadata 기록, 모델 사전 로딩), 샘플 10문항 실행 (D-024 추가, D-025, 테스트 95개)
- 2026-10-01: 청킹 보완 설계(코드 변경 없음) — 페이지를 넘는 R 코드 조사(엄격 9건·완화 41건, 뒷부분 needs_review 3건), D-026(이어진 코드 블록만 페이지 넘김 예외, 쪽 범위 출처, crop 세로 이어 붙이기), 팀 공유 문서 `docs/team/`(PaddleOCR Windows+CPU 설정, 페이지 넘는 코드 처리 초안)
