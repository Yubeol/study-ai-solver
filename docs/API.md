# API

백엔드(FastAPI) 엔드포인트 설명입니다. 실제 스키마의 기준은 서버를 켰을 때의 `/docs`(Swagger)와 `/openapi.json`이고, 이 문서는 사람이 읽는 요약입니다. **API(요청·응답)를 바꾸는 PR은 이 문서도 같이 고칩니다.**

- 기본 주소: `http://127.0.0.1:8000` (프론트 개발 서버는 Vite 프록시로 넘김, `frontend/vite.config.ts`)
- 형식: JSON(UTF-8). 업로드만 `multipart/form-data`
- 오류 응답: `{"detail": "사람이 읽는 메시지"}`. 요청 검증 실패(422)는 FastAPI 기본 형식(`detail`이 배열)
- 프론트 타입: `frontend/src/api.ts` (`QaResponse` 등, 손으로 맞춤. 자동 생성 아님)

## 목록

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 서버 살아 있음 |
| GET | `/health/db` | DB 연결 + 스키마 2개 존재 확인 |
| GET | `/subjects` | 과목 목록 |
| POST | `/books` | 자료(book) 만들기 |
| GET | `/books?subject=` | 자료 목록(과목 필터 선택) |
| GET | `/books/{book_id}` | 자료 하나 |
| GET | `/books/{book_id}/pages` | 자료의 페이지 처리 상태 |
| POST | `/books/{book_id}/pages` | 페이지 이미지 업로드 → 백그라운드 처리 시작 |
| GET | `/processing-runs/{run_id}` | 처리 실행 하나 + 그 페이지들 |
| POST | `/qa` | 질문 → 답변·근거 |
| POST | `/ocr` | 문제 사진 → 문제 텍스트(Gemini 기본, 실패 시 PaddleOCR) |
| POST | `/answer-reports` | 답변 오류 신고 저장(근거 스냅샷 포함) |
| GET | `/answer-reports?status=&limit=` | 오류 신고 목록(최신순) |
| PATCH | `/answer-reports/{id}` | 신고 처리: 상태(open/resolved)·처리 결과·메모·연결 블록 |
| GET | `/blocks/{block_id}` | 블록의 지금 clean_text·수정 가능 여부(이론만 editable) |
| POST | `/block-corrections` | 이론 블록 수정안 등록(proposed) |
| GET | `/block-corrections?status=&block_id=&report_id=&limit=` | 수정안 목록(최신순) |
| POST | `/block-corrections/{id}/approve` | 승인 = 블록 clean_text 수정 + 재임베딩(바로 검색 반영) |
| POST | `/block-corrections/{id}/reject`, `/withdraw` | 반려 / 철회(블록 그대로) |
| POST | `/supplements` | 보충 이론 등록(텍스트/이미지/PDF). 텍스트는 등록 즉시 임베딩 → 다음 질문부터 검색 후보(D-M-035) |
| GET | `/supplements?status=&limit=` | 보충 이론 목록(검토 대기는 `pending_review`) |

## 상태 확인

### `GET /health`
```json
{"status": "ok"}
```

### `GET /health/db`
```json
{"status": "ok", "schema": true, "app_schema": true, "judge_provider": "none"}
```
- 스키마가 하나라도 없으면 `status: "degraded"`. DB에 접속하지 못하면 500.

## 과목·자료

### `GET /subjects`
`books.subject` 값 목록(중복 없음, 정렬). 예: `["ADsP"]`

### `POST /books` → 201
요청:
```json
{"title": "ADsP 1과목", "subject": "ADsP", "material_type": "textbook", "edition": null, "source_name": null}
```
- `material_type`: `textbook` / `lecture_note` / `personal_note`
- `title`·`subject`는 1~200자 / 1~100자, 공백뿐이면 422

응답: book 객체(아래) + `"page_count": 0, "status_counts": {}`

### `GET /books?subject=ADsP`, `GET /books/{book_id}`
book 객체:
```json
{
  "id": "uuid", "title": "…", "subject": "ADsP", "material_type": "textbook",
  "edition": null, "source_name": "team_import:1과목.pdf", "created_at": "2026-09-30T…",
  "page_count": 50, "status_counts": {"EMBEDDED": 50}
}
```
- 없는 `book_id`면 404 `"자료를 찾을 수 없습니다."`

