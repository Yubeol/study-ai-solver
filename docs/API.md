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
| POST | `/ocr` | 문제 사진 → 문제 텍스트(Google Vision 기본, 실패 시 PaddleOCR) |
| POST | `/answer-reports` | 답변 오류 신고 저장(근거 스냅샷 포함) |
| GET | `/answer-reports?status=&limit=` | 오류 신고 목록(최신순) |
| PATCH | `/answer-reports/{id}` | 신고 하나의 처리 상태 변경(open/resolved) |
| POST | `/supplements` | 보충 이론 등록(텍스트/이미지/PDF) → 검토 대기, 임베딩 안 함 |
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

응답(200, 답변한 경우):
```json
{
  "question": "VIF가 10 넘게 나오면 …",
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
    "n": 1, "chunk_id": "uuid", "book_title": "…", "page": "217", "path": "제목 > 소제목",
    "raw_text": "교재 원문 그대로", "vector_score": 0.64, "rerank_score": 0.97, "cited": true
  }],
  "citations": ["evidence 중 cited=true인 것"],
  "timings_ms": {"embed_ms": 100, "vector_ms": 400, "rerank_ms": 4000, "llm_ms": 1700, "total_ms": 6300},
  "query_log_id": "uuid"
}
```

필드 메모:
- **`evidence[].page`는 문자열**(`printed_page_number`, 예 `"217"`)입니다. 없으면 null. 프론트 타입은 `string | number | null`.
- `answer`·`explanation`·`confusions` 안의 `[n]`은 `evidence[].n` 번호입니다. 범위 밖 번호는 서버가 지우고 `llm.citation_check`에 기록합니다.
- `raw_text`는 교재 원문 그대로(교정 없음). LLM에는 `clean_text`를 넘기지만 응답에서는 뺍니다.
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
- `query_log_id`: `mingyu_app.query_logs`에 남긴 행 id(기록 실패 시 null).

오류:
| 코드 | 경우 |
|---|---|
| 422 | `question`이 비었거나 2000자 초과, `k` 범위 밖 |
| 503 | 질의 모델 미로드(`PRELOAD_MODELS=false`) |
| 500 | DB 접속 실패 등 |

## 문제 사진 OCR

### `POST /ocr`
요청: `multipart/form-data`, 필드 `file` = 문제 사진 1장(PNG/JPEG/WEBP, `MAX_UPLOAD_MB` 이하). 사진은 저장하지 않습니다.

응답(200, 기본 엔진 Google Vision):
```json
{
  "text": "16 데이터 분석 조직 구조에 대한 설명으로 옳은 것은?\n① 기능 중심 조직은 …\n② 분산 조직은 …",
  "engine": "google_vision",
  "model": null,
  "problem_text": "(text와 같음)",
  "choices": [],
  "figure_description": "",
  "fallback_reason": null
}
```
- 엔진은 `.env`의 `PROBLEM_OCR_ENGINE`으로 고릅니다.
  - `google_vision`(기본): Google Cloud Vision `DOCUMENT_TEXT_DETECTION`(`GOOGLE_VISION_API_KEY`, `GOOGLE_VISION_LANGUAGE_HINTS`). 사진의 **글자 전체**를 읽는 순서대로 돌려줍니다. 문제 하나만 골라내거나 선택지를 나누지 않으므로(`choices`는 빈 배열) 위아래 다른 문제 글자는 사용자가 입력칸에서 지웁니다. 사진 1장 = Vision 1단위(월 1,000단위 무료).
  - `gemini`: Gemini 비전(`PROBLEM_EXTRACT_MODEL`, 프롬프트 `prompts/problem_extract_*`)으로 가장 온전한 문제 1개와 선택지만 옮겨 적습니다(`choices`, `figure_description` 채움). `text` = 문제 → `[그림·표] 설명` → `① …` 선택지 한 줄씩.
- 고른 엔진의 키가 없거나 호출이 실패하면 **PaddleOCR**로 읽습니다(`engine: "paddleocr"`). `fallback_reason`: `vision_not_configured` / `vision_failed` / `llm_not_configured` / `llm_failed`. PaddleOCR은 첫 호출 때 모델을 올려서 느립니다.
- 프론트 흐름: 사진 → `text`를 "추출된 문제" 칸에 채움 → 사용자가 고침 → `POST /qa`.

오류:
| 코드 | 경우 |
|---|---|
| 400 | 이미지가 아니거나 PNG/JPEG/WEBP가 아님 |
| 413 | `MAX_UPLOAD_MB` 초과 |
| 422 | `file` 없음 |

## 오류 신고

