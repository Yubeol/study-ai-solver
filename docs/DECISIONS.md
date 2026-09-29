# DECISIONS

## D-001 과목은 ADsP (2026-09-29)
공부에 실제로 쓸 과목. 설계는 과목에 의존하지 않게 유지한다(books.subject로 구분).

## D-002 과제 중심은 질의형 시험공부 RAG (2026-09-29)
실습과제 슬라이드 기준으로 "자료 업로드 → 질문 → 시험형 답변"이 핵심이다. 인수인계의 문제 사진 풀이는 질의 입력 방식 중 하나로 포함한다.

## D-003 DB는 팀 공유 서버의 mingyu 스키마 (2026-09-29)
- 팀원이 AWS에 PostgreSQL을 띄우고 스키마 4개(jaewon, mingyu, sugi, sumin)와 규격 테이블을 만들어 둠. 내 스키마는 mingyu.
- 공용 프론트가 같은 구조로 조회할 수 있으므로 기존 컬럼은 바꾸지 않고 추가만 한다.
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
