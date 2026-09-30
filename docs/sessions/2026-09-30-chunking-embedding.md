# 2026-09-30 세션: 이론 청킹 · 로컬 임베딩 · 벡터 검색 (+ 설계 보완)

## 무엇을 만들었나
- **이론 청킹**: DB에 들어가 있던 팀 교재 3권(324쪽)의 페이지 텍스트를 검색하기 좋은 조각(청크)으로 나눠 `theory_chunks` 테이블에 넣었습니다. 머리말·쪽번호는 빼고, "1장 > 01 절 > 1. 항" 같은 제목 경로를 페이지를 넘어 이어 붙이며, 기출 표시(★)와 학습목표는 `exam_clues`로 옮깁니다. "기출유형 개념잡기" 문제 블록은 이론 검색에서 빼고 `excluded_sections`에 위치만 기록합니다.
- **실행 진입점**: 이미 텍스트가 뽑힌 페이지에 "청킹"이나 "임베딩" 단계만 다시 돌리는 명령(`run_stages`)을 만들었습니다. 기본은 dry-run(DB를 바꾸지 않고 리포트만 만듦)이고, `--apply`를 붙여야 DB에 씁니다.
- **로컬 임베딩과 검색**: BGE-M3 모델(내 컴퓨터 CPU에서 동작)로 청크를 1024개 숫자(벡터)로 바꿔 저장하고, 질문도 같은 방식으로 바꿔 가장 가까운 청크를 찾는 확인용 검색 명령을 만들었습니다. 모델 파일은 C: 대신 `E:\hf_models`에 받습니다.
- **설계 문서 보완**(코드 변경 없음): 팀 방향 변경(공용 프론트 없음, D-021), 이론 보충·수정 기능 설계, 리랭커 등 검색 개선 후보, 검색 평가 방법을 문서에 적고 다음 작업 순서를 바꿨습니다.

## 어떻게 돌아가나
**청킹 (`--stages chunk`)**
1. `backend/app/ingestion/run_stages.py`의 `main`이 `--subject`(subject1~3, all)로 book을 찾고(`resolve_targets`), 그 book의 페이지 중 상태가 EXTRACTED/VERIFIED/EMBEDDED인 것을 쪽 순서대로 고릅니다(`list_book_pages`).
2. dry-run이면 `dry_run`이 각 페이지 텍스트를 읽어 청킹 결과만 계산하고 `data/reports/chunking/{subject}.json`(전체)과 `.txt`(사람이 읽는 표본)로 저장합니다. DB는 그대로입니다.
3. `--apply`면 `processing_runs`에 실행 기록 1건을 만들고 `pipeline.py`의 `run_pipeline` → `process_page`가 페이지마다 `stages.py`의 `chunk_theory`를 부릅니다.
4. `chunk_theory`는
   - 저장소의 추출 결과(`data/storage/books/{book_id}/{page_id}.text.json`, OCR이면 `.ocr.json`)를 줄 목록으로 읽고(`read_page_lines`),
   - 바로 앞 페이지의 `pages.page_metadata.chunking.end_state`(제목 경로)를 가져와서(`pages.get_previous_chunk_state`),
   - `chunking.py`의 `chunk_page`로 규칙을 적용합니다(순수 함수, DB 없음).
5. 결과는 `repositories/theory_chunks.py`의 `replace_page_chunks`가 **한 트랜잭션으로** 그 페이지의 기존 청크·기출 블록을 지우고 새로 넣습니다. 그래서 여러 번 돌려도 중복되지 않습니다.
   - `theory_chunks`: raw_text(원문 그대로), clean_text(표시 뺀 것), embedding_text(제목 경로 + clean_text), exam_clues, source_alignment(제목 경로·줄 범위), needs_review
   - `excluded_sections`: 기출 문제 블록(section_type=exam_question) + 원문 위치(source_region_ids)
   - `pages.page_metadata.chunking`: 청크 수, 다음 페이지가 이어받을 제목 경로 등
6. 페이지 상태는 VERIFIED가 되고, 아직 없는 시각자료 단계는 건너뛰었다고 `page_metadata.pipeline.skipped=["detect_visuals"]`에 남깁니다.

