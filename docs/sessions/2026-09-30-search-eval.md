# 2026-09-30 전체 임베딩 확인 · 실행 중단 처리 · 검색 평가 스크립트

## 무엇을 만들었나
- **전체 임베딩 완료 확인**: 팀 교재 3권 324쪽이 모두 임베딩되어(EMBEDDED) 검색 가능한 이론 청크가 605개가 되었음을 DB에서 확인했다. 코드는 바꾸지 않았다.
- **실행 중단 처리**: 청킹·임베딩 실행기를 Ctrl+C로 멈추면, 그 실행 기록(processing_runs)이 "실행 중(RUNNING)"으로 영원히 남던 문제를 고쳤다. 이제 멈추는 순간 "실패(FAILED)"로 닫고, 그때까지 처리한 개수를 남긴다.
- **검색 평가 스크립트**: 내가 만든 질문 세트(CSV)로 "검색이 정답 쪽을 몇 등 안에 찾아오는지(hit@1/3/K)"와 "점수 몇 이상일 때만 답하게 하면 자료에 없는 질문을 얼마나 걸러내는지(임계값별 통과·차단)"를 한 번에 계산한다.

## 어떻게 돌아가나
### 실행 중단 처리
1. `run_stages`(또는 업로드 API)는 `backend/app/ingestion/pipeline.py`의 `run_pipeline`을 부른다.
2. `run_pipeline`은 실제 페이지 반복을 `_process_pages`에 맡기고 바깥을 감싼다. 페이지 하나가 오류가 나면 원래처럼 그 페이지만 FAILED로 하고 계속 간다.
3. Ctrl+C가 들어오면(KeyboardInterrupt) 반복이 멈추고, `run_pipeline`이 `backend/app/repositories/runs.py`의 `finish_run(..., interrupted=True)`를 불러 `mingyu.processing_runs`의 status를 FAILED, finished_at을 지금으로 기록한다. 그 다음 중단을 다시 위로 던진다.
4. `run_stages`의 `main`은 그 중단을 받아 "같은 명령을 다시 실행하면 된다"고 출력하고 끝난다. 처리 중이던 페이지는 상태가 바뀌지 않았으므로(예: VERIFIED 그대로) 다시 실행하면 다시 처리된다.
5. 단, 터미널 창을 닫거나 프로세스를 강제로 끄면 코드가 끼어들 틈이 없어 RUNNING으로 남을 수 있다. 그래서 세션 시작(/start) 때 RUNNING을 보면 "실행 중일 수 있음"으로 보고하고 먼저 물어보게 했다.

### 검색 평가
1. `python -m app.retrieval.evaluate`를 실행하면 `backend/app/retrieval/evaluate.py`의 `main`이 질문 파일(`.env`의 `EVAL_QUESTIONS_PATH`, 기본 `data/eval/questions.csv`)을 읽는다.
2. `parse_questions`가 형식을 검사한다: 머리행 `id,question,subject,pages,note`, subject는 `data/raw/adsp/page_map.json`의 key(subject1~3), pages는 인쇄 쪽번호(여러 개는 `18|19`), pages가 비어 있으면 "자료에 없는 질문". 틀린 줄은 줄 번호와 함께 한꺼번에 알려 준다. `--check`면 여기서 끝난다.
3. `run`이 모든 질문을 BGE-M3로 한 번에 벡터로 바꾸고(`app/ingestion/embedding.py`), 질문마다 `app/retrieval/search.py`의 `search_theory`로 `mingyu.v_searchable_theory`에서 상위 20개(`EVAL_RANK_DEPTH`)를 가져온다. DB는 읽기만 한다.
4. `find_rank`가 결과 중 "정답 과목 교재의 정답 쪽" 청크가 처음 나온 순위를 찾는다.
5. `summarize`가 hit@1/3/K(K는 `SEARCH_TOP_K`, 기본 5), MRR, 과목별 수치, K 안에 정답이 없는 질문 id, 1위 점수 범위, 임계값 후보(`EVAL_THRESHOLDS`)별 통과·차단 비율을 계산한다.
6. 화면에 요약을 출력하고 `data/reports/eval/{날짜-시각}.json`(질문별 상위 결과 전체)과 `.txt`(요약)로 저장한다.

## 직접 확인하는 방법
1. 임베딩 상태 (DataGrip)
   - `SELECT processing_status, count(*) FROM mingyu.pages GROUP BY 1;` → `EMBEDDED 324`
   - `SELECT count(*) FROM mingyu.v_searchable_theory;` → `605`
   - `SELECT status, started_at, finished_at FROM mingyu.processing_runs ORDER BY started_at DESC LIMIT 5;` → 최근 실행이 모두 SUCCESS, finished_at 있음
2. 질문 파일 형식 검사 (PowerShell)
   - `cd backend; uv run python -m app.retrieval.evaluate --questions ..\data\eval\questions.sample.csv --check`
   - 기대: `질문 6개(답할 수 있는 질문 4, 자료에 없는 질문 2)`
3. 예시 평가 실행
   - `uv run python -m app.retrieval.evaluate --questions ..\data\eval\questions.sample.csv`
   - 기대: `hit@1 3/4 hit@3 4/4 hit@5 4/4`, 임계값 표 출력, `data\reports\eval\` 아래 json/txt 생성
4. 내 질문 세트로 평가: `data\eval\questions.csv` 작성(엑셀은 "CSV UTF-8"로 저장) → `uv run python -m app.retrieval.evaluate --check` → `uv run python -m app.retrieval.evaluate`
5. 테스트: 저장소 루트에서 `uv run pytest` → 75개 통과

## 아직 안 되는 것
- 실제 질문 세트(20~30개)는 아직 없다. 예시 6문항 결과는 동작 확인용이라 결론으로 쓰면 안 된다.
- 예시에서 자료에 없는 질문(트랜스포머, 0.524)이 교재 질문(DIKW, 0.515)보다 점수가 높았다. 점수 하나로 "확인 불가"를 가르기 어려울 수 있어, 다음 단계의 답변 가능 판정·리랭커가 필요할 수 있다.
- 리랭커·키워드 검색은 아직 없다(평가 설정에 `reranker: null`, `keyword_search: null`로 표시).
- 창 닫기·강제 종료로 끊긴 실행은 여전히 RUNNING으로 남을 수 있다(자동 정리 기능 없음).