### `GET /books/{book_id}/pages`
페이지 배열(업로드 순서). 저장소 경로(`source_s3_uri`)는 응답에서 뺍니다.
```json
[{
  "id": "uuid", "book_id": "uuid", "processing_run_id": "uuid",
  "source_width": 1654, "source_height": 2339,
  "processing_status": "EXTRACTED", "quality_passed": true, "review_required": false,
  "upload_index": 0, "original_filename": "p001.jpg",
  "pipeline": {"…": "단계별 상태·오류 (page_metadata.pipeline)"},
  "created_at": "…"
}]
```
- `processing_status`는 팀 규격 값입니다. 파이프라인 단계가 끝나면 EXTRACTED(텍스트 추출) → VERIFIED(청킹) → EMBEDDED(임베딩)로 바뀌고, 실패 FAILED, 검토 필요 REVIEW_REQUIRED. 업로드 직후 값과 전체 목록은 ARCHITECTURE·D-012.

## 업로드·처리

### `POST /books/{book_id}/pages` → 202
- `multipart/form-data`, 필드 이름 `files`(여러 개). PNG/JPEG/WEBP, 업로드 순서가 페이지 순서.
- **한 장이라도 검증에 실패하면 아무것도 저장하지 않습니다.**

응답:
```json
{"run_id": "uuid", "book_id": "uuid",
 "pages": [{"id": "uuid", "upload_index": 0, "original_filename": "p001.jpg"}]}
```
오류:
| 코드 | 경우 |
|---|---|
| 400 | 파일 없음, 이미지가 아님/깨짐 (`"파일명: 이유"`) |
| 404 | 자료 없음 |
| 413 | 한 파일이 `MAX_UPLOAD_MB`(기본 20MB) 초과 |

- 처리는 백그라운드로 진행되고, 지금은 detect_visuals 단계가 미구현이라 업로드 경로는 EXTRACTED에서 멈춥니다. 진행은 아래로 확인합니다.

### `GET /processing-runs/{run_id}`
```json
{
  "id": "uuid", "pipeline_version": "…", "paddle_model": null, "gemini_model": null, "embedding_model": null,
  "started_at": "…", "finished_at": null, "status": "RUNNING",
  "page_count": 3, "success_count": 0, "review_count": 0, "failure_count": 0, "cost_usd": null,
  "pages": ["… /books/{id}/pages 와 같은 페이지 객체"]
}
```
- `status`: RUNNING / SUCCESS / PARTIAL / FAILED. 없는 run이면 404 `"처리 기록을 찾을 수 없습니다."`

## 질의

### `POST /qa`
요청:
```json
{"question": "VIF가 10 넘게 나오면 무슨 문제가 있다는 거야?", "k": 5}
```
- `question`: 1~2000자(앞뒤 공백 제거). `k`: 근거 개수 1~20, 생략하면 `SEARCH_TOP_K`(5)

흐름: 질문 임베딩 → 벡터 후보 N개(`SEARCH_CANDIDATES_N`) → 리랭커 → 상위 K개 → "확인 불가" 3구간 → (회색 구간이면 판정기) → Gemini 답변 + 인용 검증 → `query_logs` 기록. 자세한 설계는 ARCHITECTURE "질의 흐름", D-024·D-025·D-028.

검색 대상은 서버 설정 `SEARCH_CORPUS`가 정합니다(요청 값으로 바꾸지 않음, D-M-033): `team_text`(팀 텍스트 이론 청크) / `common_json`(공통 JSON 블록: 이론·표·시각자료) / `mixed`(기본, 공통 JSON이 적재된 교재는 블록, 나머지 교재는 이론 청크).
**사용자 보충**(D-M-035): `SEARCH_CORPUS`와 상관없이 `POST /supplements`로 등록한 텍스트 보충(`rejected` 제외)도 벡터 후보 N개를 가져와 같은 cosine 점수로 합칩니다(상위 N개 → 리랭커). 기준값·리랭커·프롬프트는 같습니다.

