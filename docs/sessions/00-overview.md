# 00. 백엔드 전체 개요 (2026-09-30 기준)

이 문서는 코드를 직접 짜지 않은 사람이 지금까지 만든 백엔드를 이해하고, 직접 실행해서 확인할 수 있도록 쓴 설명서다. 설계 전체는 `docs/ARCHITECTURE.md`, 결정 이유는 `docs/DECISIONS.md`에 있다.

## 1. 한 문단 요약
지금 백엔드는 "과목별 자료(책)를 만들고 → 페이지 이미지를 올리면 → 서버가 뒤에서 글자를 읽어(OCR) 저장하고 → 처리 상태를 조회"하는 데까지 동작한다. 글자를 읽은 다음 단계(시각자료 잘라내기, 청킹, 임베딩)는 아직 만들지 않았기 때문에, 페이지는 `EXTRACTED`(글자 추출 완료) 상태에서 멈춘다. 질문에 답하는 기능, 판정기(Jev), 화면(프론트)은 아직 없다.

## 2. 폴더와 주요 파일

```text
adsp-study-rag/
├── .env                  # 비밀번호·API 키·모델 이름 등 설정값 (커밋 안 함)
├── .env.example          # .env에 어떤 값이 필요한지 보여주는 견본
├── pyproject.toml        # 파이썬 패키지 목록 (uv가 관리)
├── backend/
│   ├── app/
│   │   ├── main.py       # 서버 시작점
│   │   ├── core/config.py
│   │   ├── api/          # 외부에서 부르는 주소(API) 모음
│   │   ├── repositories/ # DB에 SQL을 보내는 곳
│   │   ├── ingestion/    # 업로드 후 처리(OCR 등)
│   │   ├── storage/      # 이미지·결과 파일 저장
│   │   └── db/           # DB 연결, 마이그레이션 실행기
│   ├── migrations/       # DB 구조 변경 SQL 파일 (001, 002 적용 완료)
│   └── tests/            # 자동 테스트
├── data/                 # 교재 이미지, 저장소 파일 (커밋 안 함)
└── docs/                 # 문서
```

| 파일 | 하는 일 |
|---|---|
| `backend/app/main.py` | 서버가 켜질 때 DB 커넥션 풀을 열고, 설정·저장소·처리 단계 목록을 준비한 뒤 API 라우터 3개(health, books, runs)를 붙인다. 서버가 꺼질 때 풀을 닫는다. |
| `backend/app/core/config.py` | `.env`를 읽어 `Settings` 객체로 만든다. 스키마 이름 형식 검사, OCR 모델 설정 검사도 여기서 한다. 코드는 모델 이름·스키마 이름을 직접 쓰지 않고 항상 이 설정에서 가져온다. |
| `backend/app/api/health.py` | `/health`(서버 살아 있나), `/health/db`(DB 연결되고 mingyu·mingyu_app 스키마가 있나) |
| `backend/app/api/books.py` | 과목 목록, 자료(book) 생성·조회, 페이지 목록, **이미지 업로드** |
| `backend/app/api/runs.py` | 업로드 1회의 처리 결과 조회(`/processing-runs/{run_id}`) |
| `backend/app/api/deps.py` | 각 API 함수에 DB 연결·설정·저장소를 넘겨주는 도우미 |
| `backend/app/repositories/books.py` | `mingyu.books`에 넣고 읽는 SQL (페이지 수·상태별 개수 집계 포함) |
| `backend/app/repositories/pages.py` | `mingyu.pages`에 넣고, 상태·메타데이터를 바꾸는 SQL |
| `backend/app/repositories/runs.py` | `mingyu.processing_runs`에 실행 기록을 만들고 마감하는 SQL |
| `backend/app/ingestion/images.py` | 업로드 파일이 진짜 이미지인지(PNG/JPEG/WEBP) 확인, OpenCV로 여는 함수(`decode_bgr`) |
| `backend/app/ingestion/pipeline.py` | 페이지마다 단계를 순서대로 실행하고, 끝날 때마다 상태를 바꾸고, 마지막에 실행 기록을 마감 |
| `backend/app/ingestion/stages.py` | 단계 함수 4개. `extract_text`만 구현, 나머지 3개는 "미구현" 신호를 던진다 |
| `backend/app/ingestion/ocr.py` | PaddleOCR 엔진. 처음 부를 때 모델을 한 번만 올리고, 이미지에서 줄 단위 글자·신뢰도·위치를 뽑는다 |
| `backend/app/storage/local.py` | 파일을 `data/storage/` 아래에 저장하고 `local://...` 주소를 돌려준다 (S3는 자리만 있음) |
| `backend/app/db/connection.py` | DB 커넥션 풀 생성, 스키마를 잠깐 지정하는 트랜잭션 도우미 |
| `backend/app/db/migrate.py` | `migrations/` 폴더의 SQL을 순서대로 적용하고 이력을 `mingyu_app.schema_migrations`에 남긴다 |

