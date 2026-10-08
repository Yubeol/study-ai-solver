# DECISIONS

> **번호 규칙** (2026-10-06, 팀 합류 후)
> - D-001~D-029는 팀 합류 전 기록이다. 번호를 바꾸지 않는다.
> - 새 결정은 `D-<이니셜>-<번호>`로 사람마다 따로 번호를 이어 간다. 민규는 `D-M-030`부터(팀 합류 준비 결정 D-030을 D-M-030으로 바꿈), 팀원은 각자 이니셜로 `001`부터. 이니셜이 겹치면 두 글자로 정한다.
>
>   | 사람 | 역할 | 이니셜 | 시작 번호 |
>   |---|---|---|---|
>   | 민규 | DB·재적재·질의 흐름 | `M` | `D-M-030` |
>   | 재원 | 백엔드 기능 | `JW` | `D-JW-001` |
>   | 수지 | 프론트 | `SJ` | `D-SJ-001` |
>   | 수민 | 데이터 | `SM` | `D-SM-001` |
>
>   새 팀원은 이 표에 한 줄 추가한다.
> - 형식: `## D-M-031 제목 (날짜)` + 배경·결정·이유, 외부 정보는 확인 날짜와 출처 URL. 같은 PR에서 새 결정을 추가하고, 다른 사람의 결정을 바꿀 때는 원래 항목에 "→ D-X-NNN에서 변경"을 덧붙인다.

## D-001 과목은 ADsP (2026-09-29)
공부에 실제로 쓸 과목. 설계는 과목에 의존하지 않게 유지한다(books.subject로 구분).

## D-002 과제 중심은 질의형 시험공부 RAG (2026-09-29)
실습과제 슬라이드 기준으로 "자료 업로드 → 질문 → 시험형 답변"이 핵심이다. 인수인계의 문제 사진 풀이는 질의 입력 방식 중 하나로 포함한다.

## D-003 DB는 팀 공유 서버의 mingyu 스키마 (2026-09-29)
- 팀원이 AWS에 PostgreSQL을 띄우고 스키마 4개(jaewon, mingyu, sugi, sumin)와 규격 테이블을 만들어 둠. 내 스키마는 mingyu.
- 공용 프론트가 같은 구조로 조회할 수 있으므로 기존 컬럼은 바꾸지 않고 추가만 한다. → **D-021에서 공용 프론트 없음으로 변경**, "추가만" 규칙은 유지.
- 서비스 전용 테이블은 별도 스키마 mingyu_app에 둔다.
- 보안: 5432 포트가 0.0.0.0/0으로 공개되어 있고 관리자 계정을 공유한다. 접속 정보는 .env에만 두고, 다른 스키마는 접근하지 않는다.

## D-004 프로젝트 경로는 E:\자료실\adsp-study-rag (2026-09-29)
한글 경로 때문에 Windows에서 cv2.imread가 실패할 수 있다. 이미지는 바이트로 읽어 cv2.imdecode로 연다(CLAUDE.md 규칙).

## D-005 Python 환경: 루트 pyproject + uv, Python 3.12 고정 (2026-09-29)
PyCharm이 루트에 uv 프로젝트를 생성해 그대로 사용. torch 계열 설치 문제를 피하려고 requires-python ">=3.12,<3.13".

## D-006 Vision/LLM은 Gemini 3.5 Flash-Lite(기본) + 3.7 Flash(재처리, 잠정) (2026-09-29)
- 처음 계획은 2.5 Flash-Lite / 2.5 Flash였으나 신규 무료 키로 호출 시 404. 모델 목록에는 보이지만 호출은 막힘.
  - Google 공지: 2.5 모델 접근을 기존 사용자로 제한, 신규 프로젝트는 3.5 Flash-Lite / 3.8 Flash 권장. 2.5는 2026-10-16 종료 예정.
  - 출처: https://ai.google.dev/gemini-api/docs/deprecations , https://firebase.google.com/docs/ai-logic/models
- 실제 호출 결과 (무료 키, 2026-09-29):
  - gemini-3.5-flash-lite: 성공 → GEMINI_MODEL_LITE로 확정
  - gemini-3.8-flash: 429 연속 → 무료 한도 없음 또는 극소로 판단, 사용 안 함
  - gemini-3.7-flash, gemini-3.6-flash: 503(일시적 과부하) → 접근 자체는 가능해 보임. 3.7을 GEMINI_MODEL_STRONG으로 잠정 지정, 재처리 기능 구현 시 재확인
- 무료 티어는 입력 데이터가 Google 제품 개선에 쓰일 수 있음(개인 학습 자료이므로 수용, 개인정보는 넣지 않음).
- 참고: GPT-5.6 Luna는 입력 $0.20 / 출력 $1.20 per 1M (2026-07-30부터, 출처: https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/)