응답(200, 답변한 경우):
```json
{
  "question": "VIF가 10 넘게 나오면 …",
  "corpus": "mixed",
  "candidate_sources": {"common_json": 9, "team_text": 1},
  "status": "answered",
  "confidence": "high",
  "zone": "answer",
  "zone_reason": "ok",
  "scores": {"vector_top": 0.64, "rerank_top": 0.97},
  "judge": null,
  "answer": "다중공선성 문제가 있다고 본다 [1].",
  "explanation": "…[1]",
  "confusions": "…[2]",
  "low_confidence": false,
  "low_confidence_reasons": [],
  "mcq_check": null,
  "cited": [1],
  "llm": {"model": "…", "usage": {}, "failed_attempts": [], "citation_check": {}},
  "llm_unanswerable": false,
  "evidence": [{
    "n": 1, "chunk_id": "uuid", "book_title": "…", "page": "79", "path": "제목 > 소제목",
    "raw_text": "교재 원문 그대로", "vector_score": 0.64, "rerank_score": 0.97, "cited": true,
    "corpus": "common_json", "kind": "table", "block_id": "S2:TABLE:TAB_79_01", "title": "KDD와 CRISP-DM 비교",
    "title_path": ["제목", "소제목"], "document_title": "2과목 …",
    "thumbnail_url": "https://…/thumbnails/…jpg 또는 null", "image_url": "https://…/crops/…jpg 또는 null",
    "related_visuals": []
  }],
  "citations": ["evidence 중 cited=true인 것"],
  "timings_ms": {"embed_ms": 100, "vector_ms": 400, "rerank_ms": 4000, "llm_ms": 1700, "visuals_ms": 20, "total_ms": 6300},
  "query_log_id": "uuid"
}
```

필드 메모:
- **`evidence[].page`는 문자열**(`printed_page_number`, 예 `"217"`)입니다. 없으면 null. 프론트 타입은 `string | number | null`.
- `answer`·`explanation`·`confusions` 안의 `[n]`은 `evidence[].n` 번호입니다. 범위 밖 번호는 서버가 지우고 `llm.citation_check`에 기록합니다.
- `raw_text`는 교재 원문 그대로(교정 없음), 항상 문자열입니다. 표·시각자료 블록은 원문이 글자 목록이라 줄바꿈으로 이어서 줍니다. 원문이 없는 코드 블록은 `clean_code`, 수식 블록은 `plain_text`를 줍니다(D-M-034). LLM에는 정리된 본문(이론은 `clean_text`, 표는 행 텍스트, 시각자료는 설명·구조·그림 속 글자)을 넘기지만 응답에서는 뺍니다.
- **`evidence[].chunk_id`는 `corpus`에 따라 가리키는 테이블이 다릅니다**: `corpus`가 `team_text`면 `theory_chunks.id`, `common_json`이면 `mingyu_app.blocks.id`. 두 경우 모두 UUID 문자열입니다.
- 검색 대상 전환(D-M-033)으로 **추가된 필드**(기존 필드는 그대로):
  | 필드 | 뜻 |
  |---|---|
  | `corpus` | `team_text` / `common_json` / `supplement` (이 근거가 나온 곳, `supplement`는 D-M-035) |
  | `kind` | `theory` / `table` / `visual` / `code` / `formula` / `supplement` (`team_text`는 항상 `theory`, 코드·수식은 3과목 블록, D-M-034. 사용자 보충은 `supplement`) |
  | `block_id` | 공통 JSON 블록 ID(예 `S2:TABLE:TAB_79_01`), `team_text`·`supplement`면 null |
  | `title`, `title_path` | 근거 제목, 제목 경로 목록(`path`는 이것을 ` > `로 이은 문자열) |
  | `document_title` | 공통 JSON 문서 제목(`team_text`면 책 제목) |
  | `thumbnail_url`, `image_url` | 표·시각자료 블록의 썸네일·원본 crop URL. 서버 설정 `ASSET_URL_TEMPLATE`이 비어 있거나 이론이면 null |
- **사용자 보충 근거**(`kind`·`corpus` = `supplement`, D-M-035): `chunk_id` = `mingyu_app.supplements.id`, `block_id` = null, `book_title`·`document_title` = `"사용자 보충"`, **`page` = null**(쪽 번호 없음, LLM 입력에는 `-`), `title`·`path` = 등록할 때 넣은 제목(`title_path`는 `[제목]`, 제목이 없으면 `""`·`[]`), `raw_text` = 입력한 본문 그대로, `thumbnail_url`·`image_url` = null, `related_visuals` = `[]`. Gemini·판정기에는 본문을 그대로 넘깁니다.
- **`evidence[].related_visuals`**(D-JW-008, 추가 필드): 근거가 공통 JSON **이론** 블록일 때 `block_relations`로 연결된 그림·표 목록. 없으면 `[]`(team_text·표·그림·보충 근거도 `[]`).
  ```json
  [{"block_id": "S2:VISUAL:VIS_78_01", "kind": "visual", "title": "…", "thumbnail_url": "https://…", "image_url": "https://…"}]
  ```
  - 관계 신뢰도 `RELATED_VISUAL_MIN_CONFIDENCE`(0.7) 이상, 근거당 최대 `RELATED_VISUAL_MAX`(3)개, 신뢰도 높은 순. 이미 `evidence`에 있는 블록은 빼고, 이미지 주소를 만들 수 없으면(키 없음·`ASSET_URL_TEMPLATE` 비어 있음) 뺀다.
  - `thumbnail_url`이 없으면 `image_url`로, 반대도 같게 채운다. S3 공개 주소라 `<img src>`로 바로 띄운다.
  - LLM 입력에는 넣지 않는다(화면 표시용). `query_logs.metadata.evidence[].related_visual_ids`에 block_id만 남는다. 조회가 실패해도 답변은 그대로(`[]`).