## 3. 요청이 흘러가는 순서

### 3-1. 과목(자료) 만들기
사용자가 `POST /books`에 제목·과목·자료 유형(textbook / lecture_note / personal_note)을 보내면 `api/books.py`의 `create_book` 함수가 받는다. 이 함수는 제목과 과목의 앞뒤 공백을 지우고 비어 있지 않은지 확인한 뒤 `repositories/books.py`의 `create_book`을 부른다. 여기서 `mingyu.books` 테이블에 한 행이 INSERT되고, 새로 생긴 id가 응답으로 돌아온다. "과목"은 별도 테이블이 아니라 books의 `subject` 컬럼 값이다. 그래서 `GET /subjects`는 books에 들어 있는 subject 값을 중복 없이 모아서 보여 줄 뿐이다.

### 3-2. 이미지 업로드
`POST /books/{book_id}/pages`로 이미지 여러 장을 보내면 `api/books.py`의 `upload_pages`가 받는다. 이 함수는 세 단계로 일한다.

먼저 **전부 검사**한다. 파일마다 크기가 `MAX_UPLOAD_MB`를 넘는지 보고, `ingestion/images.py`의 `inspect_image`로 진짜 PNG/JPEG/WEBP인지와 가로·세로 크기를 확인한다. 한 장이라도 문제가 있으면 여기서 오류를 돌려주고 아무것도 저장하지 않는다.

다음으로 **파일을 저장**한다. 각 페이지에 새 id를 붙이고, `storage/local.py`의 `save`로 `data/storage/books/{book_id}/{page_id}.jpg` 같은 위치에 원본 바이트를 그대로 저장한다. 돌려받은 `local://books/...` 주소를 기억해 둔다.

마지막으로 **DB에 기록**한다. 하나의 트랜잭션 안에서 `repositories/runs.py`의 `create_run`이 `mingyu.processing_runs`에 "이번 업로드" 기록 1건을 만들고(상태 RUNNING), `repositories/pages.py`의 `insert_pages`가 `mingyu.pages`에 페이지마다 한 행씩 넣는다. 이때 `source_s3_uri`에 저장 주소, `processing_run_id`에 방금 만든 실행 id, `page_metadata`에 업로드 순서(`upload_index`)와 원래 파일명(`original_filename`)이 들어간다. 처음 상태는 `RAW`다. DB 기록이 실패하면 방금 저장한 파일을 지워서 찌꺼기가 남지 않게 한다.

모든 것이 끝나면 백그라운드 작업으로 `ingestion/pipeline.py`의 `run_pipeline`을 예약하고, 사용자에게는 바로 `202 Accepted`와 `run_id`를 돌려준다. 즉 업로드 응답은 OCR이 끝나기를 기다리지 않는다.

### 3-3. 백그라운드 처리
`run_pipeline`은 업로드된 페이지를 한 장씩 꺼내 `process_page`에 넘긴다. `process_page`는 단계 목록(`DEFAULT_STAGES`)을 순서대로 실행한다.

