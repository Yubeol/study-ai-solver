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
| POST | `/ocr` | 문제 사진 → 텍스트(질문 입력칸 채우기) |

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

응답(200):
```json
{"text": "다음 중 옳지 않은 것은?\n① … ② …", "line_count": 3, "mean_confidence": 0.88}
```
- 인쇄체 PaddleOCR(업로드 경로와 같은 엔진, `OCR_*` 설정). **첫 호출 때 모델을 올려서 느립니다**(처음이면 모델 다운로드 약 19MB).
- `text`: 줄을 위→아래, 같은 높이는 왼→오른 순서로 이은 문자열(같은 높이는 공백, 다른 줄은 `\n`). 교정하지 않습니다.
- 프론트 흐름: 사진 → `text`를 "추출된 문제" 칸에 채움 → 사용자가 고침 → `POST /qa`.

오류:
| 코드 | 경우 |
|---|---|
| 400 | 이미지가 아니거나 PNG/JPEG/WEBP가 아님 |
| 413 | `MAX_UPLOAD_MB` 초과 |
| 422 | `file` 없음 |