- 응답 최상위 `corpus`: 이 요청에 쓴 검색 대상(`SEARCH_CORPUS`). `candidate_sources`: 리랭크 전 벡터 후보 N개가 어느 쪽에서 왔는지 개수(개발 확인용). 보충이 후보에 들면 `"supplement": 개수`가 붙습니다(없으면 키 없음).
- `status`:
  | 값 | 뜻 | `answer` |
  |---|---|---|
  | `answered` | 근거로 답함 | 답 문장 |
  | `unanswerable` | 근거 부족(3구간 reject, 판정기 거절, LLM이 답할 수 없다고 함) | `"자료에서 확인 불가"` |
  | `error` | LLM 미설정·호출 실패 | `"답변 생성 실패(잠시 후 다시 시도)"`, `error`: `llm_not_configured` / `llm_failed` |
- `confidence`: `high` / `low` / `unanswerable` / null(error)
- `zone` / `zone_reason`("확인 불가" 3구간, 기준값은 `.env`의 `ANSWERABLE_*`):
  | zone | zone_reason | 경우 |
  |---|---|---|
  | reject | `no_result` | 검색 결과 없음 |
  | reject | `vector_below_floor` | 벡터 1위 < `ANSWERABLE_MIN_VECTOR_SCORE` |
  | reject | `rerank_below_floor` | 리랭커 1위 < `ANSWERABLE_MIN_RERANK_SCORE` |
  | gray | `rerank_gray` | 리랭커 1위가 하한 이상, 상한(`ANSWERABLE_CONFIDENT_RERANK_SCORE`) 미만 |
  | answer | `ok` | 리랭커 1위 ≥ 상한 |
  | answer | `no_reranker` | 리랭커 미설정(벡터 하한만 통과) |
- `low_confidence_reasons`(답했지만 "근거 확신 낮음"인 이유, 프론트 문구는 `ConfidenceNotice.tsx`):
  | 코드 | 뜻 |
  |---|---|
  | `gray_no_judge` | 회색 구간인데 판정기 없음(`JUDGE_PROVIDER=none`) |
  | `gray_judge_error` | 회색 구간, 판정기 호출 오류 |
  | `gray_judge_not_confident` | 회색 구간, 판정기 확률 < `JUDGE_CONFIDENT_MIN` |
  | `no_valid_citation` | 유효한 인용 없음 |
  | `mcq_inconsistent` | 객관식 보기별 판단과 고른 번호가 모순(`mcq_check.reasons`) |
- `judge`(회색 구간에서 판정기를 불렀을 때만, 아니면 null):
  `{provider, question_key: "can_answer", input, model, probability, can_answer, confident, thresholds: {can_answer_min, confident_min}, latency_ms, usage, attempts, error}`. `can_answer=false`면 Gemini를 부르지 않고 `unanswerable`.
- `mcq_check`(객관식으로 보이는 질문에 답한 경우만, 아니면 null):
  `{is_mcq: true, negative, chosen, option_verdicts: {"1": "적절하다" | "적절하지 않다" | "확인되지 않는다" | "알 수 없음", …}, consistent, reasons: ["사람이 읽는 문장"]}`
- `llm`·`llm_unanswerable`·`cited`는 개발 확인용입니다. reject 구간이면 `llm`은 null.
- `query_log_id`: 팀 규격 `query_logs`(`DB_SCHEMA`, 지금 `mingyu.query_logs`)에 남긴 행 id(기록 실패 시 null). `retrieved_theory_ids` 컬럼에는 `team_text` 근거(theory_chunks id)만 들어가고, 블록 근거는 `metadata.retrieved_block_ids`와 `metadata.evidence[].block_id`에, 사용자 보충 근거는 `metadata.retrieved_supplement_ids`(supplements.id 목록)에 남습니다. `metadata`에는 `corpus`·`candidate_sources`도 있습니다.

