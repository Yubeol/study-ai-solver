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

## D-006 Vision/LLM은 Gemini 2.5 Flash-Lite(기본) + 2.5 Flash(재처리) (2026-09-29)
- 확인 사항: Gemini Developer API에서 gemini-2.5-flash-lite, gemini-2.5-flash는 2026-10-16 종료 예정. Google은 2.5 접근을 기존 사용자로 제한하고 신규 프로젝트에 3.5 Flash-Lite / 3.8 Flash를 권장.
  - 출처: https://firebase.google.com/docs/ai-logic/models , https://ai.google.dev/gemini-api/docs/deprecations
- 결정: 프로젝트 기간(~10-15)이 종료 전이라 2.5를 사용. 모델명은 .env 설정값으로 두어 교체 가능하게 한다. 신규 키로 접근이 막히면 3.1 Flash-Lite로 바꾼다.
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