**임베딩 (`--stages embed`)**
1. 같은 `run_stages`가 VERIFIED/EMBEDDED 페이지를 골라 `stages.embed`를 부릅니다(`--pages 14,15`로 쪽 제한 가능).
2. `embed`는 그 페이지에서 needs_review=false인 청크의 embedding_text를 가져와(`list_for_embedding`), `embedding.py`의 `LocalEmbedder`(BGE-M3, 처음 한 번만 로드)로 벡터로 바꿉니다. 벡터는 길이 1로 정규화합니다.
3. `save_embeddings`가 `theory_chunks.embedding`에 저장하고 `embedding_enabled=true`, `needs_review=false`로 둡니다. 페이지 상태는 EMBEDDED가 됩니다.

**검색 확인**
- `backend/app/retrieval/search.py`의 `main`이 질문을 같은 모델로 벡터로 바꾼 뒤, 팀 규격 뷰 `v_searchable_theory`(임베딩 있고 검수 대기 아닌 청크)에서 가장 가까운 K개를 찾아 점수·교재·쪽·제목과 함께 출력합니다.

## 직접 확인하는 방법
1. 테스트: 루트에서 `uv run pytest` → **68 passed**. 실제 모델 테스트는 `uv run pytest -m embedding_model`(처음이면 모델을 `E:\hf_models`로 받음, 약 1~2분) → 1 passed.
2. 청킹 결과 미리보기(DB 변경 없음): `cd backend; uv run python -m app.ingestion.run_stages --subject subject1` → 요약에 `"chunks": 92`, `"excluded_blocks": 24`. 표본은 `data/reports/chunking/subject1.txt`에서 청크별 embedding_text·raw_text·exam_clues와 제외된 기출 블록을 볼 수 있습니다.
3. 전체 임베딩 완료 확인(지금 옆 창에서 실행 중): DataGrip에서
   - `SELECT processing_status, count(*) FROM mingyu.pages GROUP BY 1;` → 끝나면 EMBEDDED 324
   - `SELECT count(*) FROM mingyu.v_searchable_theory;` → 끝나면 605 (청크 616 − 검수 대기 11)
   - `SELECT count(*) FROM mingyu.theory_chunks WHERE NOT needs_review AND embedding IS NULL;` → 0
4. 검색 해 보기: `cd backend; uv run python -m app.retrieval.search "정성적 데이터와 정량적 데이터의 차이"` → 1과목 15쪽 "2. 데이터의 유형"이 1위(점수 약 0.75)로 나와야 합니다.
5. DataGrip에서 청크 보기: `SELECT title, clean_text, exam_clues, needs_review FROM mingyu.theory_chunks t JOIN mingyu.pages p ON p.id = t.page_id WHERE p.printed_page_number = '14' ORDER BY t.sort_order;`
   - 기출 블록: `SELECT title, source_region_ids FROM mingyu.excluded_sections LIMIT 5;`

## 아직 안 되는 것
- 전체 임베딩은 세션 종료 시점에 실행 중이었습니다(완료 확인은 다음 세션 시작 시 위 3번 쿼리로).
- 검색 품질 평가(질문 세트, hit@K, "자료에서 확인 불가" 점수 기준)는 설계만 했습니다. 질문 세트 `data/eval/questions.csv`는 직접 작성해야 합니다(형식은 ARCHITECTURE "검색 평가").
- 질문 → 답변 생성, 판정기(Jev), 리랭커, 키워드 검색은 아직 없습니다. 지금 검색은 벡터 검색만 됩니다.
- 이론 보충·수정, 프론트 화면, 시각자료(그림·표 crop), 오답노트는 설계만 되어 있습니다.
- 청킹 규칙의 알려진 한계: 표·그림 글자가 한 줄로 합쳐진 텍스트는 그대로 청크에 들어가고, 2과목 101쪽 첫 줄의 기출 조각이 청크에 남아 있습니다.
- 업로드 API로 새로 올린 사진은 시각자료 단계가 없어서 여전히 EXTRACTED에서 멈춥니다. 청킹·임베딩은 `run_stages --book-id`로 따로 돌려야 합니다.