오류:
| 코드 | 경우 |
|---|---|
| 422 | `question`이 비었거나 2000자 초과, `k` 범위 밖 |
| 503 | 질의 모델 미로드(`PRELOAD_MODELS=false`) |
| 500 | DB 접속 실패 등 |

## 오류 신고

저장 위치: `DB_APP_SCHEMA.answer_reports`(마이그레이션 `003_jaewon_answer_reports.sql`, D-JW-004). 한 답변에 신고가 여러 번 오면 행이 하나씩 쌓입니다.

### `POST /answer-reports` → 201
요청(JSON, 프론트 오류 신고 화면 값):
```json
{
  "question": "다음 중 빅데이터 가치 패러다임의 변화 단계별 순서로 가장 적절한 것은? …",
  "type": "wrong_concept",
  "concept_details": ["관련 개념이 빠져 있어요"],
  "detail": "근거가 다른 단원이에요",
  "query_log_id": "990cdaba-f52e-425d-a7ee-b4250abe1a8f",
  "evidence": [{"n": 1, "chunk_id": "uuid", "book_title": "…", "page": "62", "path": "…", "raw_text": "…"}]
}
```
- `type`(또는 `report_type`, 프론트 이름): `wrong_answer`(답이 틀림) / `wrong_explanation`(해설이 틀림) / `wrong_concept`(개념·근거가 이상함) / `missing_concept`(관련 개념이 부족함) / `wrong_ocr`(문제를 잘못 읽음) / `insufficient`(설명이 부족함) / `other`
- `question`: 1~2000자. `detail`: 0~500자. `concept_details`: 문자열 최대 10개(각 1~100자)
- `query_log_id`(권장): `/qa` 응답의 `query_log_id`. 있으면 질문·답·근거를 그 기록에서 가져와 스냅샷으로 남깁니다(없는 id면 422).
- `evidence`(선택): `/qa` 응답의 `evidence` 그대로. 재적재로 청크가 없어졌거나 `query_log_id`가 없을 때 스냅샷에 씁니다. 받는 필드는 `n, chunk_id, book_title, page, path, raw_text, vector_score, rerank_score, cited, corpus, kind, block_id`(모두 선택)이고 나머지는 무시합니다.
- `answer`(선택): `query_log_id`가 없을 때만 답 스냅샷으로 씁니다. 그 밖의 필드(예: `explanation`)는 무시합니다.

응답:
```json
{
  "id": "uuid", "query_log_id": "uuid 또는 null",
  "question_text": "…", "answer_text": "정답은 ④이다 [1][2]. …",
  "report_type": "wrong_concept", "concept_details": ["관련 개념이 빠져 있어요"], "detail": "…",
  "evidence_snapshot": [{
    "n": 1, "chunk_id": "uuid", "book_title": "2024 ADsP 한 권으로 끝내기 이론편 - 1과목 데이터 이해", "page": "62",
    "path": "3장 … > 2. 빅데이터 회의론을 넘어 : 가치 패러다임의 변화", "raw_text": "교재 원문 그대로",
    "vector_score": 0.747, "rerank_score": 0.978, "cited": true,
    "corpus": "team_text", "kind": "theory", "block_id": null, "source": "db"
  }],
  "status": "open", "created_at": "2026-10-06T…", "resolved_at": null
}
```
- `evidence_snapshot[].source`: `db`(신고 시점에 청크를 조회해 채움) / `client`(요청의 `evidence`로 채움) / `missing`(둘 다 없음, `raw_text` null). `query_logs`에는 근거가 청크 id·쪽·점수로만 남아 있어서, 재적재 뒤에도 신고 당시 근거를 볼 수 있도록 원문까지 복사합니다.
- 기록된 근거에 `block_id`가 있으면(검색 대상 `common_json`·`mixed`) `mingyu_app.blocks`에서, 없으면 `theory_chunks`에서 조회합니다(D-M-033). `corpus`·`kind`·`block_id`는 그 전 기록이면 null입니다. 사용자 보충 근거는 조회되지 않으므로 화면이 보낸 `evidence` 값(`source: client`)으로 채웁니다.

### `GET /answer-reports?status=open&limit=50`
최신순 목록. `status`: `open` / `resolved`(생략하면 전체), `limit`: 1~200(기본 50). 항목 형식은 위 응답과 같습니다.