1. **extract_text** (`stages.py`) — 먼저 `mingyu.pages.page_metadata.pipeline`에 "지금 extract_text 중"이라고 적는다. 그다음 `repositories/books.py`의 `get_material_type`으로 자료 유형을 본다. 개인노트(손필기)면 아직 방법이 없으므로 `NeedsReview`를 던져 페이지를 `REVIEW_REQUIRED`로 만든다. 인쇄체면 저장소에서 원본 바이트를 읽어 `images.py`의 `decode_bgr`로 이미지로 열고, `ocr.py`의 `get_engine(...).recognize`로 글자를 읽는다. 줄 단위 전체 결과(글자, 신뢰도, 위치)는 `data/storage/books/{book_id}/{page_id}.ocr.json`에 저장하고, 줄 수·평균 신뢰도·모델 이름 같은 요약만 `pages.page_metadata.ocr`에 넣는다. 단계가 끝나면 `repositories/pages.py`의 `set_status`가 `processing_status`를 `EXTRACTED`로 바꾼다.
2. **detect_visuals**, **chunk_theory**, **embed** — 아직 구현하지 않았다. 각 함수는 `StageNotImplemented`를 던지고, `process_page`는 이를 받아 상태는 `EXTRACTED` 그대로 두고 `page_metadata.pipeline.stopped = "not_implemented"`라고만 적는다.

도중에 예상 못 한 오류가 나면 그 페이지는 `FAILED`가 되고 오류 메시지가 `page_metadata.pipeline.error`에 남는다. 한 페이지가 실패해도 다음 페이지는 계속 처리한다.

모든 페이지가 끝나면 `repositories/runs.py`의 `finish_run`이 `mingyu.processing_runs`의 상태를 마감한다. 전부 성공이면 `SUCCESS`, 전부 실패면 `FAILED`, 그 밖에는 `PARTIAL`이다. 지금은 모든 페이지가 미구현 단계에서 멈추므로 정상이라도 **PARTIAL**이 나온다.

### 3-4. 상태 조회
`GET /processing-runs/{run_id}`는 `api/runs.py`의 `get_run`이 받아서, `processing_runs` 한 행과 그 실행에 속한 pages 목록(상태, 현재 단계, 오류)을 합쳐 돌려준다. `GET /books/{book_id}`는 그 책의 페이지 수와 상태별 개수(`status_counts`)를, `GET /books/{book_id}/pages`는 페이지 목록을 보여 준다. 응답에서 저장소 주소(`source_s3_uri`)는 내부 정보라 뺀다.

### 3-5. 한눈에 보기
```text
POST /books ──► api/books.create_book ──► repositories/books.create_book ──► mingyu.books
POST /books/{id}/pages
   └► api/books.upload_pages
        ├ images.inspect_image (검사)
        ├ storage.local.save ──► data/storage/books/{book_id}/{page_id}.jpg
        ├ runs.create_run ──► mingyu.processing_runs (RUNNING)
        ├ pages.insert_pages ──► mingyu.pages (RAW)
        └ (백그라운드) pipeline.run_pipeline
             └ process_page
                 ├ stages.extract_text ── ocr ──► .ocr.json 저장, pages.page_metadata.ocr, 상태 EXTRACTED
                 ├ detect_visuals / chunk_theory / embed ──► 미구현, EXTRACTED에서 멈춤
             └ runs.finish_run ──► mingyu.processing_runs (PARTIAL)
GET /processing-runs/{run_id} ──► api/runs.get_run ──► processing_runs + pages
```

## 4. 직접 확인하는 방법

### 4-1. 서버 켜기 (PowerShell)
```powershell
cd E:\자료실\adsp-study-rag\backend
uv run uvicorn app.main:app --reload
```
`Uvicorn running on http://127.0.0.1:8000`이 나오면 켜진 것이다. 끌 때는 `Ctrl+C`.

### 4-2. 브라우저에서 API 호출 (/docs)
1. `http://127.0.0.1:8000/docs`를 연다. API 목록이 나온다.
2. `GET /health/db` → **Try it out** → **Execute**. `"status": "ok"`, `schema`, `app_schema`가 모두 `true`면 DB 연결이 정상이다.
3. `POST /books` → Try it out → 본문에 아래처럼 넣고 Execute. 응답의 `id`(책 id)를 복사해 둔다.
   ```json
   {"title": "테스트 교재", "subject": "ADsP", "material_type": "textbook"}
   ```
