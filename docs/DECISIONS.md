# DECISIONS

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

## D-022 검색 평가 기준과 실행 중단 처리 (2026-09-30)
- 적중 기준: 상위 K개 중 **정답 과목 book + 정답 인쇄 쪽** 청크가 있으면 적중(청크 id가 아니라 쪽 단위). 청킹을 바꿔도 같은 질문 세트를 그대로 쓸 수 있게 하기 위함. 정답 순위는 `EVAL_RANK_DEPTH`(20)까지 찾아 MRR도 함께 본다.
- "확인 불가" 임계값은 **1위 점수(cosine 유사도)** 하나로 평가한다(1위 ≥ t → 통과). 예시 6문항에서 자료에 없는 질문(0.524)이 교재 질문(0.515)보다 높게 나와, 점수만으로 못 가를 가능성이 있음 → 실제 세트 결과를 보고 답변 가능 판정(can_answer)·리랭커와 역할을 나눈다.
- 평가 스크립트는 DB를 읽기만 하고, 결과는 `data/reports/eval/`(gitignore)에 둔다. 질문 세트도 `data/eval/`(교재 쪽번호·내용 포함이라 커밋 안 함).
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
- 첫 샘플(10문항, 2026-10-01): 질문당 전체 5.7~7.4초(리랭크 3.4~5.1초, LLM 1.5~2.0초), 확인 불가(reject)는 0.5~4.4초. 토큰 약 2,000~2,750/질문. 결과 `data/reports/answers/20261001-091851.md`.

## D-026 페이지를 넘어 이어지는 코드 블록은 "청크는 페이지를 넘지 않음"(D-019)·페이지 단위 출처(D-014)의 예외 (2026-10-01, 설계만)
- 배경(팀원 피드백 + DB 읽기 전용 조사 2026-10-01): 교재 R 코드가 페이지를 넘어 이어지는 경우가 있고, 지금은 청크가 페이지에서 끊겨 뒷부분 출력 조각이 needs_review(검색 제외)가 된다. 3과목에서 엄격 기준(앞 페이지 마지막 본문 줄·다음 페이지 첫 본문 줄이 모두 코드, 사이 제목 없음) 9건(실제 코드 이어짐 6, 그래프 글자 3), 완화 기준(앞뒤 3줄 안) 41건(눈으로 본 잠정 분류: 코드·출력 이어짐 약 18, 앞 예제 끝·다음 예제 시작 4, 그래프·수식 글자 오검출 19). 1과목 0건, 2과목은 완화 기준 1건(도식, 오검출). 뒷부분 첫 청크가 needs_review인 건 3건(135·142·143쪽, 모두 "R 기초" 단원) — 전체 needs_review 11개 중 3개.
- 결정(설계, 구현은 PROGRESS 다음 작업 2번 "청킹 보완"):
  - 코드 블록 인식 규칙 + 페이지 넘김 이어짐 판단(마지막 본문 줄·다음 첫 본문 줄이 코드, 사이에 제목 없음, "예제N"·기출 블록으로 시작하면 이어짐 아님)
  - **이어진 코드 블록만** 한 청크로 합친다. `page_id`는 시작 페이지, 전체 페이지·줄 범위는 `source_alignment.spans`(JSONB, 컬럼 추가 없음), 출처는 "226~227쪽"처럼 범위로 표시. D-014의 "청크 출처는 페이지 단위"는 이 경우만 "페이지 범위"로 바뀐다. 그 밖의 본문은 여전히 페이지를 넘지 않는다.
  - 코드와 실행 결과는 같은 청크, 출력만 떨어진 조각을 만들지 않는다.
  - 코드 청크 embedding_text = 제목 경로 + 코드 앞 설명 문장 + 코드. 설명이 부족할 때만 Gemini 설명문을 embedding_text에 추가(원문 필드에는 넣지 않음).
  - 시각자료 crop(D-016)도 같은 원칙: 페이지를 넘는 코드·표는 두 crop을 세로로 이어 붙여 하나로, 페이지 범위를 기록.
- 이유: 코드는 앞 대입·호출과 뒤 출력이 함께 있어야 뜻이 통하고(출력 조각만으로는 검색·답변 근거가 안 됨), 시험 문제도 "아래 R 코드 출력 결과는?" 형태로 코드+출력을 함께 묻는다. 일반 본문까지 페이지를 넘기면 출처 표시와 재청킹 범위가 복잡해지므로 예외는 코드 블록(필요하면 표)으로 한정한다.
- 주의: 팀 텍스트에는 그래프 축 눈금·수식 조각이 한 줄로 섞여 있어 숫자·기호 줄만으로는 코드와 구별되지 않는다(조사의 오검출 원인). 출력 줄은 코드 줄이 앞에 있는 블록 안에서만 인정한다. 규칙은 구현 시 같은 조사 스크립트로 오검출을 다시 확인한다.