### `PATCH /answer-reports/{id}`
```json
{"status": "resolved", "resolution": "block_corrected", "resolution_note": "이론 수정함", "linked_block_ids": ["S1:THEORY:TH_62_02"], "reviewed_by": "재원"}
```
- 보낸 값만 바꿉니다(모두 선택, 하나 이상).
- `resolution`(처리 결과): `block_corrected`(이론 수정) / `supplement_added`(보충 이론) / `source_fix_requested`(표·시각자료 → JSON 수정 요청) / `prompt_issue` / `retrieval_issue` / `not_an_error` / `duplicate` / `other`.
- **`resolved`로 바꿀 때 `resolution`이 필요합니다**(없으면 422). `resolved`면 `resolved_at`이 채워지고 `open`으로 되돌리면 null.
- `linked_block_ids`: 근거가 기존 교재 청크(team_text)일 때 검토자가 대응 블록을 연결. 최대 20개.
- 응답: 신고 1건(`resolution`, `resolution_note`, `linked_block_ids`, `reviewed_by` 포함). 없는 id면 404.
- 이론 수정 승인(`/block-corrections/{id}/approve`)은 `report_id`가 있으면 신고를 자동으로 닫습니다.

## 보충 이론

저장 위치: `DB_APP_SCHEMA.supplements`(003, 임베딩 칸은 006). 상태는 `pending_review`로 저장되지만 **승인 화면이 없어서 `rejected`가 아니면 바로 검색 대상입니다**(D-M-035).
- **텍스트 보충**: 등록할 때 `"제목\n\n본문"`(제목이 없으면 본문만)을 서버에 올라온 임베더(/qa와 같은 `EMBEDDING_MODEL`, 정규화)로 임베딩해 같은 INSERT로 저장합니다. 다음 `/qa`부터 검색 후보에 들어가 근거로 나올 수 있습니다(`kind=supplement` 근거).
- **알려진 한계**: 파일만 올린 보충(이미지·PDF, 텍스트 없음)은 **저장만 하고 임베딩하지 않아 검색에 걸리지 않습니다**(사진 이론 OCR 텍스트화는 다음 개선). 긴 본문은 청크로 나누지 않고 한 덩어리로 임베딩합니다(모델 최대 길이 `EMBEDDING_MAX_SEQ_LENGTH` 뒤는 잘림). 인증이 없어 누구나 등록할 수 있고, 잘못 넣은 보충은 지금 DB에서 `status='rejected'`로 바꿔야 빠집니다.

### `POST /supplements` → 201
요청: `multipart/form-data`
| 필드 | 필수 | 설명 |
|---|---|---|
| `source` | O | `report`(오류 신고 화면 안에서 첨부) / `unanswerable`("확인 불가" 답변의 [이론 보충하기]) |
| `kind` | | `text` / `image` / `pdf`. 생략하면 자동: 파일이 PDF면 `pdf`, 그 밖의 파일은 `image`, 파일 없이 내용만 있으면 `text` |
| `title` | | 자료 제목(0~200자) |
| `content`(또는 `text`) | kind=text | 이론 내용(`SUPPLEMENT_MAX_TEXT_CHARS`자 이하). 프론트는 `text`로 보냄 |
| `file` | kind=image/pdf | 이미지 PNG/JPEG/WEBP 또는 PDF(`MAX_UPLOAD_MB` 이하, PDF는 `SUPPLEMENT_MAX_PDF_PAGES`쪽 이하) |
| `report_id` | | 오류 신고 안에서 첨부할 때 `POST /answer-reports` 응답의 `id` |
| `query_log_id` | | `/qa` 응답의 `query_log_id` |
| `question` | | 어떤 질문 때문에 넣은 자료인지(0~2000자) |
| `subject` | | 과목(저장만 함, 검색 필터에는 안 씀) |

화면 흐름(오류 신고 안에서 첨부): `POST /answer-reports` → 받은 `id`를 `report_id`로 `POST /supplements`.

응답:
```json
{
  "id": "uuid", "report_id": "uuid 또는 null", "query_log_id": "uuid 또는 null",
  "source": "report", "kind": "pdf", "title": "가치 패러다임 정리", "subject": null, "question_text": "…",
  "content_text": null, "original_filename": "정리.pdf", "mime_type": "application/pdf",
  "byte_size": 182344, "page_count": 3, "status": "pending_review", "review_note": null,
  "created_at": "2026-10-06T…", "reviewed_at": null,
  "embedding_model": "BAAI/bge-m3 또는 null", "searchable": false
}
```
파일은 저장소 `supplements/{id}.{png|jpg|webp|pdf}`에 두며, 저장소 위치(URI)와 벡터는 응답에 넣지 않습니다.
- 추가 필드(D-M-035): `embedding_model`(텍스트 보충을 임베딩한 모델, 파일 보충은 null), `searchable`(지금 검색 후보에 들어가는지 = 벡터 있음 + `rejected` 아님). 목록(`GET`)도 같은 형식입니다.