저장 위치: `DB_APP_SCHEMA.answer_reports`(마이그레이션 `003_jaewon_answer_reports.sql`, D-J-004). 한 답변에 신고가 여러 번 오면 행이 하나씩 쌓입니다.

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
- `type`: `wrong_answer`(답이 틀림) / `wrong_explanation`(해설이 틀림) / `wrong_concept`(개념·근거가 이상함) / `missing_concept`(관련 개념이 부족함) / `wrong_ocr`(문제를 잘못 읽음) / `insufficient`(설명이 부족함) / `other`
- `question`: 1~2000자. `detail`: 0~500자. `concept_details`: 문자열 최대 10개(각 1~100자)
- `query_log_id`(권장): `/qa` 응답의 `query_log_id`. 있으면 질문·답·근거를 그 기록에서 가져와 스냅샷으로 남깁니다(없는 id면 422).
- `evidence`(선택): `/qa` 응답의 `evidence` 그대로. 재적재로 청크가 없어졌거나 `query_log_id`가 없을 때 스냅샷에 씁니다.
- `answer`(선택): `query_log_id`가 없을 때만 답 스냅샷으로 씁니다.

응답:
```json
{
  "id": "uuid", "query_log_id": "uuid 또는 null",
  "question_text": "…", "answer_text": "정답은 ④이다 [1][2]. …",
  "report_type": "wrong_concept", "concept_details": ["관련 개념이 빠져 있어요"], "detail": "…",
  "evidence_snapshot": [{
    "n": 1, "chunk_id": "uuid", "book_title": "2024 ADsP 한 권으로 끝내기 이론편 - 1과목 데이터 이해", "page": "62",
    "path": "3장 … > 2. 빅데이터 회의론을 넘어 : 가치 패러다임의 변화", "raw_text": "교재 원문 그대로",
    "vector_score": 0.747, "rerank_score": 0.978, "cited": true, "source": "db"
  }],
  "status": "open", "created_at": "2026-10-06T…", "resolved_at": null
}
```
- `evidence_snapshot[].source`: `db`(신고 시점에 청크를 조회해 채움) / `client`(요청의 `evidence`로 채움) / `missing`(둘 다 없음, `raw_text` null). `query_logs`에는 근거가 청크 id·쪽·점수로만 남아 있어서, 재적재 뒤에도 신고 당시 근거를 볼 수 있도록 원문까지 복사합니다.

### `GET /answer-reports?status=open&limit=50`
최신순 목록. `status`: `open` / `resolved`(생략하면 전체), `limit`: 1~200(기본 50). 항목 형식은 위 응답과 같습니다.

### `PATCH /answer-reports/{id}`
```json
{"status": "resolved"}
```
신고 하나의 상태만 바꿉니다. `resolved`면 `resolved_at`이 채워지고 `open`으로 되돌리면 null. 없는 id면 404.

## 보충 이론

저장 위치: `DB_APP_SCHEMA.supplements`(003). **검토 대기(`pending_review`)로만 저장하고 임베딩하지 않습니다.** 승인 → 추출·청킹·임베딩은 별도 작업입니다.

### `POST /supplements` → 201
요청: `multipart/form-data`
| 필드 | 필수 | 설명 |
|---|---|---|
| `source` | O | `report`(오류 신고 화면 안에서 첨부) / `unanswerable`("확인 불가" 답변의 [이론 보충하기]) |
| `kind` | O | `text` / `image` / `pdf` |
| `title` | | 자료 제목(0~200자) |
| `content` | kind=text | 이론 내용(`SUPPLEMENT_MAX_TEXT_CHARS`자 이하) |
| `file` | kind=image/pdf | 이미지 PNG/JPEG/WEBP 또는 PDF(`MAX_UPLOAD_MB` 이하, PDF는 `SUPPLEMENT_MAX_PDF_PAGES`쪽 이하) |
| `report_id` | | 오류 신고 안에서 첨부할 때 `POST /answer-reports` 응답의 `id` |
| `query_log_id` | | `/qa` 응답의 `query_log_id` |
| `question` | | 어떤 질문 때문에 넣은 자료인지(0~2000자) |
| `subject` | | 과목 |

화면 흐름(오류 신고 안에서 첨부): `POST /answer-reports` → 받은 `id`를 `report_id`로 `POST /supplements`.

응답:
```json
{
  "id": "uuid", "report_id": "uuid 또는 null", "query_log_id": "uuid 또는 null",
  "source": "report", "kind": "pdf", "title": "가치 패러다임 정리", "subject": null, "question_text": "…",
  "content_text": null, "original_filename": "정리.pdf", "mime_type": "application/pdf",
  "byte_size": 182344, "page_count": 3, "status": "pending_review", "review_note": null,
  "created_at": "2026-10-06T…", "reviewed_at": null
}
```
파일은 저장소 `supplements/{id}.{png|jpg|webp|pdf}`에 두며, 저장소 위치(URI)는 응답에 넣지 않습니다.

오류:
| 코드 | 경우 |
|---|---|
| 400 | 텍스트가 비었거나 너무 김 / 파일 없음 / 이미지·PDF가 아님 / PDF 쪽 수 초과 |
| 413 | `MAX_UPLOAD_MB` 초과 |
| 422 | `source`·`kind` 값이 틀림 / 없는 `report_id`·`query_log_id` |

### `GET /supplements?status=pending_review&limit=50`
최신순 목록. `status`: `pending_review` / `approved` / `rejected`(생략하면 전체), `limit`: 1~200.