4. `POST /books/{book_id}/pages` → Try it out → `book_id`에 붙여 넣고, `files`에서 이미지를 고른다(여러 장이면 **Add string item**으로 칸을 늘림). Execute → 응답 `202`와 `run_id`를 복사한다.
5. `GET /processing-runs/{run_id}`를 몇 번 실행해 본다.
   - 처음에는 `status: RUNNING`, 페이지는 `RAW`, `pipeline.stage: extract_text`
   - 끝나면 `status: PARTIAL`, 페이지는 `EXTRACTED`, `pipeline.stopped: not_implemented` ← 이게 지금의 정상 결과
   - 서버를 켠 뒤 **첫 업로드는 OCR 모델을 올리느라 더 오래 걸린다**. 이후 인쇄체 1장에 약 16초(맑은 고딕 A4 기준, 실제 교재는 아직 측정 안 함)
6. OCR 결과 파일은 탐색기에서 `E:\자료실\adsp-study-rag\data\storage\books\{book_id}\` 폴더를 열면 원본 이미지와 `{page_id}.ocr.json`이 보인다.

### 4-3. DataGrip에서 DB 확인
접속 정보는 `.env`의 `DB_HOST`, `DB_PORT`, `DB_NAME`(cert_rag), `DB_USER`, `DB_PASSWORD`. 스키마는 **mingyu**, **mingyu_app**만 본다(다른 팀원 스키마는 열지 않는다).

```sql
-- 내가 만든 자료
SELECT id, title, subject, material_type, created_at FROM mingyu.books ORDER BY created_at DESC;

-- 최근 업로드 실행 기록
SELECT id, status, page_count, success_count, review_count, failure_count, started_at, finished_at
FROM mingyu.processing_runs ORDER BY started_at DESC LIMIT 10;

-- 한 책의 페이지 상태와 OCR 요약
SELECT id, processing_status, quality_passed, review_required,
       page_metadata->>'original_filename' AS 파일명,
       page_metadata->'pipeline'           AS 단계정보,
       page_metadata->'ocr'->>'line_count' AS 줄수,
       page_metadata->'ocr'->>'mean_confidence' AS 평균신뢰도
FROM mingyu.pages
WHERE book_id = '여기에-책-id'
ORDER BY (page_metadata->>'upload_index')::int;

-- 적용된 마이그레이션
SELECT * FROM mingyu_app.schema_migrations;
```
기대 결과: 업로드한 장수만큼 pages 행이 있고, `processing_status = EXTRACTED`, `줄수`와 `평균신뢰도`에 값이 있다. theory_chunks, visual_assets는 아직 비어 있다.

### 4-4. 자동 테스트
```powershell
cd E:\자료실\adsp-study-rag
uv run pytest                 # 기본 테스트 (가짜 OCR 엔진 사용, 빠름)
uv run pytest -m ocr_model    # 실제 PaddleOCR 모델로 1건 (느림)
```

## 5. 아직 비어 있는 부분
- **처리 단계 3개**: 시각자료 검출·crop(`detect_visuals`), 이론 청킹(`chunk_theory`), 설명문·임베딩(`embed`). 그래서 `theory_chunks`, `visual_assets`, `visual_tables` 등은 비어 있고 페이지는 VERIFIED/EMBEDDED에 도달하지 못한다.
- **팀 교재 3권 반입**: `data/raw/adsp/`의 PDF·팀 텍스트를 넣는 스크립트 (다음 작업 1번)
- **손필기(개인노트) 추출**: 지금은 올리면 바로 REVIEW_REQUIRED
- **검색·질의 응답**: 질문 → 검색 → 답변 API 전부
- **판정기(Jev)**: `.env`에 키만 있고 코드에서 쓰지 않음
- **오답노트, 검수 보고서**: 설계만 있음 (ARCHITECTURE 참고)
- **재처리·삭제 API**: 실패하거나 멈춘 페이지를 다시 돌리는 기능, 자료 삭제 시 저장 파일 정리
- **서버 재시작 시 처리 중이던 페이지**는 중간 상태로 남는다(백그라운드 작업이 서버 프로세스 안에서 돌기 때문)
- **S3 저장소**: 자리만 있고 local만 동작
- **프론트엔드**: 폴더도 아직 없음