오류:
| 코드 | 경우 |
|---|---|
| 400 | 텍스트가 비었거나 너무 김 / 파일 없음 / 이미지·PDF가 아님 / PDF 쪽 수 초과 |
| 413 | `MAX_UPLOAD_MB` 초과 |
| 422 | `source`·`kind` 값이 틀림 / 없는 `report_id`·`query_log_id` |
| 503 | 텍스트 보충인데 임베딩 모델 미로드(`PRELOAD_MODELS=false`) |

- 400 메시지: 내용·파일이 모두 없으면 `"보충할 이론 내용을 입력하거나 파일을 선택해 주세요."`, `kind=text`인데 본문이 비었으면 `"보충할 이론 내용을 입력해 주세요."`(`detail`).

### `GET /supplements?status=pending_review&limit=50`
최신순 목록. `status`: `pending_review` / `approved` / `rejected`(생략하면 전체), `limit`: 1~200.

## 문제 사진 OCR

### `POST /ocr`
요청: `multipart/form-data`, 필드 `file` = 문제 사진 1장(PNG/JPEG/WEBP, `PROBLEM_OCR_MAX_UPLOAD_MB` 이하, 기본 12MB). 사진은 저장하지 않습니다.

응답(200, 기본 엔진 Gemini):
```json
{
  "text": "다음의 의사결정나무에서 B의 지니지수를 계산한 결과로 적절한 것은?\n[그림·표] 노드 A(Good 30, Bad 70)가 B(Good 10, Bad 40)와 C(Good 20, Bad 30)로 나뉜다.\n① 0.5\n② 0.48\n③ 0.38\n④ 0.32",
  "engine": "gemini",
  "model": "gemini-…",
  "problem_text": "다음의 의사결정나무에서 B의 지니지수를 계산한 결과로 적절한 것은?",
  "choices": ["0.5", "0.48", "0.38", "0.32"],
  "figure_description": "노드 A(Good 30, Bad 70)가 B(Good 10, Bad 40)와 C(Good 20, Bad 30)로 나뉜다.",
  "fallback_reason": null
}
```
- 엔진은 `.env`의 `PROBLEM_OCR_ENGINE`으로 고릅니다.
  - `google_vision`: Google Cloud Vision `DOCUMENT_TEXT_DETECTION`(`GOOGLE_VISION_API_KEY`, `GOOGLE_VISION_LANGUAGE_HINTS`). 사진의 **글자 전체**를 읽는 순서대로 돌려줍니다. 문제 하나만 골라내거나 선택지를 나누지 않으므로(`choices`는 빈 배열) 위아래 다른 문제 글자는 사용자가 입력칸에서 지웁니다. 사진 1장 = Vision 1단위(월 1,000단위 무료).
  - `gemini`(기본): Gemini 비전(`PROBLEM_EXTRACT_MODEL`, 프롬프트 `prompts/problem_extract_*`)으로 가장 온전한 문제 1개와 선택지만 옮겨 적습니다(`choices`, `figure_description` 채움). `choices`는 번호 기호 없이 보기 내용만, `text` = 문제 → `[그림·표] 설명` → `① …` 선택지 한 줄씩(번호 기호는 `text`를 만들 때 붙임).
- 고른 엔진의 키가 없거나 호출이 실패하면 **PaddleOCR**로 읽습니다(`engine: "paddleocr"`). `fallback_reason`: `vision_not_configured` / `vision_failed` / `llm_not_configured` / `llm_failed`. PaddleOCR은 첫 호출 때 모델을 올려서 느립니다. 프론트는 `/qa`와 별도로 `VITE_OCR_TIMEOUT_SECONDS`(기본 330초)까지 기다립니다.
- 프론트 흐름: 사진 → `text`를 "추출된 문제" 칸에 채움 → 사용자가 고침 → `POST /qa`.

