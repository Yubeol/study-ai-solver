# 2026-10-01 기출 객관식으로 답변 확인 · Jev 키 확인 · 답변 프롬프트 조정

## 무엇을 만들었나
- **기출 객관식 확인 도구(`mcq_run`)**: 청킹 때 이론에서 빼 둔 "기출유형 개념잡기" 문제를 다시 꺼내 문제문·보기 ①~④·정답 번호로 나누고, 고른 문제를 질의 API(`/qa`)에 넣어 답변을 모은다. 사람이 답변을 읽고 채점한 파일을 합치면 과목별 정답률과 틀린 원인을 표로 정리한다.
- **Jev(판정기) 키 확인**: 받은 키로 TypeSafe 직접 API에 요청 한 번을 보내 성공(200)했다. 판정기 구현은 아직이고, 어떤 주소·형식으로 부르면 되는지만 확정했다.
- **답변 프롬프트 조정**: 답변이 근거 문장 하나당 한 문장으로, 모든 문장에 [번호] 인용을 붙여, "~다"체로 쓰도록 규칙을 바꿨다. 인용 없는 문장이 몇 개인지 자동으로 세어 기록한다.

## 어떻게 돌아가나
1. `extract`: `backend/app/qa/mcq_run.py`의 `load_blocks`가 DB `mingyu.excluded_sections`(section_type='exam_question')에서 기출 블록의 원문 위치(추출 결과 파일 주소 + 줄 범위)를 읽고, 저장소의 팀 텍스트 파일에서 그 줄을 잘라 온다. `split_block`이 "기출유형 개념잡기" 단위로 문제를 나누고, `parse_question`이 보기 기호 ①~④와 "정답" 옆 번호를 찾는다. 기호가 깨졌거나 정답 번호가 없으면 이유를 적어 제외한다(애매하면 빼는 엄격 규칙). 결과는 `data/reports/mcq/candidates.json`·`.md`에 저장된다.
2. 사람이 `candidates.md`를 보고 실행할 문제 key를 `data/eval/mcq_selection.json`의 `selected`에 적는다(이번에는 과목별 5개, 그림·표가 필요한 문제와 뺀 이유도 같이 기록).
3. `run`: 고른 문제를 "문제문 + ① ~ ④" 텍스트로 만들어 실행 중인 서버의 `POST /qa`에 한 문제씩 보낸다(요청 사이 `MCQ_REQUEST_INTERVAL_SECONDS`초 대기). 서버 쪽은 기존 질의 흐름(`app/qa/service.py`: 검색 → 리랭커 → 3구간 → Gemini 답변 → 인용 검증 → `query_logs` 기록)을 그대로 탄다. 응답은 `data/reports/mcq/{시각}.json`·`.md`에 저장된다.
4. 사람이 답변을 읽고 `{시각}.grades.json`에 문제별 채점(맞음/틀림/확인 불가/답이 모호함)과 원인(검색 실패/LLM 판단 오류/정제 문제/시각자료 필요/기타)을 적는다.
5. `report`: 채점 파일을 합쳐 같은 이름의 `.md`를 요약표 포함으로 다시 쓰고 `{시각}.graded.json`을 만든다. `--baseline`을 주면 이전 채점 열이 붙어 전후 비교가 된다.
6. 프롬프트: `backend/app/prompts/answer_system.txt`(규칙)와 `answer_schema.json`(필드 설명)을 고쳤다. 서버는 질문마다 이 파일을 다시 읽는다. `service.py`의 `validate_citations`가 설명·헷갈리는 개념 칸의 인용 없는 문장 수를 세어 응답의 `llm.citation_check`와 `query_logs.metadata.citation_check`에 남긴다.

## 이번 결과 요약
- 기준선(프롬프트 변경 전) 15문제: 맞음 10, 틀림 0, 확인 불가 4, 답이 모호함 1. 확인 불가 4개는 모두 근거를 찾았는데 LLM이 "보기 하나라도 근거가 없으면 전체 거절"한 경우였다.
- 프롬프트 변경 후: 인용 없는 문장과 "~습니다"체 문장은 0개로 줄었다. 정답 수(9)는 다시 돌리면 뒤집히는 정도의 차이라 좋아졌다/나빠졌다고 말할 수 없다.
- Jev: TypeSafe 직접 API로 성공. Cloudflare 값은 비어 있어 그 경로는 쓰지 않는다(DECISIONS D-007).

## 직접 확인하는 방법
1. 파싱 결과 보기(서버 불필요, DB 접속 필요):
   `cd backend; uv run python -m app.qa.mcq_run extract`
   → 화면에 "109문제, 파싱 성공 24". `data/reports/mcq/candidates.md`를 열면 문제별 상태(ok 또는 제외 이유)와 파싱된 문제 목록이 보인다.
2. 이번 세션 결과 열어 보기: `data/reports/mcq/20261001-170318.md`(기준선)와 `20261001-171504.md`(프롬프트 변경 후, "이전 채점" 열 포함). 맨 위 요약표에 과목별 맞음·확인 불가 수와 정답률이 있다.
3. 다시 실행해 보기(Gemini 무료 한도 사용, 약 3분):
   다른 창에서 `cd backend; uv run uvicorn app.main:app`(모델 로딩 약 1분, "Application startup complete" 확인) →
   `cd backend; uv run python -m app.qa.mcq_run run` → 문제마다 "구간/상태 고른 보기 정답 인용 시간" 한 줄씩 나오고 마지막에 저장 경로가 나온다.
4. 프롬프트 변경 확인: 같은 서버로 `uv run python -m app.qa.sample_run --ids c07,c01,a01` → `data/reports/answers/{시각}.md`에서 설명 문장 끝마다 [번호]가 있고 "~다"로 끝나는지 본다. 인용 검증 줄의 `uncited_sentence_count`가 0이면 정상.
5. DataGrip: `mingyu.query_logs`의 최근 행 `metadata -> 'citation_check'`에 `uncited_sentences`, `uncited_sentence_count`가 있다.
6. 테스트: 루트에서 `uv run pytest` → 105 passed.

## 아직 안 되는 것
- 객관식에서 보기별로 판단하지 못해 거절이 많다(1과목 5문제 중 3문제 확인 불가). 판정기(Jev)의 객관식 후보 역할이나 객관식 전용 프롬프트로 개선할지 판정기 단계에서 정한다.
- 답변 결과가 실행마다 1~2문제 흔들린다. 비교할 때는 2회 이상 돌려야 한다.
- 표가 한 줄로 뭉친 청크(예: 3과목 p280) 때문에 생기는 답 오류는 프롬프트로 안 고쳐진다 → 다음 세션 첫 작업(청킹 보완).
- 판정기(Jev)는 키 확인만 했고 서비스에는 아직 연결하지 않았다.
- 파싱은 엄격해서 109문제 중 24문제만 쓸 수 있다(정답 번호가 그림이라 팀 텍스트에 없는 경우가 많음).
- 프롬프트 변경 부작용: 헷갈리는 개념 칸이 비거나 설명과 같은 문장을 반복하는 경우가 있다.