## D-007 Jev는 교체 가능한 판정기로만 사용 (2026-09-29)
- 확인 사항:
  - 2026-09-15 얼리 액세스. 직접 API는 대기자 명단, POST https://api.typesafe.ai/v1/systemone, 모델 jev-latest. 무료 크레딧 언급 없음. (출처: https://www.datacamp.com/blog/system-one-models-jev , https://typesafe.ai/blog/introducing-system-one-models-and-jev)
  - Cloudflare Workers AI: 모델 ID typesafe/jev, 서드파티, 무보관, 컨텍스트 32,000토큰, 입력 $0.042/1M, 출력·캐시 무료. REST로 호출 가능. (출처: https://developers.cloudflare.com/ai/models/typesafe/jev/)
  - Vercel AI Gateway, Cloudflare는 대기자 명단 없이 제공.
  - 텍스트/JSON만 입력 가능(이미지 불가). choice/score는 confidence+probabilities, noul은 확률값 하나만 반환.
  - Workers AI 무료 할당량(10,000 뉴런/일)이 서드파티 Jev에 적용되는지는 미확인.
- **키 경로 확인(2026-10-01)**: `.env`의 `TYPESAFE_API_KEY`는 **TypeSafe 직접 API용**. `CLOUDFLARE_ACCOUNT_ID`·`CLOUDFLARE_API_TOKEN`은 키 이름만 있고 값이 비어 있음 → Cloudflare 경로는 쓰지 않는다.
  - 공식 문서(확인 2026-10-01): `POST https://api.typesafe.ai/v1/systemone`, 헤더 `Authorization: Bearer <API_KEY>`, 본문 필수 `state`(문자열 또는 JSON), `model`(`"jev-latest"`), `questions`(이름 → 질문 객체). 질문 유형 `noul`(예/아니오 확률 0~1, `instructions`, 선택 `criteria.true/false`), `choice`(choice·probabilities·confidence), `score`(2~10단계 루브릭). 응답 `model`, `answers`(질문 이름별 `{type, noul|choice|score…}`), `usage.input_tokens/output_tokens`. 오류 401(키 없음·잘못됨) / 422(요청 검증 실패) / 429(한도 초과, 지수 백오프) / 529(과부하). 문서 안내 한도 250,000토큰/초·1,200요청/분(바뀔 수 있음)
  - 출처: https://docs.typesafe.ai/api.md , https://docs.typesafe.ai/introduction/quickstart , https://docs.typesafe.ai/primitives/noul.md (noul 페이지 예시는 `"selectedModels": ["jev-latest"]`를 쓰지만 API 레퍼런스는 `model` → 레퍼런스 형식으로 호출해 성공)
  - 최소 요청 1회(2026-10-01, 문서 예시 문장 + noul 질문 1개): **HTTP 200 성공**, 응답 모델 `jev-1.13.0`, 입력 283·출력 23토큰. `.env`의 `JEV_MODEL` 값은 `jev-latest`와 같음. 키·응답 헤더는 출력·기록하지 않음
- 결정: 역할은 답변 가능 판정, 단원·유형 분류, 객관식 후보, 근거 일치 판정. JUDGE_PROVIDER로 교체하며 none에서도 서비스가 동작한다. 신뢰도 임계값은 직접 데이터로 보정한다.

## D-008 텍스트 추출은 자료 유형별 분기 (2026-09-29)
인쇄체(교재·강의노트)는 PaddleOCR(로컬), 손필기(개인노트)는 비전 LLM. 사용자 문제 사진은 비전 LLM으로 문제문·보기·수식을 구조화 추출.

## D-009 임베딩은 로컬 BGE-M3, 1024차원 (2026-09-29)
팀 DB 규격(vector(1024))과 테이블 주석 기준. 질의 임베딩도 같은 모델을 사용한다.

## D-010 외부 API 호출은 재시도 + 폴백 필수 (2026-09-29)
무료 키에서 429(한도)와 503(과부하)가 실제로 발생함을 확인. 모든 Gemini 호출은 429/503에 지수 백오프 재시도를 하고, GEMINI_MODEL_STRONG이 재시도 후에도 실패하면 GEMINI_MODEL_LITE로 폴백한다. 대량 처리는 분당 요청 수를 제한해서 돌린다.

## D-011 DB 접근은 psycopg 3 + 직접 SQL, 마이그레이션은 자체 실행기 (2026-09-29)
- ORM/Alembic 대신 psycopg 3(+psycopg_pool)와 번호 붙은 SQL 파일을 쓴다. 팀 규격 테이블을 "추가만" 하는 규칙과 스키마 이름 비하드코딩 규칙을 SQL 파일 단위로 검토·통제하기 쉽기 때문.
- 스키마 이름은 SQL에 `{{schema}}`, `{{app_schema}}` 자리표시자로 두고 실행기가 설정값으로 치환한다. 설정 로딩 시 스키마 이름은 `[a-z_][a-z0-9_]*`만 허용한다.
- search_path는 세션에서 바꾸지 않고, 필요할 때만 트랜잭션 안 `SET LOCAL`(scoped_transaction). 테스트로 풀 반환 후 원복을 확인한다.
- mingyu_app → 팀 테이블(query_logs, constraint_presets) FK는 ON DELETE SET NULL로 걸었다(팀 테이블 자체는 변경 없음).
- books.material_type 값은 영문 코드: textbook / lecture_note / personal_note.

## D-012 처리 상태는 팀 규격 값만 쓰고, 세부 정보는 JSONB에 둔다 (2026-09-29)
- pages.processing_status CHECK(RAW/EXTRACTED/REVIEW_REQUIRED/VERIFIED/EMBEDDED/FAILED)에는 "처리 중" 값이 없다. 팀 규격 제약을 바꾸지 않기 위해 단계 묶음이 끝날 때만 상태를 바꾼다(extract_text→EXTRACTED, detect_visuals+chunk_theory→VERIFIED, embed→EMBEDDED, 품질 미달→REVIEW_REQUIRED, 예외→FAILED).
- 현재 단계·오류는 pages.page_metadata.pipeline, 업로드 순서는 page_metadata.upload_index(pages에 순서 컬럼이 없음), 원본 파일명은 page_metadata.original_filename. DDL 변경 없음.
- 업로드 1회 = processing_runs 1건. pipeline_version은 모델 이름이 아니므로 코드 상수(`PIPELINE_VERSION`, 현재 `0.2-ocr`)로 둔다.
- 백그라운드 실행은 FastAPI BackgroundTasks(프로세스 내). 서버가 재시작되면 진행 중이던 페이지는 중간 상태로 남는다 → 재처리 API로 보완 예정.
- 업로드 검증은 Pillow(형식·크기 확인만, 원본 바이트는 변경하지 않음). 이후 이미지 처리는 OpenCV(한글 경로 규칙 적용). python-multipart는 FastAPI 파일 업로드에 필요.
- (2026-09-29 추가) 아직 구현하지 않은 단계는 `StageNotImplemented`를 던지고, 페이지는 상태를 바꾸지 않은 채 멈춘다(마지막으로 끝난 상태 유지, page_metadata.pipeline.stopped="not_implemented"). 이런 페이지는 run 개수 컬럼 어디에도 넣지 않고 run은 PARTIAL로 둔다(page_count - 합계 = 미완료).

## D-013 인쇄체 OCR: PaddleOCR 3.7 + mobile 검출 + 한국어 인식, CPU, oneDNN 끔 (2026-09-29)
- 설치 (확인일 2026-09-29):
  - paddlepaddle 3.3.1 (cp312 win_amd64 wheel 있음, 약 105MB), paddleocr 3.7.0 (2026-06-11, Python>=3.8), paddlex 3.7.2. `uv add "paddlepaddle==3.3.1" "paddleocr==3.7.0" numpy opencv-contrib-python`
  - OpenCV는 paddlex가 `opencv-contrib-python==4.10.0.84`로 고정 → `opencv-python`을 따로 넣지 않는다(cv2 충돌).
  - 출처: https://pypi.org/project/paddlepaddle/3.3.1/#files , https://pypi.org/project/paddleocr/ , https://www.paddleocr.ai/latest/en/version3.x/installation.html
- 모델 캐시 위치: `OCR_MODEL_DIR`(현재 `E:\paddle_models`) → import 전에 `PADDLE_PDX_CACHE_HOME`으로 설정. 모델은 `{경로}/official_models`, 잠금·임시 파일도 같은 경로 아래. HuggingFace에서 `snapshot_download(local_dir=...)`로 받으므로 C:의 HF 캐시에는 참조 파일·로그만 남는다(실측 약 100KB).
  - 공식 사용 문서 본문에는 없고, 근거는 PaddleX 소스와 메인테이너 답변: https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/utils/cache.py , https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/utils/official_models.py , https://github.com/PaddlePaddle/PaddleOCR/discussions/16631 . 설치된 3.7.2 소스에서도 같은 코드임을 확인.
  - paddlex가 이미 다른 캐시 값으로 import된 경우 엔진 생성 시 오류를 낸다(모델이 C:로 받아지는 것 방지).
- 실행 옵션:
  - `enable_mkldnn=False`: paddlepaddle 3.3.x CPU oneDNN 경로에서 `NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]`가 실제로 발생. 공식 파라미터로 끔. 출처: https://github.com/PaddlePaddle/Paddle/issues/77340 , https://github.com/PaddlePaddle/Paddle/issues/79749 . Paddle이 고치면 다시 켜서 속도 비교.
  - 문서 방향 분류·왜곡 보정·줄 방향 분류는 끔(기본값은 켜짐, 스캔 교재에 불필요).
  - 모델: `OCR_DET_MODEL=PP-OCRv5_mobile_det`, `OCR_REC_MODEL=korean_PP-OCRv5_mobile_rec`. 모델 이름을 주면 PaddleOCR가 `lang`을 무시한다 → 검출만 지정하면 비한국어 인식 모델(PP-OCRv6_medium_rec)이 올라와 한글이 모두 빠지는 것을 실측. 그래서 검출을 지정하면 인식도 필수(설정 검증).
- 실측 (이 PC, CPU 28스레드, oneDNN 끔, 맑은 고딕으로 만든 A4 1654x2339, 30줄):
  - `lang="korean"` 기본 검출(PP-OCRv5_server_det): A4 1장이 20분 넘게 끝나지 않음 → 사용 불가
  - PP-OCRv5_mobile_det + korean_PP-OCRv5_mobile_rec: 1장 약 16~17초, 30줄 모두 검출, 평균 신뢰도 0.994
  - 쉼표 뒤 공백이 빠지는 경우가 있음("선형성, 독립성" → "선형성,독립성"). raw_text는 OCR 결과 그대로 두고 교정하지 않는다.
  - 실제 교재 스캔으로는 아직 측정하지 않음 → 품질이 낮으면 Gemini 추출 경로를 다시 검토.
- 동시성: 추론 객체의 스레드 안전성이 문서에 없어 엔진 1개 + 잠금으로 직렬화(BackgroundTasks 스레드풀 대비).
- 저장: 줄 단위 전체 결과(text, confidence, bbox)는 저장소 `books/{book_id}/{page_id}.ocr.json`, `page_metadata.ocr`에는 요약(uri, 줄 수, 평균 신뢰도, 엔진·버전·모델). theory_chunks는 4-3에서 만든다. 손필기(personal_note)는 비전 LLM 구현 전까지 REVIEW_REQUIRED("손필기 추출 미구현").
- uv 캐시는 사용자 환경변수 `UV_CACHE_DIR=E:\uv-cache`로 옮김(C 여유 공간 부족).

## D-014 팀 교재 3권은 팀 텍스트를 추출 결과로 쓰고, PaddleOCR은 새 캡처용으로 미룸 (2026-09-30)
- 팀 교재 PDF(1과목 50장, 2과목 64장, 3과목 211장)는 휴대폰 촬영 스캔이라 기울기·휨·그림자가 있고 텍스트 레이어가 없다. 팀원이 추출한 페이지별 텍스트가 이미 있으므로 이를 extract_text 결과로 저장하고 출처(engine="team_text", 원본 파일명)를 표시한다.
- D-008(인쇄체는 PaddleOCR)을 이 세 권에 한해 대체한다. PaddleOCR 경로는 새로 업로드하는 캡처용으로 남겨 두고 작업 순서만 뒤로 미룬다.
- 팀 텍스트에는 줄 bbox가 없으므로 청크 출처는 페이지 단위로만 표시한다. raw_text는 팀 텍스트 원문 그대로(교정 금지), 머리말/쪽번호 줄만 청킹에서 제외, 기출 표시는 exam_clues로 옮긴다.
- PDF 장 ↔ 인쇄 페이지 매핑은 반입 세션에서 실제 대조 후 확정(현재 확인된 것: 3과목 PDF 94~96장 = 226~228쪽). DB 적재는 매핑을 사용자에게 확인받은 뒤.

## D-015 시각자료는 다시 그리지 않고 원본 crop + 설명문으로 표시, 문제 속 그래프는 텍스트화 (2026-09-30)
- 재구성한 그래프는 원본과 달라질 위험이 있어(환각) 화면에는 원본 crop 이미지와 설명문만 보여준다.
- Jev는 텍스트/JSON만 입력 가능(D-007)하므로 문제 속 그래프·표는 비전 LLM(Gemini)이 텍스트로 풀어낸 뒤 그 텍스트로 검색·판정한다.

## D-016 시각자료 crop: 보정 → 레이아웃 검출 → 캡션 기준 그룹핑, Gemini에는 crop만 (2026-09-30)
- 순서: OpenCV 원근·조명 보정 → 레이아웃 분석 모델로 그림/표/수식/캡션 검출 → 캡션(그림 아래 `<...>`, 꺾쇠 없는 경우 포함) 기준 그룹핑·여백 확장 crop → 표는 visual_tables, 그림은 visual_assets.
- 비용·무료 한도(D-010)를 아끼기 위해 Gemini에는 페이지 전체가 아니라 crop + 관련 이론 문장 2~5개만 보낸다. 검출이 애매한 페이지만 영역 좌표 보조 요청.
- 레이아웃 모델(PaddleOCR 계열 레이아웃 기능)의 Windows + CPU 동작 여부는 **미확인** → 구현 세션에서 공식 문서로 확인하고 출처·날짜를 이 항목에 추가한다. 안 되면 OpenCV 규칙 기반으로 대체.
- 3과목 224~230쪽 시범 → 검수 HTML 보고서로 확인 → 전체 확장.

## D-017 오답노트: 내 답·내 이유 비교, 틀린 유형 4종, 판정기 역할 2개 추가 (2026-09-30)
- 틀린 유형: concept_confusion(개념 혼동) / misread(문제 오독) / calculation(계산 실수) / memorization(암기 부족).
- 판정기 인터페이스에 `reason_match`(내 이유가 근거와 일치?), `error_type`(틀린 유형 선택)을 추가한다. JUDGE_PROVIDER=none이면 LLM 구조화 출력으로 대신하거나 비워 두고, 흐름은 끝까지 간다.
- 개념 혼동 설명에는 theory_chunks.confusable_concepts와 concept_relations(compare)를 쓴다.
- 테이블은 mingyu_app에 wrong_notes / wrong_note_evidence / wrong_note_attempts로 설계만 해 두고(ARCHITECTURE "오답노트"), 마이그레이션은 구현 세션에서 사용자 확인 후 적용한다. judgments.question_key CHECK도 그때 새 마이그레이션으로 확장한다.

## D-018 팀 교재 반입: pypdfium2 렌더링, page_map.json 매핑, 합본 텍스트는 첫 쪽에 (2026-09-30)
- PDF 렌더링 라이브러리: **pypdfium2 5.13.0** (2026-08-13 릴리스, `py3-none-win_amd64` wheel). 라이선스 **BSD-3-Clause 또는 Apache-2.0**(이중), 내장 PDFium은 BSD 계열. 출처: https://pypi.org/project/pypdfium2/ (확인 2026-09-30)
  - 제외: PyMuPDF 1.28.2는 **AGPL-3.0 또는 Artifex 상용** 이중 라이선스 → 과제 코드 공개 범위와 충돌 가능성이 있어 쓰지 않음. 출처: https://pypi.org/project/PyMuPDF/ (확인 2026-09-30)
  - `uv add "pypdfium2==5.13.0"` (paddlex 의존성으로 이미 설치돼 있어 직접 의존성으로 고정만 함)
- 경로 주의: 팀 PDF 파일명이 **NFD**(자모 분리, macOS 압축 추정)로 저장돼 있어 NFC로 쓴 경로는 FileNotFoundError. 파일은 NFC 비교로 찾고, PDFium에는 파일 객체로 넘긴다.
- 팀 PDF 구조: 장마다 JPEG(DCTDecode) 1장, 1pt = 1px → 72 DPI 렌더가 원본 해상도. 저장용은 `TEAM_IMPORT_RENDER_DPI`(기본 72) JPEG, 대조용 미리보기는 `TEAM_IMPORT_PREVIEW_DPI`(기본 14)로 분리.
- 팀 텍스트 인코딩: 전 파일(과1 49, 과2 64, 과3 210) **UTF-8, BOM 없음, LF** 확인(cp949 아님). 파일명도 정상(깨지지 않음). strict UTF-8로 읽고 원문 그대로 저장.
- 매핑(표본 대조, "PDF 장 + offset = 인쇄 쪽" 가정 검증, `data/raw/adsp/page_map.json`):
  - 1과목: 50장 = 14~63쪽, offset +13 일정. `과1-58-59p.txt` 한 파일에 58·59쪽 내용이 이어져 있음(58쪽=PDF 45장, 59쪽=PDF 46장)
  - 2과목: 64장 = 66~129쪽, offset +65 일정
  - 3과목: 211장이지만 **216쪽은 촬영 안 됨**, **252쪽은 120·121장에 중복 촬영**. 1~84장 +131, 85~120장 +132, 121장 건너뜀, 122~211장 +131 → pages 210행. `과3-216-217p.txt`의 내용은 217쪽뿐
  - (D-014의 "3과목 PDF 94~96장 = 226~228쪽"은 이 매핑과 일치)
  - 보조 확인: 텍스트 끝 쪽번호 줄과 대조 1과목 49/49, 2과목 55/55, 3과목 200/201 일치(나머지는 쪽번호 줄 없음, 3과목 159쪽 1건은 R 출력 숫자 오탐). `|`가 1로 읽힌 경우("127" = 27쪽)도 일치로 봄
- 72 DPI 근거(2026-09-30 전수 확인): 325장 모두 이미지 1개, 내장 JPEG 픽셀 크기 = 페이지 크기(pt), 이미지가 페이지 전체(0,0,w,h)를 덮음. 과목별 첫/중간/끝 장을 72 DPI로 렌더한 크기도 내장 이미지와 같음 → 저장 DPI 72 유지.
- 합본 텍스트 처리(사용자 확정): page_map `text_files`에 `split_at_lines`(다음 쪽이 시작하는 줄 번호)가 있으면 줄 단위로만 잘라 쪽별로 저장한다(내용 변경 없음, 조각을 이으면 원문). 두 페이지 `page_metadata.text.note`에 "과1-58-59p.txt의 30번째 줄에서 분할" 기록, `text.lines`에 줄 범위.
  - `과1-58-59p.txt`: 58쪽 이미지는 29줄("…소프트 스킬이다.") 아래가 비어 있고 59쪽 맨 위는 HARD/SOFT SKILLS 그림 → 30줄부터 59쪽.
  - `split_at_lines`가 없으면 첫 쪽에 전체를 붙이고 나머지 쪽은 REVIEW_REQUIRED("team_text 없음 (…에 합쳐져 있음)").
- 누락 쪽(3과목 216쪽): pages 행을 만들지 않는다. books·processing_runs에 메모 컬럼이 없으므로 반입 리포트(`data/reports/team_import/apply_{key}.json`의 missing_printed)와 다음 쪽(217쪽) `page_metadata.missing_before`에 남긴다. `과3-216-217p.txt`는 217쪽으로 매핑하고 `text.note`에 파일명과 내용이 다름을 기록.
- 실행: `--apply`는 `--subject`(page_map key, 여러 개는 쉼표, 전체는 all) 필수. 1과목 반입 → 사용자 확인 → 2·3과목 반입 완료(2026-09-30, 3권 324페이지).
- 반입 방식: 원본 파일명 변경·복사본 없이 page_map.json이 원본 경로를 가리킨다(D-014의 파일명 정리 단계 대체). 중복 방지는 books(subject, title, source_name) 존재 여부, 파일 저장 후 book 단위 트랜잭션(books + processing_runs 1건 + pages), 실패 시 저장 파일 삭제. EXTRACTED 페이지는 run 집계에서 미완료로 셈 → run은 PARTIAL(D-012).

## D-019 이론 청킹 규칙, 원문 위치 저장 형식, 청킹 후 상태 (2026-09-30)
- 코드: 규칙은 `backend/app/ingestion/chunking.py`(순수 함수), 단계는 `stages.chunk_theory`, 저장은 `repositories/theory_chunks.py`, 실행은 `python -m app.ingestion.run_stages`(dry-run 기본, `--apply --subject KEY|all` 또는 `--book-id`)
- 텍스트 역할(사용자 확정)
  - `raw_text`: 청크에 속한 원문 줄을 **줄 앞뒤 공백만 정리**해 줄바꿈으로 이은 것. 글자 교정·기호 제거 없음(기출 표시·학습목표 줄 포함). 머리말/쪽번호 줄은 어느 청크에도 넣지 않는다. "제목•본문"처럼 한 줄을 제목과 본문으로 나눈 경우에도 raw_text에는 원문 줄 한 번만 넣는다.
  - `clean_text`: 머리말·쪽번호 줄, 학습목표·"5년간 출제 횟수" 줄, 기출 표시("(★기출)", "(★)", "(기출)", ★), 글자 없는 조각("•", "->")을 뺀 것.
  - `embedding_text`: `장 > 절 > 항 > 세부 > ■박스` 제목 경로 + 빈 줄 + clean_text. 제목 경로는 앞 페이지(upload_index 순서)의 `page_metadata.chunking.end_state`에서 이어받는다.
  - `title`은 경로의 마지막 제목, `sort_order`는 페이지 안 순서(0부터).
- 머리말/쪽번호: "ADSP 한 권으로 끝내기"가 들어간 줄, `|`만 있는 줄, 그 쪽 번호 또는 "1"+쪽번호("127" = "|27", D-018), "N과목 …"(25자 이하), "N장 … |" 및 페이지 끝 4줄 안의 "N장 …".
- 제목: "N장"+다음 줄 / "0N 절" / "N. 항" / "N) 세부" / "■ 박스". `CHUNK_HEADING_MAX_CHARS`(60) 이하이고 "다(.)"로 끝나지 않는 줄만. "3.5" 같은 수치는 제외. "N) 제목•본문"은 "•" 앞을 제목으로 본다. 장 제목 줄이 깨진 경우(1과목 3장) 꼬리말 "N장 …"의 장 번호로 보완.
- `exam_clues`(JSONB 목록): `heading_mark`(제목의 기출 표시, 별 개수. 같은 제목 아래 다음 청크·다음 페이지에는 `inherited: true`로 붙고, 같은 수준 이상의 제목이 바뀌면 끊긴다), `exam_mark`(본문 줄의 표시), `learning_goal`, `frequency`(`items: [{topic, stars}]`).
- 기출 문제 블록: "기출유형 개념잡기"부터 다음 제목 또는 "학습정리/용어 정리/확대경/학습목표"(앞의 `|`, `•` 무시)까지. 청크에 넣지 않고 `excluded_sections(section_type='exam_question', title='기출유형 개념잡기 [N회 출제]')`로 저장. 페이지 끝에서 끊긴 블록은 다음 쪽 첫 줄이 문제 모양([N회 출제], 정답/해설, ①~④, "번호 …?")일 때만 이어서 제외(무조건 이어받으면 2-118, 3-152, 3-221 등 이론 본문이 빠졌음).
- 크기: 청크는 페이지를 넘지 않는다. 제목이 바뀌면 새 청크, `CHUNK_MAX_CHARS`(800) 넘으면 문단(원문 한 줄) 단위로 나누고 `CHUNK_OVERLAP_CHARS`(120)까지 겹침, `CHUNK_MIN_CHARS`(80) 미만 끝 조각은 앞 조각에 합침. 문단 하나가 더 길면 자르지 않음. 본문 없는 묶음(장·절 제목, 학습목표)은 같은 페이지 다음 묶음 앞에 붙인다.
- 검수 표시: clean_text가 `CHUNK_REVIEW_MAX_CHARS`(80) 미만이고 제목 줄을 뺀 본문의 한글 비율이 `CHUNK_REVIEW_MIN_HANGUL_RATIO`(0.3) 미만이면 행은 만들되 `needs_review=true`, `review_reasons=["short_low_hangul"]` → `v_searchable_theory`에서 빠진다(R 출력·그림 글자 조각, 3과목 11개).
- 원문 위치 저장 형식(**팀 규격 미정, 이 형식 사용**): 2026-09-30 `col_description` 확인 결과 `theory_chunks.source_alignment`, `excluded_sections.source_region_ids`에 주석 없음(주석은 `raw_text`에만 있음).
  - `theory_chunks.source_alignment = {"method": "page_text_lines", "path": [제목 경로], "line_range": [시작, 끝]}` (추출 결과 줄 번호, 0부터, 끝 포함)
  - `excluded_sections.source_region_ids = [{"type": "page_text_lines", "text_uri": 추출 결과 URI, "line_range": [시작, 끝]}]` → text_uri의 줄을 잘라 기출 텍스트 복원 가능
  - 페이지 요약은 `page_metadata.chunking`(source, chunk_count, needs_review_count, excluded, dropped_lines, prev_state, end_state)
- 재실행: 페이지 단위 트랜잭션으로 그 페이지의 theory_chunks와 `exam_question` 제외 구간을 지우고 다시 넣는다(임베딩도 사라지므로 embed 재실행 필요).
- 상태(사용자 확정): detect_visuals는 구현 전까지 건너뛰고 `page_metadata.pipeline.skipped=["detect_visuals"]` 기록. chunk_theory 후 **VERIFIED**, embed 후 **EMBEDDED**. EXTRACTED에 두면 324쪽 전부 quality_passed=false로 검수 대기열을 채우기 때문. 검색 뷰는 페이지 상태를 보지 않는다. 나중에 detect_visuals는 visual_assets만 추가하므로 상태를 되돌리지 않는다.
- 알려진 한계: 표·그림이 한 줄로 합쳐진 텍스트는 그대로 청크에 들어간다(시각자료 단계에서 보완). 2과목 101쪽 첫 줄 "[34회 출제] [해설 …" 조각은 앞 쪽 블록이 "학습정리"로 끝난 뒤라 청크에 남음.

## D-020 임베딩: sentence-transformers 6.1.0 + BAAI/bge-m3(dense, 정규화), 캐시 E:, 검색은 v_searchable_theory (2026-09-30)
- 모델: **BAAI/bge-m3**, MIT 라이선스, 1024차원, 최대 8192 토큰. 모델 카드에 dense 임베딩 사용법으로 FlagEmbedding(`BGEM3FlagModel`)과 sentence-transformers(`SentenceTransformer("BAAI/bge-m3")`) 둘 다 제시. 출처: https://huggingface.co/BAAI/bge-m3 (확인 2026-09-30)
- 라이브러리: **sentence-transformers 6.1.0**(2026-09-18, Apache-2.0, Python>=3.10). 의존성으로 **torch 2.14.0**(PyPI Windows wheel = CPU 빌드, `2.14.0+cpu` 확인), transformers 5.17.0. 출처: https://pypi.org/project/sentence-transformers/ , https://pypi.org/project/torch/ (확인 2026-09-30). `uv add "sentence-transformers==6.1.0"`
  - FlagEmbedding 1.4.2는 PyPI 메타데이터에 라이선스 표기가 없어 쓰지 않음. sparse/ColBERT 출력이 필요해지면 재검토.
- 캐시 위치: huggingface_hub는 `HF_HOME`(기본 `~/.cache/huggingface`, 토큰·hub·xet 캐시 포함)과 `HF_HUB_CACHE`(기본 `$HF_HOME/hub`)를 **import 시점에** 읽는다. 출처: https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables (확인 2026-09-30)
  → `EMBEDDING_MODEL_DIR`(현재 `E:\hf_models`)을 `HF_HOME`으로 설정한 뒤 sentence_transformers를 지연 import하고, import 후 `huggingface_hub.constants.HF_HOME`이 설정과 다르면 오류로 멈춘다(C: 다운로드 방지). Windows 개발자 모드가 아니면 심볼릭 링크 대신 파일 복사(경고만, 동작 문제 없음).
- 정규화: 모델 카드에 명시 없음. 검색이 cosine(`vector_cosine_ops` HNSW, `<=>`)이므로 `normalize_embeddings=True`로 L2 정규화해 저장한다(사용자 요청).
- 입력: `theory_chunks.embedding_text`(제목 경로 + clean_text, D-019). 질문에는 접두어(instruction)를 붙이지 않는다(BGE-M3 모델 카드 예시와 동일). `EMBEDDING_MAX_SEQ_LENGTH`=1024 토큰(청크 약 800자), `EMBEDDING_BATCH_SIZE`=8, `EMBEDDING_DEVICE`=cpu.
- 저장: 임베딩하면 `embedding_enabled=true`, `needs_review=false`로 채운다. D-019의 needs_review=true 조각(짧은 비한글)은 임베딩하지 않는다(검토 후 승인되면 다시 embed).
- 상태: embed 후 EMBEDDED(D-019). 실행은 `run_stages --stages embed`(VERIFIED/EMBEDDED 페이지만), `--pages`로 쪽 제한.
- 검색 확인: `python -m app.retrieval.search "질문"`, 대상은 팀 규격 뷰 `v_searchable_theory`(embedding_enabled, embedding 있음, needs_review=false). 새 DDL 없음. Top-K는 `SEARCH_TOP_K`(5).
- 다운로드 크기(2026-09-30 확인): bge-m3 main에는 `pytorch_model.bin`(2.27GB)만 있고, transformers가 Hub PR(refs/pr/130)의 `model.safetensors`(2.27GB)를 추가로 받아 `E:\hf_models`가 약 4.3GB. C: 캐시는 늘지 않음(기존 `~/.cache/huggingface` 1.3GB는 09-29 이전 PaddleOCR·다른 프로젝트 것).

## D-021 팀 방향 변경: 공용 프론트 없이 각자 개인 프로젝트 (2026-09-30)
- 팀 공용 프론트는 만들지 않는다. 각자 백엔드와 프론트를 개인 프로젝트로 만든다(내 프론트는 `frontend/`, React + Vite).
- 공유 DB 서버와 팀 규격 테이블(`mingyu` 스키마)은 그대로다 → **기존 컬럼 이름 변경·삭제·타입 변경 금지, 컬럼/인덱스 추가만** 규칙은 유지한다(D-003의 근거였던 "공용 프론트 조회"는 없어졌지만 팀 규격 호환을 위해).
- `mingyu_app` 스키마와 API 설계는 자유(팀 규격과 맞출 필요 없음). DDL은 여전히 번호 붙은 마이그레이션 + 사용자 확인(CLAUDE.md).
- ARCHITECTURE의 프론트 관련 문구를 개인 프론트 기준으로 정리.
- → **'각자 개인 프로젝트' 방향(공용 프론트 없음·개인 프론트)은 D-M-030에서 변경**(팀원 3명이 이 저장소로 합류, `frontend/`도 팀 공동 작업). DDL 절차도 D-M-030에서 보완(마이그레이션 + PR + 팀 공지, 적용은 민규만). "기존 컬럼 변경 금지·추가만" 규칙은 그대로.

## D-022 검색 평가 기준과 실행 중단 처리 (2026-09-30)
- 적중 기준: 상위 K개 중 **정답 과목 book + 정답 인쇄 쪽** 청크가 있으면 적중(청크 id가 아니라 쪽 단위). 청킹을 바꿔도 같은 질문 세트를 그대로 쓸 수 있게 하기 위함. 정답 순위는 `EVAL_RANK_DEPTH`(20)까지 찾아 MRR도 함께 본다.
- "확인 불가" 임계값은 **1위 점수(cosine 유사도)** 하나로 평가한다(1위 ≥ t → 통과). 예시 6문항에서 자료에 없는 질문(0.524)이 교재 질문(0.515)보다 높게 나와, 점수만으로 못 가를 가능성이 있음 → 실제 세트 결과를 보고 답변 가능 판정(can_answer)·리랭커와 역할을 나눈다.
- 평가 스크립트는 DB를 읽기만 하고, 결과는 `data/reports/eval/`(gitignore)에 둔다. 질문 세트도 `data/eval/`(교재 쪽번호·내용 포함이라 커밋 안 함). → D-M-030에서 변경: 33문항 세트는 `eval/questions.csv`로 커밋(직접 지은 질문 + 쪽번호).
- 실행 중단: `run_pipeline`이 KeyboardInterrupt 등 `BaseException`을 받으면 run을 **FAILED**로 닫고(개수는 그때까지) 다시 던진다. 일부 성공이 있어도 PARTIAL이 아니라 FAILED로 두는 이유는 "끝까지 돌지 않은 실행"을 구분하기 위함. 창 닫기·kill은 잡을 수 없어 RUNNING이 남을 수 있으므로, RUNNING은 "실행 중일 수 있음"으로 보고하고 확인 전 재실행하지 않는다(/start).
- (2026-09-30 추가) 실제 세트 33문항 평가 결과, 답 가능·자료 없음의 1위 점수가 0.52~0.61에서 겹쳐 **cosine 1위 점수 임계값은 확정하지 않는다**. 리랭커를 붙인 뒤 리랭커 점수로 같은 세트를 다시 평가해 정한다. 질문 세트에는 "교재에 인접 주제는 있지만 답은 없는" 경계 사례(note `boundary`)를 넣어 임계값을 보수적으로 잰다.
- (2026-09-30 추가) 평가 HTML 보고서(`eval_report.py`)는 교재 페이지 썸네일을 포함하므로 `data/reports/eval/` 아래에만 두고 커밋하지 않는다. 청크 텍스트·이미지는 보고서 생성 시 DB/저장소에서 다시 읽는다(json에는 청크 id만).

## D-023 검색 평가의 정답 쪽 기준, "확인 불가" 2단계 판단 (2026-09-30)
- 정답 쪽 기준: **그 쪽만 보고 질문에 답할 수 있으면 정답 쪽에 포함**한다. 관련 내용이 있어도 질문이 실제로 묻는 것에 답이 안 되면 넣지 않는다. 이유: 쪽이 "관련 있음"만으로 정답에 들어가면 hit@K가 부풀려지고, 답변 생성에 쓸 근거인지와 어긋난다.
- 적용(33문항 평가 후 검토):
  - a06(알고리즘 피해자 구제 전문가 이름): p45 "데이터의 오용"에 "피해자를 구제할 수 있는 능력을 갖춘 전문가가 필요"는 있지만 이름(알고리즈미스트)이 없어 **제외**, 정답은 p52만.
  - c07(recall=sensitivity인지, specificity 뜻): p271 청크(needs_review 포함 1개)는 민감도(TPR)·특이도(TNR)·1-특이도(FPR) 정의는 있으나 "recall/재현율"이 한 번도 없어 "같은 거야?"에 답할 수 없음 → **추가 안 함**, 정답은 p268|269(p268 표에 "민감도(Sensitivity) = Recall(재현율)").
  - 결과적으로 정답 쪽 변경 없음 → 재평가 불필요, 수치는 20260930-195048 그대로.
- "확인 불가"는 2단계로 판단한다(ARCHITECTURE의 "확인 불가" 2단계 판단 절): 임베딩 1위 점수는 1차 거름망(아주 낮으면 LLM 호출 없이 바로 확인 불가), 겹치는 구간은 리랭커 점수 또는 판정기 can_answer. `JUDGE_PROVIDER=none`이면 리랭커 점수만. 값은 다음 세션에서 리랭커 점수로 평가 후 정한다(D-022 추가 사항과 같은 방향).

## D-024 리랭커: BAAI/bge-reranker-v2-m3, 후보 N=10, 입력 embedding_text, "확인 불가" 2단계 잠정값 (2026-09-30)
- 모델 정보(확인 2026-09-30, Hugging Face 모델 카드 + `https://huggingface.co/api/models/{repo}`):
  - `BAAI/bge-reranker-v2-m3`: Apache-2.0, 0.6B, bge-m3 기반 다국어 cross-encoder(XLMRobertaForSequenceClassification, 출력 1개). 카드 예시는 FlagEmbedding·transformers, `normalize=True`면 sigmoid로 0~1, 카드 예시 max_length 512(토크나이저 model_max_length 8192). HF 라이브러리 표기 sentence-transformers. 받은 커밋 953dc6f(2024-06-24), `model.safetensors` 2.27GB. 출처: https://huggingface.co/BAAI/bge-reranker-v2-m3
  - `dragonkue/bge-reranker-v2-m3-ko`: Apache-2.0, 0.6B, 위 모델을 한국어로 미세조정. 카드에 sentence-transformers `CrossEncoder` 사용법과 sigmoid 출력 명시, 평가는 한국 금융 도메인 벤치마크. 받은 커밋 2aca588(2025-04-03), 2.27GB. 출처: https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko
  - 로드: 설치된 sentence-transformers 6.1.0의 `CrossEncoder(name, max_length=, activation_fn=torch.nn.Sigmoid())`(출력 1개면 기본값도 Sigmoid — 설치본 `cross_encoder/model.py` docstring 확인). 새 의존성 없음. 캐시는 임베딩과 같은 `EMBEDDING_MODEL_DIR`→HF_HOME(`E:\hf_models`, 세 모델 합계 8.51GB). 다운로드는 사용자가 `hf download`로 미리 받음.
- 비교(같은 33문항, 정답 쪽 기준 D-023, K=5, CPU, 한 번에 리랭커 1개만 로드). 표의 hit@1은 답할 수 있는 26문항 기준:

  | 설정 | hit@1 | hit@3 | hit@5 | MRR | 과목별 hit@1(1/2/3) | 리랭크 시간 평균/최대(초) |
  |---|---|---|---|---|---|---|
  | 벡터만 | 21 (81%) | 25 | 26 | 0.881 | 7/8 · 8/8 · 6/10 | - |
  | v2-m3, N=20, embedding_text | 22 (85%) | 25 | 25 | 0.910 | 6/8 · 7/8 · 9/10 | 12.6 / 20.1 |
  | v2-m3, N=20, clean_text | 21 (81%) | 25 | 26 | 0.886 | 5/8 · 7/8 · 9/10 | 8.4 / 13.8 |
  | **v2-m3, N=10, embedding_text** | **22 (85%)** | **26** | **26** | **0.917** | 6/8 · 7/8 · 9/10 | **6.0 / 10.2** |
  | v2-m3, N=30, embedding_text | 22 (85%) | 25 | 25 | 0.910 | 6/8 · 7/8 · 9/10 | 14.6 / 26.9 |
  | -ko, N=20, embedding_text | 24 (92%) | 26 | 26 | 0.962 | 6/8 · 8/8 · 10/10 | 10.3 / 18.1 |
  | -ko, N=20, clean_text | 23 (88%) | 25 | 25 | 0.929 | 6/8 · 8/8 · 9/10 | 12.0 / 16.8 |
- 결정: **`BAAI/bge-reranker-v2-m3` + N=10 + 입력 embedding_text**.
  - `-ko`는 순위는 가장 좋지만, **점수를 "확인 불가" 판단에 쓸 수 없다**: 1위에 정답을 올리고도 점수가 0.000~0.05인 답 가능 질문이 6개(a05·b08·c02·c06·c07·c09, 입력을 clean_text로 바꿔도 비슷). 임계값을 0.01로 잡아도 답 가능 26개 중 6개를 막는다. v2-m3는 답 가능 1위 점수 최저 0.043, 자료 없음은 n08 말고 모두 0.005 이하라 분리된다. 두 모델을 동시에 올려 순위(-ko)·판단(v2-m3)을 나누는 방법은 RAM(여유 약 6GB)·시간 때문에 제외.
  - N=10이 N=20/30보다 낫다: N=20/30은 벡터 13~19위 청크가 리랭커로 올라와 c06(정답 벡터 1위)이 6위로 밀려 K 밖, n08(자료 없음)이 벡터 13위 DBSCAN 청크로 0.622를 받는다. 시간도 N에 비례.
  - embedding_text(제목 경로 + 본문)가 clean_text보다 두 모델 모두 순위가 좋다. 입력 토큰은 최대 545·중앙 약 270이라 `RERANKER_MAX_LENGTH`=1024에서 잘리는 쌍 0.
- 리랭커가 푼 것/못 푼 것(v2-m3, N=10, 벡터 → 리랭크 순위): c01 4→1, c02 3→1, c07 3→1, c09 2→1(용어 중의성·청킹 문제 질문 모두 1위). a06 2→2(p45 "데이터의 오용"이 여전히 1위, 이름이 없는 쪽 — D-023 기준 오답). 나빠진 것: a02 1→2, b02 1→2, c06 1→3. 3과목 hit@1 60%→90%, 1·2과목은 한 문항씩 내려감.
- "확인 불가" 2단계 값(**33문항 기준 잠정값**, 질문이 Claude 초안이라 실제 질문으로 다시 재야 함):
  - 1단계 `ANSWERABLE_MIN_VECTOR_SCORE=0.45`: 답 가능 벡터 1위 최저 0.516보다 충분히 낮게(먼 주제 n01 0.419만 걸러 리랭크 시간 절약). 0.50은 답 가능 최저와 0.016 차이라 리랭커 확인 없이 막을 위험이 있어 쓰지 않음.
  - 2단계 `ANSWERABLE_MIN_RERANK_SCORE=0.15`: 자료 없음 최고 0.131(n08, 경계 사례)과 답 가능 쪽 c07 0.208 사이 가운데. 결과 답 가능 24/26 통과, 자료 없음 7/7 차단. **보수적으로 잡은 대가**로 정답이 1위인데도 점수가 낮은 c06(0.043)·c09(0.066)는 "확인 불가"가 된다(두 정답 청크는 표·수식이 한 줄로 뭉친 청크 — p339 향상도 공식, p245~247). 0.05로 낮추면 c09를 살리지만 n08과의 차이가 줄어 택하지 않음.
  - `JUDGE_PROVIDER=none`에서는 이 두 값만으로 판단. 판정기(can_answer)를 붙이면 0.15 근처 구간을 판정기에 넘기는 방식을 다음 세션에서 검토.
- 속도: CPU에서 질문당 리랭크 평균 6.0초/최대 10.2초(N=10). 답변 흐름 지연에 그대로 더해지므로 화면에서 "검색 중" 표시 필요. 줄일 방법(ONNX 백엔드, fp16 불가한 CPU, N 축소)은 필요해지면 검토.
- (2026-09-30 보완, 사용자 결정) **"확인 불가"는 3구간으로 설계**한다(구현은 1-b 질의 흐름·1-c 판정기). 리랭커 1위 점수 < 하한(잠정 0.03) → 바로 "자료에서 확인 불가" / 하한~상한(잠정 0.15) → 회색 구간: 판정기 can_answer, `JUDGE_PROVIDER=none`이면 답변 + "근거 확신 낮음" 표시 / ≥ 상한 → 그대로 답변. 이유: 자료에 없는 질문은 n08(0.131) 외 모두 0.005 이하이고 답할 수 있는 질문 최저는 0.043이라, 0.15 하나로 자르면 c06·c09처럼 교재에 있는 내용을 없다고 답하게 된다. 두 값은 `.env` 설정값이며 33문항 기준 잠정값. 위 2단계 값(0.15에서 차단)은 3구간 구현 전까지의 현재 동작이다.
- (2026-10-01 측정, 1-b 첫 작업) **서버 메모리·단계별 시간**(임베딩 + 리랭커를 한 프로세스에 동시 로드, CPU, 33문항, RAM 16GB PC):
  - 프로세스 RSS: 시작 50MB → bge-m3 로드 756MB → 리랭커까지 3,219MB → 질문 처리 중 최대 **4,659MB**. 로드 직후 시스템 여유 RAM 약 4.2GB. 로드 시간 임베딩 21.8초 + 리랭커 18.4초.
  - 질문당(평균/중앙/최대 초): 임베딩 0.94 / 0.14 / **26.6**(첫 질문만 — 가중치 지연 로딩), 벡터 검색 0.44 / 0.42 / 0.62, 리랭크(N=10) 4.12 / 4.06 / 5.15. → 서버 시작 시 두 모델을 로드하고 **한 번씩 돌려 두기(워밍업)**로 결정(`app/qa/service.py`의 `load_qa_models`). 리랭크 시간은 어제 평가(평균 6.0초)보다 짧았다(PC 부하 차이로 보임).
  - **`RERANKER_MAX_LENGTH` 1024 vs 512**(evaluate --reranker BAAI/bge-reranker-v2-m3 --n 10, `.env` 값만 바꿈): 512에서 잘리는 쌍 2/330(최대 545토큰), hit@1 22/26·hit@3 26·hit@5 26·MRR 0.917·리랭커 1위 점수 분포 모두 **동일**, 리랭크 평균 4.25초(1024) vs 4.32초(512)로 차이 없음 → **1024 유지**(잘림 0, 손해 없음). 보고서 `data/reports/eval/20261001-091130`(1024), `20261001-091450`(512).
- 평가 결과 파일: `data/reports/eval/` 20260930-201321(벡터), -202649(v2-m3 N20), -203344(-ko N20), -203942(v2-m3 clean), -204741(-ko clean), -205236(v2-m3 N10, 채택), -210116(v2-m3 N30).

## D-025 질의 흐름: Gemini JSON 구조화 출력 + 인용 검증, query_logs.metadata 기록, 모델 사전 로딩 (2026-10-01)
- Gemini 구조화 출력(확인 2026-10-01): REST `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, 헤더 `x-goog-api-key`, `generationConfig.responseMimeType="application/json"` + `responseJsonSchema`. 응답 텍스트는 `candidates[0].content.parts[].text`, 토큰 수는 `usageMetadata`. gemini-3.5-flash-lite로 실제 호출해 JSON 응답 확인. 출처: https://ai.google.dev/api/generate-content , https://ai.google.dev/gemini-api/docs/structured-output (이 문서 예시는 새 Interactions API `v1beta/interactions` + `response_format`을 쓰지만 generateContent도 폐기 표시 없음 → 기존 generateContent 사용)
- HTTP 클라이언트는 SDK 대신 httpx(이미 dev 의존성, 본 의존성으로 이동). 새 SDK 의존성을 늘리지 않고 재시도·폴백(D-010)을 직접 제어하기 위함.
- 답변 JSON: unanswerable, answer(핵심 1~2문장), explanation, confusions, cited. 인용 번호는 코드로 1..K 범위 검사 → 밖이면 제거·기록. 프롬프트와 스키마 설명문은 `backend/app/prompts/`.
- 3구간 뒤 한 겹 더: 회색·답변 구간이라도 LLM이 근거에 답이 없다고 하면(unanswerable) "자료에서 확인 불가". 첫 샘플에서 n08(회색, 리랭커 0.131)이 이 겹에서 걸러짐.
- 기록: 팀 규격 query_logs의 기존 컬럼 + `metadata` JSONB(3구간 판정, 단계별 시간, 인용 검증 등). 컬럼 추가 불필요.
- 모델 사전 로딩: D-024 측정에서 첫 질문 임베딩이 26.6초(지연 로딩) → 서버 시작 시 임베딩·리랭커 로드 + 워밍업. 지연 로딩 경로는 두지 않고 `PRELOAD_MODELS=false`(테스트)면 /qa 503.
- 판정기는 아직 none만(`app/judge`의 get_judge). 다른 값이면 시작 시 NotImplementedError → 1-c에서 구현.
- (추가 2026-10-01) 답변 프롬프트 규칙: 근거 문장 하나가 말하는 내용만 한 문장으로, 서로 다른 근거 문장을 이어 붙이지 않음 / answer·explanation·confusions 모든 문장에 [n] / "~다"체. citation_check에 `uncited_sentences`(explanation·confusions별 인용 없는 문장 수)와 `uncited_sentence_count` 추가, `[1, 2]`처럼 한 괄호에 여러 번호를 쓴 인용도 인식. 효과는 형식(인용 없는 문장·문체)에서만 확인됐고 정답률 차이는 실행 간 흔들림 안(기출 객관식 15문제 비교, 민규 개인 평가 기록).
- (추가 2026-10-01, 팀 비교 준비) **답변 온도 `ANSWER_TEMPERATURE` 0.2 → 0 고정**. 이유: 기출 15문제 1회 실행에서 ±1~2문제가 실행마다 바뀌어(temperature 0.2) 수정 전후·팀 간 비교가 안 됐음. 0이어도 Gemini가 완전히 같은 답을 낸다는 보장은 없으므로 비교는 2회 실행으로 확인한다. 적용 후 기출 15문제 2회 실행에서 고른 번호·판정이 모두 같았다(인용 번호 구성만 3문제에서 조금 다름).
- 첫 샘플(10문항, 2026-10-01): 질문당 전체 5.7~7.4초(리랭크 3.4~5.1초, LLM 1.5~2.0초), 확인 불가(reject)는 0.5~4.4초. 토큰 약 2,000~2,750/질문. 결과 `data/reports/answers/20261001-091851.md`.

## D-026 페이지를 넘어 이어지는 코드 블록은 "청크는 페이지를 넘지 않음"(D-019)·페이지 단위 출처(D-014)의 예외 (2026-10-01, 설계만)
- 배경(팀원 피드백 + DB 읽기 전용 조사 2026-10-01): 교재 R 코드가 페이지를 넘어 이어지는 경우가 있고, 지금은 청크가 페이지에서 끊겨 뒷부분 출력 조각이 needs_review(검색 제외)가 된다. 3과목에서 엄격 기준(앞 페이지 마지막 본문 줄·다음 페이지 첫 본문 줄이 모두 코드, 사이 제목 없음) 9건(실제 코드 이어짐 6, 그래프 글자 3), 완화 기준(앞뒤 3줄 안) 41건(눈으로 본 잠정 분류: 코드·출력 이어짐 약 18, 앞 예제 끝·다음 예제 시작 4, 그래프·수식 글자 오검출 19). 1과목 0건, 2과목은 완화 기준 1건(도식, 오검출). 뒷부분 첫 청크가 needs_review인 건 3건(135·142·143쪽, 모두 "R 기초" 단원) — 전체 needs_review 11개 중 3개.
- 결정(설계, 구현은 GitHub Issues "청킹 보완"):
  - 코드 블록 인식 규칙 + 페이지 넘김 이어짐 판단(마지막 본문 줄·다음 첫 본문 줄이 코드, 사이에 제목 없음, "예제N"·기출 블록으로 시작하면 이어짐 아님)
  - **이어진 코드 블록만** 한 청크로 합친다. `page_id`는 시작 페이지, 전체 페이지·줄 범위는 `source_alignment.spans`(JSONB, 컬럼 추가 없음), 출처는 "226~227쪽"처럼 범위로 표시. D-014의 "청크 출처는 페이지 단위"는 이 경우만 "페이지 범위"로 바뀐다. 그 밖의 본문은 여전히 페이지를 넘지 않는다.
  - 코드와 실행 결과는 같은 청크, 출력만 떨어진 조각을 만들지 않는다.
  - 코드 청크 embedding_text = 제목 경로 + 코드 앞 설명 문장 + 코드. 설명이 부족할 때만 Gemini 설명문을 embedding_text에 추가(원문 필드에는 넣지 않음).
  - 시각자료 crop(D-016)도 같은 원칙: 페이지를 넘는 코드·표는 두 crop을 세로로 이어 붙여 하나로, 페이지 범위를 기록.
- 이유: 코드는 앞 대입·호출과 뒤 출력이 함께 있어야 뜻이 통하고(출력 조각만으로는 검색·답변 근거가 안 됨), 시험 문제도 "아래 R 코드 출력 결과는?" 형태로 코드+출력을 함께 묻는다. 일반 본문까지 페이지를 넘기면 출처 표시와 재청킹 범위가 복잡해지므로 예외는 코드 블록(필요하면 표)으로 한정한다.
- 주의: 팀 텍스트에는 그래프 축 눈금·수식 조각이 한 줄로 섞여 있어 숫자·기호 줄만으로는 코드와 구별되지 않는다(조사의 오검출 원인). 출력 줄은 코드 줄이 앞에 있는 블록 안에서만 인정한다. 규칙은 구현 시 같은 조사 스크립트로 오검출을 다시 확인한다.


## D-027 객관식 문제는 보기별로 판단하고, 부정형은 "어긋남 > 근거 없음 하나" 순으로 고른다 (2026-10-01)
- 배경: 기출 15문제 기준선에서 확인 불가 4~5개가 모두 "보기 하나라도 근거로 판별 못 하면 전체 거절"(LLM 판단 오류)이었다. p56-1은 정답 보기를 반박하는 문장을 설명에서 인용하고도 거절했다. 팀 비교 전에 데이터와 무관한 이 거절을 줄인다. 검색·"확인 불가" 3구간 로직은 바꾸지 않고 **답변 프롬프트만** 고친다.
- 규칙(`backend/app/prompts/answer_system.txt` 규칙 8, 규칙 2에 "객관식은 규칙 8" 예외)
  - 보기마다 근거와 대조한다(뒷받침 / 정면으로 어긋남 / 근거에 없음). 보기 하나가 근거에 없다는 이유만으로 전체를 거절하지 않는다.
  - 부정형("옳지 않은/적절하지 않은/틀린/아닌 것"): 1순위로 근거와 정면으로 어긋나는 보기를 고르고 어긋나는 근거를 [n]으로 인용한다. 2순위는 어긋나는 보기가 없을 때만 적용하며, 나머지가 모두 뒷받침되고 하나만 근거에 없으면 그 보기를 고른다. 어긋나는 보기가 없고 근거에 없는 보기가 둘 이상이면 unanswerable로 한다.
  - 2순위를 좁게 둔 이유(사용자 결정): 검색 K=5라 보기가 검색에 안 걸렸을 뿐인데 "근거 없음"이 될 수 있다. 거절이 오답으로 바뀌는 것을 피한다.
  - 긍정형: 근거가 뒷받침하는 보기 하나를 고르고, 하나로 정할 수 없으면 unanswerable로 한다.
  - 풀이 형식: answer는 "정답은 ③이다 [n]." 한 문장이다(1~4, (1)~(4)로 와도 ①~④로 씀). explanation은 보기마다 한 줄씩 "①은 ~이므로 적절하다 [n]."로 쓰고, 근거 없는 보기는 "③은 근거에서 확인되지 않는다."라고 인용 없이 쓴다(지어내지 않음).
- 인용 검사: `count_uncited_sentences`는 "①은/는 근거에서 확인되지 않는다" 형태의 보기 줄을 인용 없는 문장으로 세지 않고 `citation_check.unsupported_option_sentences`로 따로 센다. 문구가 달라지면(예: "근거에 없어 확인되지 않는다") 그대로 인용 없는 문장으로 센다.
- 채점(`app/qa/mcq_run.py`): 답의 "정답은 X"에서 번호를 뽑는다(①~④ / 1~4 / (1)~(4)를 같은 번호로 봄). 정답 번호와 같으면 맞음, 다르면 틀림이다. 거절했거나 번호를 못 뽑으면 "검토 필요"로 두고, 사람이 `{시각}.grades.json`에 이유(note)와 함께 수동 채점한다. 수동 채점은 자동 채점보다 우선한다. `compare` 명령은 여러 실행과 기준선을 한 표로 비교한다.
- 결과(같은 15문제, 온도 0, 2회 실행): **맞음 12 / 틀림 0 / 확인 불가 2 / 모호 1**(80%, 두 실행 동일). 수정 전 기준선(20261001-171504)은 맞음 9 / 틀림 0 / 확인 불가 5 / 모호 1이었다.
  - 풀린 거절: p26-2·p56-1·p99-1. 3과목 p232-1은 모호에서 맞음이 됐다.
  - 남은 거절: p26-3(근거 p27 데이터 마트 문장과 ④가 어긋나는데도 거절, 기준선에서는 흔들려 맞음/거절), p50-2(사례 연결형, 근거가 약함)
  - 알려진 한계: p84-1은 ①·② 둘 다 "근거에 없다"고 쓰고도 ①을 골랐다(정답과 같지만 규칙 위반, 수동으로 "답이 모호함"). 프롬프트 규칙만으로는 2순위 조건을 완전히 지키지 못한다 → 판정기(Jev) choice나 코드 검사(근거 없는 보기 줄 수 ≥ 2이면 거절) 후보
- 일반 질문 영향: 10문항 샘플의 판정(답변 7 / 확인 불가 3)과 인용 쪽은 이전과 같았다(`data/reports/answers/20261001-182909`).

## D-028 판정기 Jev(can_answer)는 회색 구간에서 질문 + 근거 K개로 부르고, 객관식 모순은 코드로 검사한다 (2026-10-01)
- 대상: "확인 불가" 3구간의 회색 구간(리랭커 1위 0.03~0.15, D-024)에서만 부른다. 구간 경계는 지금처럼 config(`ANSWERABLE_*`)에서만 읽는다.
- 보내는 것: **질문 + 근거 K개(5개)**. Gemini에 넘기는 근거와 같은 묶음이다. 질문만으로는 "근거로 답할 수 있는가"를 판단할 수 없기 때문이다.
  - `state = {"question", "evidence": [{n, page, path, text=clean_text}]}`, `questions.can_answer` = noul 질문(`prompts/judge_can_answer.json`의 instructions + criteria.true/false), `model = JEV_MODEL`
  - 공식 문서 재확인(2026-10-01): noul 응답 값은 "예일 확률(0=아니오, 1=예)", 오류 401/422/429/529, 429·529는 지수 백오프 재시도 권장. 출처: https://docs.typesafe.ai/api.md , https://docs.typesafe.ai/primitives/noul.md
- 분기(잠정값, 재적재 후 조정): 확률 < `JUDGE_CAN_ANSWER_MIN`(0.5) → "자료에서 확인 불가"(Gemini를 부르지 않음) / 그 이상 → 답변, 그중 ≥ `JUDGE_CONFIDENT_MIN`(0.8)이면 "근거 확신 낮음" 해제. 판정기 오류(시간 초과, 재시도 소진, 401 등)는 none과 같은 동작(답변 + 확신 낮음)을 하고 이유를 기록한다.
- 재시도: 429/529/5xx/시간 초과만 `JUDGE_MAX_RETRIES`(2)번, 대기 `JUDGE_RETRY_BASE_SECONDS`×2^(n-1). `.env`의 `JEV_ENABLED`는 `JUDGE_PROVIDER`와 역할이 겹쳐 쓰지 않는다.
- 기록: `query_logs.metadata.judge` = {provider, question_key, input(question, evidence_n), model, probability, can_answer, confident, thresholds, latency_ms, usage, attempts, error}. 확률값은 재적재 후 임계값 재조정 자료라 오류가 아니면 항상 남긴다. 판정기 시간은 `timings_ms.judge_ms`(total에 포함)와 `judge.latency_ms`. 확신 낮음 이유는 `low_confidence_reasons`(gray_no_judge / gray_judge_error / gray_judge_not_confident / no_valid_citation / mcq_inconsistent).
- **judgments 테이블은 이번에는 쓰지 않는다(사용자 결정).** 제약 조회(2026-10-01, 읽기 전용) 결과 `solution_id`·`problem_id`는 NULL 허용이고 둘 중 하나를 강제하는 CHECK·트리거가 없어 행은 들어간다. 하지만 query_logs를 가리키는 컬럼이 없어 어느 질문의 판정인지 연결할 수 없다 → DDL을 바꾸지 않고 query_logs.metadata에만 기록하고, 화면 단계에서 solutions를 저장할 때 solution_id로 연결해 쓰기 시작한다.
- 실제 호출(2026-10-01, c06·c09·n08, 예상과 일치): c06 확률 0.92(247ms) → 답변, 확신 높음, 정답 쪽 247 인용 / c09 0.94(196ms) → 답변, 확신 높음, 정답 쪽 339 인용 / n08(자료 없음) 0.06(236ms) → 확인 불가(Gemini 미호출). 입력 1,846~2,505토큰·출력 21토큰, 응답 모델 jev-1.13.0. 판정기 시간은 /qa 전체(6.0~7.2초)의 약 3~4%. 결과 `data/reports/answers/20261001-190235`.
- **객관식 일관성 검사**(`app/qa/mcq_check.py`, D-027 한계 p84-1 보완, Jev가 아니라 코드로):
  - 보기 줄("①은 …")마다 판정을 뽑는다: 판정 표현이 있는 첫 문장의 마지막 표현. 적절하다(옳다·올바르다·맞다·해당한다) / 적절하지 않다(옳지 않다·올바르지 않다·부적절하다·틀리다·어긋난다·해당하지 않는다) / 확인되지 않는다(확인할 수 없다). "첫 문장"으로 좁힌 이유: 2회차 실행 p84-1처럼 ① 줄 뒤에 "[1]은 … ③은 적절하다"가 이어 붙으면 뒤 문장 판정을 가져왔다.
  - 부정형(문제 본문에 적절하지 않은/옳지 않은/올바르지 않은/부적절한/틀린/아닌 것/해당하지 않는): '적절하지 않다'가 정확히 하나이고 고른 번호와 같아야 한다. 긍정형: '적절하다'가 정확히 하나이고 고른 번호와 같아야 한다. 고른 번호의 줄이 '확인되지 않는다'이면 모순.
  - 모순이면 답을 거절로 바꾸지 않고 "근거 확신 낮음" + `metadata.mcq_check`(negative, chosen, option_verdicts, consistent, reasons).
  - 저장된 결과 재검사(`mcq_run check`, Gemini 호출 없음): 20261001-183237·183551 두 실행 모두 **p84-1만 걸림**(정답 번호와 같지만 수동 채점 "답이 모호함"인 문제). 나머지 답변 12개는 통과, 거절 2개는 검사 대상 아님.
  - 범위 밖: 판정 이유와 결론이 맞지 않는 줄(예: p99-1 ④ "근거에 없으므로 적절하다")은 보지 않는다(규칙 추가 안 함).
- **판정기 켜기(2026-10-01, 사용자 결정)**: `.env`를 `JUDGE_PROVIDER=jev_typesafe`로 바꿨다(`.env.example`은 키 없이도 동작하도록 none 유지). 이유: 실제 호출 c06·c09·n08 3건 모두 예상과 일치, 판정기 시간 약 0.2초(/qa 전체의 3~4%), 오류 시 none과 같은 동작(답변 + 확신 낮음), 임계값 0.5/0.8은 재적재 후 다시 잡을 잠정값이라 켜 둔 채 `metadata.judge.probability`를 모은다. 켠 뒤 화면 확인(2026-10-01): c06 확률 0.93(232ms) → 답변·확신 높음·247쪽 인용, n08 0.05(226ms) → 확인 불가.

## D-029 최소 공부 화면: Vite 8 + React 19 + TypeScript, 개발 서버 프록시, 검색 대상 선택은 컴포넌트 하나로 분리 (2026-10-01)
- 버전(2026-10-01 확인): create-vite 9.2.1(`npm create vite@9.2.1 . -- --template react-ts`), vite 8.3.2, react 19.3.0, typescript 6.0.3, @vitejs/plugin-react 6.1.x, 린트는 템플릿 기본 oxlint. Vite 요구 Node 20.19+ / 22.12+ → 설치된 Node 24.19.0(npm 11.17.0)으로 충족. 출처: https://vite.dev/guide/ , `npm view vite version`·`npm view vite engines`(npm 레지스트리). 추가 라이브러리(라우터·UI 키트) 없음.
- CORS: 백엔드는 고치지 않고 Vite 개발 서버 프록시로 `/qa`, `/subjects`를 넘긴다. 백엔드 주소는 `frontend/.env`의 `VITE_API_TARGET`(기본 http://127.0.0.1:8000). 배포·빌드 결과 서빙 방식은 화면 전체 구성을 팀과 정할 때 다시 본다.
- 범위: "질문 입력 → 답변과 근거 표시" 한 화면만. 상단바·사이드바·업로드 탭은 팀과 정한 뒤.
- 검색 대상 선택: `SourceSelector`(value/onChange만 노출)로 분리. 지금은 과목 목록(`GET /subjects`)이지만 `/qa`에 과목 필터가 없어 **선택값을 보내지 않는다**(사용자 승인, 화면에 "현재 검색은 전체 자료 대상" 표시). 나중에 "업로드한 자료(문서) 선택"으로 이 파일만 바꾼다.
- 오류 표시: 백엔드가 꺼져 있으면 Vite 프록시가 본문 없는 502를 돌려준다(2026-10-01 확인) → JSON 없는 5xx나 fetch 실패는 "서버에 연결할 수 없습니다(백엔드 실행 확인)". `VITE_QA_TIMEOUT_SECONDS`(60초)를 넘기면 요청을 끊고 "응답 시간이 초과됐습니다". 처리 중 질문 버튼 비활성화 + 경과 초 표시. 백엔드 503 등 JSON detail이 있으면 그 문구를 보여 준다.
- 표시 규칙(내용은 바꾸지 않고 나누기만): 본문 [n]은 근거 카드 링크. 객관식(`mcq_check` 있음)이면 answer("정답은 ③이다")를 강조 상자로, explanation은 백엔드 `option_lines`와 같은 규칙(글 처음·줄바꿈·".", "]", "다" 뒤의 "①은")으로 보기 줄을 나눠 판정(option_verdicts)과 함께 표시, 고른 번호 줄 강조. 확신 낮음 이유 코드는 사람이 읽는 문구로(`ConfidenceNotice.tsx`), mcq_inconsistent면 `mcq_check.reasons`도 나열. 근거는 인용된 것만 펼치고(raw_text 원문, 책·쪽·제목 경로) 나머지는 접기. 개발 확인용 `DevInfo`(구간·점수·판정기 확률·시간·query_log_id)는 작은 회색 글씨.
- 알게 된 것: `/qa` 응답의 `evidence[].page`는 문자열이다(printed_page_number) → 타입은 string | number.


## D-M-030 팀 합류 준비: 저장소는 팀 공유로, 개인 기록은 추적 해제, 서비스 스키마는 mingyu 유지 (2026-10-01 계획, 2026-10-06 실행 `chore/team-onboarding`. 처음 번호는 D-030)
- 배경: 팀원 3명(데이터·프론트·백엔드 기능)이 각자 프로젝트를 접고 이 저장소로 합류한다(D-021의 "각자 개인 프로젝트"를 대체). 협업은 기능 브랜치 → PR → main, PR마다 pytest·npm build·lint 자동 실행. 기출은 DB에 넣지 않고 이론만 근거로 쓰며, 기출 평가 세트는 평가 파일로만 둔다. 피드백 저장(solutions + judgments)은 재적재 이후로 미룬다.
- 조사 결과(읽기 전용): 커밋 39개에 `data/`·`.env`가 들어간 적 없고, `.env` 비밀값·키 패턴의 기록 등장 0건 → 기록 재작성 없이 추적 해제만 한다. DB 접속 불가 조건에서 테스트 2개(`test_pool_connection_does_not_leak_search_path`, `test_qa_api`)가 건너뛰지 않고 실패 → CI 전에 수정. `uv.lock`에 nvidia 패키지 43개(Linux에서 CUDA torch).
- 결정(사용자):
  - A. 서비스 스키마는 mingyu·mingyu_app 유지. 데이터 담당 결과물은 DB가 아니라 공통 JSON 파일로 받는다. 각자 실험용 스키마는 본인만, 서비스 스키마 변경은 `backend/migrations/` 번호 파일 + PR + 팀 공지, 재적재·DDL 적용은 민규만. DB 서버는 보안 그룹으로 팀원 IP만 허용(민규가 AWS에서 설정).
  - B. PROGRESS·sessions는 추적 해제만(기록은 이전 커밋에 남음). README에 "현재 상태" 5줄 요약, 남은 작업은 GitHub Issues(웹에서 직접 생성).
  - C. 평가 질문 33문항은 `eval/questions.csv`로 커밋(직접 쓴 질문 + 쪽번호). 커밋 전 정답 표시가 쪽번호 기준인지 확인. 기출 원문은 커밋하지 않는다.
  - D. CI의 torch는 정리 PR 머지 직후 별도 PR로 pytorch-cpu 인덱스 적용(확인 2026-10-01, https://docs.astral.sh/uv/guides/integration/pytorch/ — `[tool.uv.sources]` + `[[tool.uv.index]] name="pytorch-cpu" url="https://download.pytorch.org/whl/cpu" explicit=true`). `uv.lock`이 바뀌므로 Windows 로컬 재설치와 실제 모델 테스트로 확인. → **D-M-031에서 적용**
  - main 보호: 무료 비공개 저장소는 보호된 브랜치를 쓸 수 없다(사용자 확인, GitHub 문서 "About protected branches" https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches — 이 세션의 문서 조회에서는 해당 문장을 직접 찾지 못함) → README에 팀 약속 "main 직접 push 금지, PR + CI 통과 후 머지".
- CLAUDE.md 분리: 팀 규칙은 `CLAUDE.md`(커밋), 개인 지침(세션 시작·완료 루틴, /start·/wrap, 개인 경로)은 `CLAUDE.local.md`(gitignore). 공식 문서 확인 2026-10-01: "For private per-project preferences that shouldn't be checked into version control, create a `CLAUDE.local.md` at the project root. It loads alongside `CLAUDE.md`… Add `CLAUDE.local.md` to your `.gitignore`" (https://code.claude.com/docs/en/memory).
- CI에서는 실제 모델 테스트(addopts로 제외)와 DB 테스트(닿지 않는 가짜 DB 값 → 건너뜀)를 돌리지 않는다. 공유 DB 정보는 GitHub Secrets에 넣지 않고 DB 테스트는 PR 전 로컬에서 돌린다.
- API 계약은 `docs/API.md`(사람이 씀) + FastAPI `/docs`·`/openapi.json`. API를 바꾸는 PR은 API.md도 같이 고친다.
- 실행 결과(2026-10-06, `chore/team-onboarding`):
  - 결정 번호를 이니셜 체계로 바꿨다(이 항목 D-030 → D-M-030, 규칙은 문서 맨 위). 팀 문서 `docs/team/` → `docs/guides/`, 새 README·`docs/API.md`·`eval/questions.csv`(정답 표시가 인쇄 쪽번호 기준임을 `evaluate.py`의 printed_page_number 비교로 확인), `EVAL_QUESTIONS_PATH` 기본값 `eval/questions.csv`.
  - DB 없는 조건의 테스트: `test_pool_connection_does_not_leak_search_path`는 `db_conn` fixture를 받아 건너뛰고, `test_qa_api`는 `get_conn`을 가짜 커넥션으로 바꿔 DB 없이도 실행한다(검색·기록이 이미 가짜). 가짜 DB 값으로 107 통과 / 20 건너뜀 / 실패 0, 로컬 DB로 127 통과.
  - CI `.github/workflows/ci.yml`: backend(ubuntu, `astral-sh/setup-uv@v10` Python 3.12, `uv sync --locked`, `uv run pytest`, 가짜 DB 값·`JUDGE_PROVIDER=none`·`PRELOAD_MODELS=false`) / frontend(`actions/setup-node@v7` Node 24, `npm ci`·lint·build). 액션 버전은 GitHub API 최신 릴리스로 확인(2026-10-06: actions/checkout v7.0.1 https://github.com/actions/checkout/releases, astral-sh/setup-uv v10.2.0 https://github.com/astral-sh/setup-uv/releases, actions/setup-node v7.0.0 https://github.com/actions/setup-node/releases). torch CPU 인덱스는 D 결정대로 다음 PR — 그 전까지 백엔드 CI가 CUDA torch로 느리거나 실패할 수 있다(사용자 결정: 원인이 이것이면 머지 가능).


## D-M-031 torch는 PyTorch CPU 인덱스에서 받는다 (2026-10-06, `chore/torch-cpu-index`)
- 배경: torch는 `sentence-transformers==6.1.0`을 통한 간접 의존이었고, `uv.lock`은 PyPI의 torch 2.14.0을 가리켰다. PyPI Linux 휠은 CUDA 빌드라 Linux(CI 포함)에서 `nvidia-*` 16개·`triton`·`cuda-*` 3개, 합계 19개(Linux x86_64 약 2.45GB, torch 휠 555MB 별도)가 함께 설치됐다. 이 서비스는 임베딩·리랭커를 CPU로 돌린다(`EMBEDDING_DEVICE`·`RERANKER_DEVICE` 기본 cpu). Windows PyPI 휠은 원래 CPU 빌드(`2.14.0+cpu`)라 로컬에는 차이가 없었다. CI backend의 `uv sync --locked`는 36~70초가 걸렸다(그중 다운로드·준비 33초, uv 캐시는 prune돼 매번 새로 받음).
- 결정: `pyproject.toml`에 `torch==2.14.0`을 직접 의존으로 추가하고, `[tool.uv.sources] torch = [{ index = "pytorch-cpu" }]` + `[[tool.uv.index]] name = "pytorch-cpu"`, `url = "https://download.pytorch.org/whl/cpu"`, `explicit = true`로 둔다. `explicit`이라 torch만 이 인덱스에서 받고 나머지는 PyPI에서 받는다. torch 버전은 그대로 2.14.0.
- 출처(확인 2026-10-06): uv PyTorch 연동 문서 https://docs.astral.sh/uv/guides/integration/pytorch/ (CPU 전용 예시, "macOS는 PyPI로"는 CUDA 인덱스를 쓸 때의 안내), CPU 인덱스 휠 목록 https://download.pytorch.org/whl/cpu/torch/ (2.14.0 cp312: win_amd64·win_arm64·manylinux x86_64/aarch64·s390x는 `+cpu`, macosx_14_0_arm64는 `2.14.0`). macOS arm64 휠도 CPU 인덱스에 있으므로 marker로 플랫폼을 나누지 않는다. uv 문서에서 source가 간접 의존에도 적용되는지는 확인하지 못해, 공식 예시처럼 직접 의존으로 추가했다.
- 대안:
  - PyPI 유지: Linux·CI에서 쓰지 않는 CUDA 패키지 약 2.7GB를 계속 받는다.
  - Linux에만 marker로 CPU 인덱스 적용: 결과는 거의 같지만 설정만 복잡해진다(macOS도 CPU 인덱스에 휠이 있음).
  - CUDA 인덱스 사용: GPU 서버 계획이 없어 필요 없다.
- 결과(`uv lock`): `cuda-bindings`·`cuda-pathfinder`·`cuda-toolkit`·`nvidia-*` 16개·`triton` 제거(패키지 이름 127 → 108개, torch 항목이 2개라 lock 항목은 109개). torch는 `2.14.0+cpu`(Windows·Linux) + `2.14.0`(macOS) 두 항목으로 나뉘고, 출처는 둘 다 `https://download.pytorch.org/whl/cpu`. 다른 패키지 버전 변경 없음. 로컬 Windows는 `torch 2.14.0+cpu`, `cuda.is_available() False`. 같은 질문의 bge-m3 임베딩(코사인 1.0, 최대 차이 0)과 리랭커 점수 4개(차이 0)가 변경 전과 같다. 기본 pytest 127 통과, 실제 모델 테스트 3개(임베딩·리랭커·OCR) 통과.
- 영향:
  - 팀원은 머지 후 `uv sync`를 한 번 실행한다(`uv run`도 자동으로 동기화한다). Windows는 torch만 다시 받는다(약 118MB). 모델 캐시(`EMBEDDING_MODEL_DIR`)는 그대로 쓴다.
  - Linux에서 NVIDIA GPU가 있어도 CUDA를 쓸 수 없다(지금 설정은 CPU라 기능 영향 없음). GPU가 필요해지면 CUDA 인덱스를 marker로 추가하는 결정을 새로 한다.
  - Intel Mac(x86_64)은 torch 2.14.0 휠이 PyPI·CPU 인덱스 모두에 없다(이번 변경 전에도 같음).
  - torch를 직접 의존(==2.14.0)으로 고정했으므로, sentence-transformers 등 torch를 쓰는 패키지를 올릴 때는 torch 버전도 함께 확인·조정할 것.


## D-M-032 공통 JSON은 mingyu_app의 새 테이블(documents·blocks·block_relations)에 블록 단위로 적재하고, 기존 데이터와 비교한 뒤 교체한다 (2026-10-07, `feat/common-json-loader`)
- 배경: 지금 DB의 이론 청크(theory_chunks 616개)는 text.zip(교재 사진 OCR) 기반이라 표 뭉침·그래프 글자 섞임이 있다(2026-10-01 DB 소스 확인). 데이터 담당(수민)이 정제한 공통 JSON 1·2과목 최종본(1과목 163블록 format 1.7, 2과목 227블록 format 1.6, 블록·관계·manifest·validation_report)을 받았다. 바로 바꾸지 않고 따로 넣어 33문항·기출로 비교한 뒤 교체 여부를 정한다.
- 조사(읽기만):
  - 블록 종류 theory 311 / table 37 / visual 42. 이론만 `block_role`(content / learning_objective 23)이 있고 표·시각자료는 없다. 일부 블록에만 있는 필드(`subject_name`, `clean_correction_note`, 관계의 `relation_scope`)가 있어 버전으로 분기하지 않고 필드가 있으면 쓰는 방식으로 읽는다.
  - 표 중복 이론은 블록의 `duplicate_of_table_id` 필드로 판단한다(1과목은 필드 7개인데 같은 관계는 1개). 값은 전체 block_id가 아니라 source_id(`TAB_104_01`)라 같은 과목의 `S{n}:TABLE:`로 풀어 쓴다.
  - 표 `rows`는 병합 셀 값이 대부분 이미 채워져 있고 TAB_79_01만 빈 칸 1개를 `merged_cells`로 채워야 한다. `headers`가 빈 표(최종본 기준 TAB_104_01)는 첫 칸이 행 이름이다. 행 이름은 `rows` 첫 칸에 이미 들어 있으므로 `row_headers`는 쓰지 않는다(첫 판의 TAB_119_01은 `row_headers` 2개·행 7개로 달랐고, 최종본은 `[구분, 구성요소]` 2열 2행).
  - 팀 규격 테이블(theory_chunks·visual_tables·visual_assets)도 필드가 비슷하지만 visual_tables에 임베딩 컬럼이 없고, visual_type CHECK에 없는 값(`composite_diagram_table`, `process_flow`)이 있으며, pages.source_s3_uri가 NOT NULL이고, 이론↔표·이론↔이론 관계를 둘 곳이 없다. 무엇보다 theory_chunks에 넣는 순간 지금 /qa·평가 검색(v_searchable_theory)에 섞인다.
- 결정(사용자 승인 2026-10-07):
  - DB: `004_common_json_blocks.sql`로 mingyu_app에 `documents`(문서 단위: document_key 고유, corpus, subject, subject_no, title, format_version, 같은 교재의 기존 book_id, manifest·pages·page_relations), `blocks`(block_id 고유, 블록 종류·block_role·쪽·제목 경로·raw/clean·표·시각자료·이미지 S3 키·model_generated·review, 원본의 나머지 필드는 `source`, `search_enabled`·`search_excluded_reason`, 임베딩 vector(1024)·embedding_text·해시, content_hash, processing_run_id), `block_relations`((from_block_id, to_block_id) 고유, relation_source·relation_types·link_type 보존), 뷰 `v_searchable_blocks`. 팀 규격 테이블은 바꾸지 않는다(books·processing_runs는 FK 참조만). 적용은 민규가 PR 머지 후.
  - 블록 1개 = 검색 단위 1개(합치지 않음). 블록 길이: 이론 임베딩 텍스트 중앙값 212자·최대 754자, 표 최대 1,708자, bge-m3 토큰 최대 813(TAB_82_01)이라 `EMBEDDING_MAX_SEQ_LENGTH` 1024 안에 든다. 60자 미만 이론 9개도 제목과 함께 완결된 문장이었다. 합치면 block_id 단위 인용·재적재·관계 연결이 깨진다.
  - 검색 제외(행은 저장, `search_enabled=false`): 표 중복 이론 25개(사유 `duplicate_of_table`, 표가 대표 — 둘 다 넣으면 상위 K에 같은 내용이 두 칸), 학습목표 23개(사유 `learning_objective`, "학습목표 + ★ 출제 중요도" 목록이 주제어만으로 상위권에 오를 위험). 설정 `COMMON_JSON_SEARCH_DUPLICATE_THEORY`·`COMMON_JSON_SEARCH_LEARNING_OBJECTIVE`로 다시 넣을 수 있다(비교 실험용).
  - 임베딩 텍스트(`app/ingestion/common_json.py`): 이론 = 제목 경로(" > ") + 빈 줄 + clean_text / 표 = 제목 경로 + `[표] 제목` + 행마다 한 줄(`table.rows`, raw_text 안 씀. 머리행이 있으면 `- 머리: 값 | …`, 없으면 첫 칸을 행 이름으로 `- 행이름: 값 / …`, 병합 셀은 빈 칸만 채움, units는 `단위: …`) / 시각자료 = 제목 경로 + `[그림] 제목` + `설명:` visual_description + `구조:` visual_structure + `그림 속 글자:` raw_text. `related_theory_context`(이론과 중복)·`visual_observation`은 넣지 않는다. model_generated(keywords·exam_clues·confusable_concepts)는 저장만 하고 넣지 않는다(나중 비교 실험 항목).
  - 결과(1·2과목 최종본 dry-run, 2026-10-07): 블록 390(1과목 163 / 2과목 227), 관계 170(62 / 108). 검색 대상 342(1과목 144: 이론 119·표 16·그림 9 / 2과목 198: 이론 144·표 21·그림 33), 제외 48(학습목표 23 = 12 + 11, 표 중복 이론 25 = 7 + 18). 검증 오류·경고 0건.
  - 적재 스크립트 `python -m app.ingestion.common_json_load`(dry-run 기본, `--apply`, `--subject`, `--block-id`, `--prune`, `--delete`, `--no-db`, `--show`): 파일 전체 검증(format·subject 일치, validation_report passed, block_id 중복·형식, 타입별 필수 필드, block_role 값, duplicate_of_table_id 대상, 관계 끝점·link_type·ID·쌍 중복, pages의 reading_order, merged_cells 범위, 모르는 block_type) — 하나라도 실패하면 아무것도 쓰지 않는다. block_id upsert + content_hash·embedding_text_hash 비교로 **바뀐 블록만 임베딩**(수정본이 오면 과목 전체를 다시 돌려도 그 블록만 바뀜). 임베딩은 DB 쓰기 전에 끝내고 과목당 트랜잭션 1개(documents → blocks → block_relations 전체 동기화 → `--prune`), 실행 기록은 processing_runs 1건(metadata.common_json). 리포트 `data/reports/common_json/`.
  - 데이터 확인 결과(수민님 2과목 최종 동기화본 2026-10-07로 해결): TAB_104_01·TH_104_01은 교재 원본에서 통합 행 문장이 조달 행에 중복 인쇄된 것이라 clean(표 rows·이론 clean_text)에서만 삭제(raw_text는 원문 유지), TH_101_02는 학습목표로 확정되어 duplicate_of_table_id와 관계 BREL_S2_00067 제거(관계 109 → 108), TAB_119_01은 `[구분, 구성요소]` 2열로 수정. 2과목 manifest의 `block_relation_count` 109는 남은 숫자 오타라 무시한다(validation_report는 108, 스크립트는 manifest 개수를 검사하지 않음).
  - 경고만 하고 적재는 진행하는 경우: 학습목표 블록에 duplicate_of_table_id가 있을 때, relation_source=`duplicate_of_table_id` 관계가 블록 필드와 맞지 않을 때(중복 판단은 블록 필드 기준), `COMMON_JSON_PENDING_BLOCK_IDS`(수정본 대기 표시, 지금은 비어 있음)에 든 블록.
  - 임베딩 시간(실측 2026-10-07, CPU, bge-m3, 배치 8): 모델 로드 29초, 블록당 0.72초 → 342블록 약 4분. 모델은 캐시(`E:\hf_models`)에서만 읽도록 설정 `EMBEDDING_OFFLINE=true`(HF_HUB_OFFLINE=1)를 추가했다.
  - /qa는 이번에 바꾸지 않는다. 검색 대상 전환(`SEARCH_CORPUS`), 1·2과목 범위 비교 실험은 다음 PR, 관계 활용(쪽 넘김 이어짐, 이론↔표·시각자료 붙이기, D-J-005 visuals를 DB 기반으로)은 그다음 PR. → 검색 대상 전환은 **D-M-033**에서 구현.
- 대안:
  - 팀 규격 테이블 + 새 book: 위 조사의 불일치 때문에 컬럼·CHECK 우회가 많고 적재 즉시 기존 검색에 섞인다.
  - 짧은 블록을 같은 쪽 이웃과 합치기: block_id 단위가 깨진다. 이웃 문맥은 관계 활용 PR에서 근거를 붙이는 방식으로 다룬다.
  - 중복 이론을 검색에 넣고 표를 빼기(큰 표를 나눈 조각이라 더 촘촘): 비교 실험 항목으로 남긴다.
- 영향:
  - **업로드 자료의 block_id 규칙 필요**: 사용자 업로드 자료가 blocks에 들어올 때 block_id가 공통 JSON의 `S{n}:{TYPE}:{source_id}` 형식과 겹치지 않도록 별도 접두어 규칙(예: `U:{document}:…`)을 그 PR에서 정한다(`blocks.block_id`는 전체 고유).
  - **다음 PR(검색 대상 전환) 메모**: `SEARCH_CORPUS=common_json`이면 query_logs의 근거 ID(`retrieved_theory_ids`, `metadata.evidence[].chunk_id`)가 theory_chunks가 아니라 blocks의 id가 된다. 재원님 신고 스냅샷(`build_snapshot`)이 theory_chunks만 조회하면 전부 missing이 되므로, 그 PR에서 evidence에 `kind`·`block_id`·corpus를 넣고 스냅샷이 blocks도 조회하도록 재원님과 맞춘다.
  - 재원님 브랜치의 D-J-005(공통 JSON 파일을 직접 읽어 visuals를 붙임)는 관계 활용 PR에서 DB(blocks의 S3 키·block_relations)로 바꾸고 응답 형식은 유지한다. 설정 이름 `COMMON_JSON_DIR`(기본 `data/common_json`)은 그 브랜치와 같게 맞췄다.
  - 004를 적용하기 전에는 로컬 DB 테스트 `test_all_migrations_applied`가 실패한다(적용하면 통과, CI는 DB 테스트를 건너뜀).
  - 3과목 공통 JSON이 오면 같은 스크립트로 적재한다. 그때까지 서비스 검색은 1·2과목 블록 + 3과목 theory_chunks를 함께 쓰는 방식이 필요하다(다음 PR의 `mixed`).

## D-JW-004 오류 신고·보충 이론은 mingyu_app 새 테이블 2개로 저장한다 (2026-10-06)
- 배경: 오류 신고 저장 위치로 `query_logs.metadata`나 `query_logs` jsonb 컬럼을 검토했으나 민규 의견으로 별도 테이블로 정했다. 이유: (1) 배열은 "신고 많은 답변 상위 N개"·"주간 신고 수" 집계와 신고 1건만 처리 완료하기가 번거롭고 동시 기록 시 덮일 수 있다. (2) `query_logs`는 로그 테이블이라 오래된 로그를 정리하면 신고도 지워진다. (3) 1과목 재적재 예정이라 근거가 청크 id로만 남으면 다른 내용을 가리킨다.
- 확인(코드, 2026-10-06): `qa/service.py`의 기록은 `retrieved_theory_ids`(청크 id 목록)와 `metadata.evidence`(n, chunk_id, page, vector_score, rerank_score, cited)뿐이고 책 제목·제목 경로·원문은 남지 않는다.
- 결정:
  - `answer_reports`: query_log_id(FK → query_logs, **ON DELETE SET NULL**), 질문·답 스냅샷, report_type(프론트 오류 신고 값 6개 + 새 `missing_concept`), concept_details, detail, **evidence_snapshot**(신고 시점에 청크를 조회해 책 제목·경로·원문까지 복사, 청크가 없으면 화면이 보낸 evidence), status(open/resolved), resolved_at. 한 답변의 여러 신고는 행을 쌓는다.
  - `supplements`: 보충 이론(텍스트/이미지/PDF)을 **검토 대기(pending_review)** 로 저장하고 임베딩하지 않는다. report_id(오류 신고 안 첨부) 또는 source=unanswerable("확인 불가" 버튼). 텍스트는 본문, 파일은 저장소 `supplements/{id}.{확장자}` URI. 팀 규격 `books`/`pages`에 넣는 방안은 자료 유형 CHECK(`user_supplement` 없음)과 팀 규격 데이터 수정 문제로 택하지 않았다.
  - 마이그레이션 파일·PR은 재원, DB 적용은 머지 후 민규(공유 DB 적용 순서 관리).
- 프론트 요청(수지, PR #4 화면): 오류 신고 시 `query_log_id`와 `evidence` 전송, 유형 `missing_concept`("관련 개념이 부족해요") 추가, 신고 안 보충 이론 첨부와 "확인 불가" 답변의 [이론 보충하기]가 같은 입력 UI로 `POST /supplements` 호출.
- 프론트 이름에 맞춤(재원 결정, 수지 화면 연동 커밋 12eba19 기준): `/answer-reports`는 `type`과 `report_type`을 모두 받고, `/supplements`는 본문 `content`와 `text`를 모두 받으며 `kind`를 생략하면 파일 유무·형식으로 정한다(PDF 시그니처 `%PDF-` 또는 .pdf → pdf, 그 밖의 파일 → image, 파일 없음 → text). 기존 이름도 계속 받는다.
- 남은 것: 보충 이론 승인 → 추출·청킹·임베딩(적재 코드 담당과 협의), 관리 화면 검수 목록.

## D-M-033 /qa 검색 대상을 설정값(SEARCH_CORPUS)으로 바꿀 수 있게 하고, mixed는 "공통 JSON이 있는 교재는 블록" 규칙으로 합친다 (2026-10-07, `feat/qa-corpus-switch`)
- 배경: D-M-032로 1·2과목 공통 JSON 390블록(검색 대상 342)을 적재했지만 /qa·평가·기출 실행은 `v_searchable_theory`(theory_chunks)만 검색했다. 3과목 공통 JSON은 아직 없어 3과목은 theory_chunks를 계속 써야 한다. 재원님 신고 스냅샷(D-JW-004)은 근거 id로 theory_chunks만 조회했고, 프론트(PR #4)는 `/qa` evidence의 `n, chunk_id, book_title, page, path, raw_text, 점수, cited`를 쓴다(raw_text는 문자열로 표시).
- 조사(읽기만): 표·시각자료 블록 79개는 `clean_text`가 비어 있고 `raw_text`가 문자열 목록이다 → 그대로 넘기면 Gemini·Jev가 빈 근거를 받고 프론트 표시가 깨진다. `documents.book_id`는 1·2과목 모두 같은 교재 book에 연결돼 있다(정답 판정에 그대로 쓸 수 있음). 적재 때 임베딩 텍스트를 만든 함수의 재료는 모두 blocks 컬럼에 남아 있다(390/390 재생성 일치).
- 결정(사용자 승인 2026-10-07):
  - 설정 `SEARCH_CORPUS` = `team_text` / `common_json` / `mixed`. **기본값은 `mixed`**(아래 "기본값 결정", 사용자 결정 2026-10-07. 처음 구현은 team_text 기본).
  - **mixed 규칙**: `mingyu_app.documents`에 `corpus='common_json'`으로 연결된 book은 블록에서, 나머지 book은 theory_chunks에서 각각 후보 N개를 가져와 cosine 점수로 합친 뒤 상위 N개만 리랭크한다(같은 bge-m3 정규화 벡터라 점수 척도가 같고, 최종 순서는 리랭커가 정함, 리랭크 시간 그대로). 과목 목록을 설정·코드에 두지 않으므로 **3과목 공통 JSON을 적재하면 mixed의 3과목 검색 대상이 자동으로 블록으로 바뀐다**. 후보 출처 개수는 `candidate_sources`로 기록한다. (대안: 각 N개씩 2N개 리랭크 — 질문당 리랭크 시간 약 2배라 택하지 않음)
  - 블록의 LLM·Jev용 본문은 `common_json.embedding_text(블록, with_path=False)`: 적재와 같은 함수에 제목 경로 줄만 빼는 인자를 추가했다(기본 출력은 그대로라 재적재 불필요, 단위 테스트로 고정). 임베딩 텍스트 문자열을 잘라 만들지 않는다. 리랭커 입력은 저장된 embedding_text 그대로.
  - `/qa` evidence는 **필드 추가만**: `corpus, kind, block_id, title, title_path, document_title, thumbnail_url, image_url`. `chunk_id`는 corpus가 team_text면 theory_chunks.id, common_json이면 blocks.id. `raw_text`는 항상 문자열(표·그림 원문 목록은 줄바꿈으로 이음). 이미지 URL은 `ASSET_URL_TEMPLATE`(`{key}`에 저장소 키, 비면 null) — 데이터 안의 완성 URL·버킷 이름은 쓰지 않는다.
  - query_logs: 팀 규격 `retrieved_theory_ids`에는 **theory_chunks id만**(컬럼 뜻 유지). 블록 근거는 `metadata.retrieved_block_ids`·`metadata.evidence[].block_id`, `metadata.corpus`·`candidate_sources`. `retrieved_visual_ids`(팀 규격 visual_assets용)는 쓰지 않는다. 컬럼·DDL 변경 없음.
  - 신고 스냅샷은 이 PR에서 고친다(형식을 바꾼 쪽에서 맞춤, 재원님 리뷰 요청): `get_blocks` 추가, `create_report`가 block_id 있는 근거는 blocks에서 조회, `build_snapshot`은 행의 path 우선 + 스냅샷 키에 corpus·kind·block_id, `EvidenceIn`에 같은 선택 필드.
  - 평가: `evaluate --corpus a,b,c --subjects …`(같은 질문 임베딩·같은 리랭커), 블록 정답 판정도 book_id(documents.book_id) + 인쇄 쪽. 질문별 3구간·1위 근거 종류를 세고 비교표에 hit@k·MRR, 자료 없음·답 가능 질문의 3구간 수, 1위 벡터·리랭커 점수 분포를 함께 낸다. 기출은 `mcq_run run --subjects`, 검색 대상은 서버 `SEARCH_CORPUS`(결과 meta.corpus).
  - "확인 불가" 기준값(벡터 0.45 / 리랭커 0.03 / 0.15)과 Jev 임계값(0.5 / 0.8)은 이 PR에서 바꾸지 않는다.
- 범위 밖: 관계 활용(쪽 넘김 이어짐, 이론↔표·시각자료 붙이기)과 visuals(PR3), 프론트 표시(썸네일 등), 기본값 변경.
- 비교 실험 계획(처음): 검색 평가 + 기출을 team_text·common_json·mixed로 각각 실행(기출 약 40회). **마감(2026-10-08) 때문에 기출은 기본값(mixed) 15문제 1회로 줄이고, 기준선은 기존 `20261001-183551`(12/0/2/1)로 했다.**
- 검색 평가 결과(2026-10-07, 리랭커 bge-reranker-v2-m3, N=10, K=5, Gemini 0회. `data/reports/eval/20261007-202404-*`, `20261007-203331-*`):

  | 범위 | 검색 대상 | hit@1 | hit@3 | hit@5 | MRR | 자료 없음 reject/gray/answer | 답 가능 reject/gray/answer |
  |---|---|---|---|---|---|---|---|
  | 1·2과목(답 가능 16 + 자료 없음 7) | team_text | 13/16 | 16/16 | 16/16 | 0.906 | 7/0/0 | 0/0/16 |
  | | common_json | 13/16 | 15/16 | 16/16 | 0.891 | 7/0/0 | 0/1/15 |
  | 전체 33문항(답 가능 26 + 자료 없음 7) | team_text | 22/26 | 26/26 | 26/26 | 0.917 | 6/1/0 | 0/2/24 |
  | | mixed | 22/26 | 25/26 | 26/26 | 0.907 | 6/1/0 | 0/3/23 |

  - 자료 없음 질문은 어느 대상에서도 answer 0(common_json 리랭커 1위 최대 0.004). mixed의 자료 없음 gray 1개는 team_text와 같은 문항(n08, 3과목 청크).
  - 1위 근거가 표·그림인 경우: mixed 답 가능 26개 중 table 3 · visual 2(예: b02 KDD/CRISP-DM 비교 표 TAB_79_01이 1위가 되어 2위→1위).
- 기출 객관식 결과(2026-10-07, 서버 mixed, `data/reports/mcq/20261007-204900.json` + `.grades.json`, 비교 `compare-20261007-205017.md`):

  | 실행 | 맞음 | 틀림 | 확인 불가 | 모호 |
  |---|---|---|---|---|
  | 기준선 20261001-183551(team_text) | 12 | 0 | 2 | 1 |
  | mixed | 12 | 0 | 3 | 0 |

  - 바뀐 문항: p26-3 확인 불가→맞음(④). p56-1 맞음→확인 불가(LLM 판단 오류: 해설이 근거 [2] p55 "일차원적 분석으로도 상당한 효과"를 인용하고도 ①을 고르지 않음, 기준선 1위였던 56쪽 청크는 상위 5개에 없음). p84-1 모호→확인 불가(교재에 근거 없음, 규칙대로 거절). p50-2는 기준선과 같은 확인 불가(1위가 p50 "학습정리" 블록). computed 0.
- **기본값 결정(사용자, 2026-10-07)**: `SEARCH_CORPUS` 기본 `mixed`.
  - 근거 1: 검색 평가에서 hit@1·hit@5·자료 없음 차단이 team_text와 같고(MRR 0.917→0.907), 표·그림 블록이 1위로 올라오는 경우가 생긴다. 기출은 맞음 12·틀림 0으로 기준선과 같다(통과 기준: 틀림 0 유지, 맞음 12 이상).
  - 근거 2: 재원님 이론 수정 기능(D-JW-007 예정, 2026-10-07 기준 아직 PR·결정 기록 없음)이 block_id로 이론 블록을 고치는 설계라, 사용자가 보는 1·2과목 근거가 블록이어야 수정 흐름이 이어진다.
  - 3과목은 공통 JSON이 적재되기 전까지 theory_chunks 그대로(mixed 규칙).
- 알려진 위험: "학습정리" 요약 블록이 본문보다 앞에 오는 경우가 있다. a05는 TH_43_02(학습정리)가 1위가 되어 정답 쪽이 1위→4위, answer→gray. a04도 학습정리 TH_40_01이 1위였지만 정답 쪽이라 hit. 기출 p50-2도 1위가 TH_50_01(학습정리). (a08은 학습정리가 8위, 1위는 VIS_59_01로 정답 쪽.) 학습목표처럼 검색에서 뺄지는 평가 재실행이 필요해 이번에는 보류.
- 기준값(0.45 / 0.03 / 0.15)·Jev(0.5 / 0.8)는 바꾸지 않았다.

## D-JW-001 문제 사진 OCR API는 프론트 화면 흐름에 맞추고 기존 PaddleOCR을 재사용한다 (2026-10-06)
- 배경: 프론트 UI PR(`feat/frontend-ui`)의 문제 사진 입력(`QuestionForm`)은 사진 → "추출된 문제" 칸 채우기 → 사용자가 고침 → `/qa` 흐름이고, OCR API가 없어 미리보기까지만 되어 있다.
- 결정: `POST /ocr`은 문제 사진을 저장하지 않고 텍스트만 돌려준다. 사용자가 텍스트를 고친 뒤 `/qa`로 보내므로, 비전 LLM으로 바로 푸는 `/qa/image` 대신 업로드 경로의 인쇄체 PaddleOCR 엔진을 재사용한다(추가 API 비용·모델 없음, DB 사용 없음).
- 줄 순서: 세로 중심 기준 위→아래, 같은 높이(앞 줄 높이의 절반 이내)는 왼→오른으로 공백 연결.

## D-JW-002 문제 사진 추출은 Gemini 비전을 기본으로, PaddleOCR은 대체 경로로 (2026-10-06, D-JW-001 일부 변경)
- 배경: 실제 휴대폰 사진(기울어짐·페이지 휨·뒷장 비침·위아래에 다른 문제)으로 `/ocr`(PaddleOCR)을 시험하니 문제 문장과 ①② 보기를 놓치고, 비친 글자("통H허호…")와 아래 문제 문장을 섞어 읽었다. 이대로 `/qa`에 넣으면 질문 자체가 바뀐다(예: "옳은 것" → "옳지 않은 것").
- 결정: `/ocr`은 Gemini 비전 구조화 출력(`found`, `problem_text`, `choices`, `figure_description`)으로 가장 온전한 문제 1개만 옮겨 적게 한다. 모델은 `PROBLEM_EXTRACT_MODEL`(기본 lite), 프롬프트는 `backend/app/prompts/problem_extract_*`. 키가 없거나 호출이 실패하면 기존 PaddleOCR로 읽고 `fallback_reason`을 남긴다. PaddleOCR 엔진 설정(`ingestion/ocr.py`)은 교재 업로드와 공유하므로 바꾸지 않는다.
- 이미지 입력: `GeminiClient.generate_json(..., images=[(바이트, MIME)])` → user 텍스트 파트 뒤에 `inlineData {mimeType, data(base64)}` 파트. 확인 2026-10-06: https://ai.google.dev/api/caching#Part (Part.inlineData / Blob), 요청 전체 20MB 이하·텍스트 다음에 이미지 권장 https://ai.google.dev/gemini-api/docs/image-understanding .
- 비용·한도: 사진 1장당 Gemini 호출 1회(무료 한도 공유). DB는 쓰지 않는다.

## D-JW-003 문제 사진 OCR에 Google Cloud Vision 엔진을 추가한다(기본은 gemini) (2026-10-06, 2026-10-07 기본값 변경)
- 배경: 재원 결정으로 문제 사진 글자 인식은 Google Cloud Vision을 쓴다. Gemini 방식(D-JW-002)은 지우지 않고 `PROBLEM_OCR_ENGINE=gemini`로 고를 수 있게 둔다.
- 결정: `PROBLEM_OCR_ENGINE`(기본 `gemini`, `google_vision`은 키가 있을 때 선택). Vision은 REST `POST https://vision.googleapis.com/v1/images:annotate`에 `DOCUMENT_TEXT_DETECTION` + `languageHints`(`GOOGLE_VISION_LANGUAGE_HINTS`, 기본 ko)로 보내고 `fullTextAnnotation.text`를 그대로 돌려준다. 키(`GOOGLE_VISION_API_KEY`)는 `x-goog-api-key` 헤더로만 보낸다. 키가 없거나 실패하면 PaddleOCR로 대신 읽는다.
- 기본값 변경(2026-10-07, PR 전): 처음에는 기본을 `google_vision`으로 했으나 `gemini`로 되돌린다. 팀원 모두 답변용 `GEMINI_API_KEY`가 있고 Vision 키(결제 계정 필요)는 없어서, 기본이 Vision이면 `.env.example`을 복사한 팀원은 매번 PaddleOCR 대체 경로(인식 품질 낮음)로만 돈다. 실제 문제 사진(지니 지수 31번)에서 Gemini가 문제·선택지·그림 설명을 정확히 옮긴 것도 확인했다. Vision은 키를 넣고 `PROBLEM_OCR_ENGINE=google_vision`으로 고른다.
- 한계: Vision은 사진의 글자를 모두 읽으므로 위아래에 걸린 다른 문제·비친 뒷장 글자가 섞일 수 있다. 문제 1개만 골라내기·선택지 나누기는 하지 않고 사용자가 입력칸에서 고친다.
- 리뷰 반영(민규, PR #8, 2026-10-07):
  - 크기: /ocr만 `PROBLEM_OCR_MAX_UPLOAD_MB`(기본 12). Gemini 인라인 요청은 20MB까지라 base64(약 1.33배)를 붙이면 15MB쯤부터 400이 난다. `OCR_*`는 PaddleOCR 설정 접두어라 `PROBLEM_OCR_*`로 맞췄다.
  - PaddleOCR까지 실패(모델 파일 없음 등)하면 500 대신 503 + "문제를 직접 입력해 주세요".
  - 프론트 대기 시간: `VITE_OCR_TIMEOUT_SECONDS`(기본 330초)를 /qa와 따로 둔다. 서버 최악 경로 = Gemini 4번 시도(60초×4 + 대기 2+4+8초, `GEMINI_MAX_RETRIES`=3) + PaddleOCR 첫 로드(약 60초) ≈ 314초. `PROBLEM_EXTRACT_MODEL=strong`이면 strong→lite 폴백까지 시도해 약 2배로 늘어난다.
  - 남은 것: /ocr 전용 재시도 횟수(`PROBLEM_OCR_MAX_RETRIES`)는 다음 PR. 화면(QuestionForm)의 OCR 중 입력 막기·기존 입력 보호는 수지 담당.
- 확인 2026-10-06: 요청·응답 형식 https://docs.cloud.google.com/vision/docs/ocr , 인증("API key or OAuth token") https://docs.cloud.google.com/vision/docs/request , 가격(기능별 월 1,000단위 무료, 이후 1,000단위당 $1.50, **무료 구간도 결제 계정 필요**) https://cloud.google.com/vision/pricing .

## D-JW-007 오류 신고 처리 기록과 이론 블록 수정안(block_corrections) — 005 마이그레이션 (2026-10-07)
- 배경: 강사 요구 "틀린 이론 수정". 오류 신고(D-JW-004)를 받기만 하고 처리 결과와 교재 원문 수정 경로가 없었다. 검색 대상이 공통 JSON 블록(`mingyu_app.blocks`, D-M-032)으로 옮겨 가므로 수정 대상도 blocks로 하고, 재적재해도 안 바뀌는 `block_id`로 가리킨다(민규 협의).
- 범위(1차): 이론 블록(`block_type = theory`)의 `clean_text`만. `raw_text`·표·시각자료는 고치지 않는다(표·시각자료는 `table_data`·`visual_data`에 내용이 있어 clean_text 수정으로 못 고침 → 데이터 담당 JSON 수정 요청 `source_fix_requested`로 닫음).
- 005 변경(`mingyu_app`만, 팀 규격 테이블 변경 없음):
  - `blocks.source_clean_text_hash`: JSON 원문 clean_text 해시. 005에서 SQL로 채움(지금은 적용된 수정이 없어 DB clean_text = JSON 원문). clean_text가 NULL이면 NULL.
  - 해시 규칙(기준 함수 `app/core/text_hash.py` `clean_text_hash`): CRLF·CR → LF → 앞뒤 스페이스·탭·LF만 제거 → UTF-8 sha256 hex. Python `strip()`은 모든 유니코드 공백을, PostgreSQL `btrim()`은 기본으로 스페이스만 지워서 지울 문자를 `" \t\n"`으로 명시했다. SQL 식과 Python 값이 같은지, 백필 값이 맞는지 `tests/test_text_hash.py`로 묶었다.
  - `answer_reports`: `resolution`(block_corrected / supplement_added / source_fix_requested / prompt_issue / retrieval_issue / not_an_error / duplicate / other), `resolution_note`(500자), `linked_block_ids`(team_text 근거 신고를 대응 block_id에 연결), `reviewed_by`(100자). `status`는 open/resolved 그대로, resolved면 resolution 필수.
  - `block_corrections`: block_id(FK 없음 — 블록이 JSON에서 빠져도 적재를 막지 않게), report_id(FK, SET NULL), base_clean_text(작성 당시 DB clean_text, 비교 화면용), base_clean_text_hash(작성 당시 `source_clean_text_hash` 복사 — DB clean_text 해시가 아님), new_clean_text(1~2,000자, 공백만 거부), reason, status, review_note, reviewed_by, applied_note, created_at·reviewed_at·applied_at. 블록당 approved/applied는 1개(부분 유니크).
  - 길이 한도 근거(2026-10-07 조회): theory 311개 기준 clean_text 최대 694자, 99% 586자. 1.5배(1,041자)에 2과목 이후 여유를 두어 2,000자.
- 흐름(마감 축소판, 민규 요청): 승인하면 API가 바로 블록 clean_text를 고치고 재임베딩한다(`common_json.embedding_text` 그대로).
  - proposed → (승인) applied / (반려) rejected / (철회) withdrawn
  - applied → 같은 블록의 새 수정 적용 시 superseded(같은 트랜잭션에서 먼저 처리)
  - approved·stale은 적재 코드가 승인된 수정을 다시 적용하는 후속 단계용으로 CHECK에만 둔다.
- 알려진 한계:
  - 적재 코드(common_json_load)가 JSON 원문으로 upsert하므로, 재적재하면 적용된 수정이 덮어써진다. 수정 기록(block_corrections)은 남으므로 후속 단계에서 적재 코드가 applied 수정을 다시 적용하고, 원문 해시가 다르면 stale로 바꾼다.
  - 승인 API에 인증이 없다(내부용). reviewed_by는 직접 입력한 이름이라 검증되지 않는다.
  - 길이 한도 2,000자는 1과목 기준. 다른 과목 적재 후 최대 길이가 1,300자를 넘으면 마이그레이션으로 다시 정한다.
- 역할: 005·API는 재원, 적용(DB)은 민규. API는 PR #10(evidence에 block_id) 머지 후.