오류:
| 코드 | 경우 |
|---|---|
| 400 | 이미지가 아니거나 PNG/JPEG/WEBP가 아님 |
| 413 | `PROBLEM_OCR_MAX_UPLOAD_MB` 초과 |
| 422 | `file` 없음 |
| 503 | 대체 경로 PaddleOCR까지 실패(모델 파일 없음 등). `detail`: "사진에서 문제를 읽지 못했습니다. 문제를 직접 입력해 주세요." |

## 이론 수정 (오류 신고 처리)

대상: 공통 JSON **이론 블록**(`block_type = theory`)의 `clean_text`만(D-JW-007, 005). 블록은 `/qa` 근거의 `block_id`(예: `S1:THEORY:TH_62_02`)로 가리킵니다. 표·시각자료는 400 → 신고를 `resolution: source_fix_requested`로 닫습니다(데이터 담당 JSON 수정 요청).

### `GET /blocks/{block_id}`
수정 화면에 띄울 지금 내용.
```json
{
  "block_id": "S1:THEORY:TH_62_02", "kind": "theory", "block_type": "theory", "title": "가치 패러다임의 변화",
  "title_path": ["3장 …", "2. 빅데이터 회의론을 넘어 : 가치 패러다임의 변화"],
  "path": "3장 … > 2. 빅데이터 회의론을 넘어 : 가치 패러다임의 변화", "page": 62,
  "document_title": "…", "clean_text": "지금 본문", "editable": true,
  "active_correction_id": null, "updated_at": "2026-10-08T…"
}
```
`kind`는 `/qa` 근거의 `kind`와 같은 값(`block_type`과 같음), `path`는 `title_path`를 " > "로 이은 문자열. `editable`: 이론 블록이고 원문 해시가 있으면 true. 없는 block_id면 404.

### `POST /block-corrections` → 201
```json
{"block_id": "S1:THEORY:TH_62_02", "new_clean_text": "고친 본문(1~2,000자)", "reason": "설명 보충", "report_id": "신고 id(선택)"}
```
응답: 수정안 1건(`status: "proposed"`). 블록은 아직 바뀌지 않습니다.
```json
{
  "id": "uuid", "block_id": "S1:THEORY:TH_62_02", "report_id": "uuid 또는 null",
  "base_clean_text": "등록 당시 본문", "base_clean_text_hash": "JSON 원문 해시", "new_clean_text": "고친 본문",
  "reason": "설명 보충", "status": "proposed", "review_note": "", "reviewed_by": null, "applied_note": null,
  "created_at": "…", "reviewed_at": null, "applied_at": null
}
```
오류: 400(공백·탭·줄바꿈뿐 / 이론 블록 아님 / 지금 내용과 같음 / 원문 해시 없음), 404(블록 없음), 422(2,000자 초과·없는 report_id). 앞뒤 공백은 지우고 저장합니다.

### `POST /block-corrections/{id}/approve`
```json
{"reviewed_by": "재원", "review_note": "확인", "resolve_report": true}
```
- 한 트랜잭션에서 블록 `clean_text`, `embedding_text`(적재와 같은 `common_json.embedding_text(block_from_row(행), with_path=True)`, 리랭커가 읽는 칸), `embedding`(그 텍스트로 계산)을 같이 바꿉니다(`embedding_text_hash`·`embedding_model`도 갱신). 다음 질문부터 검색·근거에 반영됩니다.
- 같은 블록에 이미 적용된 수정이 있으면 그 수정은 `superseded`가 됩니다(블록당 적용 중인 수정 1개).
- `report_id`가 있고 `resolve_report`가 true(기본)면 그 신고를 `resolved` + `resolution: block_corrected`로 닫습니다.
- 응답: 수정안(`status: "applied"`, `applied_at` 채움).
- 오류: 404(없음), 409(proposed가 아님 / 수정안 등록 뒤 교재 원문이 바뀜 → 수정안은 `stale`, 새로 등록), 503(서버에 임베딩 모델 없음).
- `blocks.source_clean_text_hash`·`raw_text`는 바꾸지 않습니다(JSON 원문 기준, 재적재 비교용). 공통 JSON을 다시 적재하면 원문으로 덮어써집니다(수정 기록은 남음).

### `POST /block-corrections/{id}/reject`, `POST /block-corrections/{id}/withdraw`
```json
{"reviewed_by": "재원", "review_note": "근거 없음"}
```
`proposed`만 가능(아니면 409). 블록은 그대로.

### `GET /block-corrections?status=proposed&block_id=&report_id=&limit=50`
최신순. `status`: proposed / applied / rejected / withdrawn / stale / superseded (approved는 후속 적재 단계용).
