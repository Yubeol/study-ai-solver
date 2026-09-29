# ARCHITECTURE

## 저장소 구조 (계획, 첫 세션에서 확정)
```text
adsp-study-rag/
├── pyproject.toml / uv.lock / .python-version   # 백엔드 Python 환경 (루트)
├── .env / .env.example
├── CLAUDE.md
├── backend/
│   ├── app/          # FastAPI 앱 (api, core, ingestion, retrieval, judge, llm, storage)
│   ├── migrations/   # 번호 붙은 SQL 파일 (DDL 변경 이력)
│   └── tests/
├── frontend/         # React + Vite
├── docs/
└── data/             # 로컬 이미지/산출물 (gitignore)
```

## DB (확정)
- 팀 공유 PostgreSQL 16.15, DB `cert_rag`, pgvector 0.8.6, pg_trgm 1.6, pgcrypto 1.3
- 내 스키마: `mingyu` (팀 규격 테이블, 팀원이 생성 완료). 다른 스키마: jaewon, sugi, sumin (접근 금지)
- 내 서비스용 스키마: `mingyu_app` (미생성)

### mingyu 스키마 (팀 규격, 기존)
- 자료 계층: books → chapters(parent_chapter_id 계층, sort_order) → pages(source_s3_uri, processing_status CHECK, quality_passed, review_required, processing_run_id)
- 검색 대상: theory_chunks(embedding_text NOT NULL, embedding vector(1024), embedding_enabled, needs_review), visual_assets(visual_type CHECK, crop_s3_uri, 구조 JSONB 다수, embedding_text, embedding, crop_complete)
- 구조 데이터: visual_groups, visual_tables(page 단위 독립, 임베딩 없음), formulas(임베딩 없음)
- 관계: theory_visual_links, visual_formula_links, concept_relations, concepts(canonical_name, aliases)
- 운영: processing_runs, constraint_presets(settings JSONB), query_logs(question_text, question_image_s3_uri, retrieved_*_ids, answer, 비용)
- 인덱스: theory_chunks HNSW(vector_cosine_ops, WHERE embedding_enabled), visual_assets HNSW(cosine), theory_chunks.clean_text trgm, books.title trgm
- 뷰: v_searchable_theory(enabled + 임베딩 있음 + needs_review=false), v_searchable_visual(임베딩 있음 + needs_review=false + crop_complete), v_review_queue
- 주의: 표·수식은 이론과 직접 링크가 없으므로 page_id / concept_id로 모아 온다.

### mingyu 스키마 보완 (계획, 컬럼/인덱스 추가만)
- books: subject, material_type(강의노트/교재/개인노트) — 과목 분리와 출처 표시용
- theory_chunks: sort_order — 페이지 내 순서, 앞뒤 문맥 복원
- theory_chunks, visual_assets: processing_run_id — 청크 단위 실행 추적
- trgm 인덱스: visual_assets.embedding_text, concepts.canonical_name

### mingyu_app 스키마 (계획)
- problems: 문제 이미지 URI, 상태
- problem_extractions: 추출기, 문제문, 보기(JSONB), 수식, 신뢰도
- solutions: 사용 모델, 답, 풀이, 경로(빠른/재풀이), 확신 라벨, 적용 제약 프리셋
- solution_evidence: (스키마, 종류, id), 순위, 점수, 인용 원문 스냅샷
- judgments: 판정 제공자, 질문 키, 답(JSONB), 신뢰도, 지연, 비용
- 요약 로그는 팀 규격 query_logs에도 기록한다.

## 자료 적재 흐름 (업로드 → 백그라운드 처리)
업로드 API가 파일을 저장소(local 또는 S3)에 저장하고 books/pages를 만든 뒤 백그라운드 작업을 시작한다. 각 단계에서 pages.processing_status를 갱신해 화면에 처리 상태를 보여준다.
1. 텍스트 추출: 교재·강의노트(인쇄체) → PaddleOCR / 개인노트(손필기) → 비전 LLM
2. 기울기 보정, 시각자료 자동 crop(OpenCV/Pillow), 세트 그림 묶기(visual_groups), 표 구조화
3. 이론 청킹(sort_order 부여), 수식 구조화, 제외 영역(예제/기출/코드) 분리
4. 시각자료 설명문 + embedding_text 생성: crop + 관련 이론 문장 2~5개 → GEMINI_MODEL_LITE, 품질 낮은 것만 GEMINI_MODEL_STRONG 재처리
5. 로컬 임베딩(BGE-M3, 1024) → 저장, 링크 테이블 채우기

## 질의 흐름
1. 입력: 질문 텍스트 또는 문제 이미지(비전 LLM으로 문제문·보기·수식 추출)
2. 검색: 선택 과목 범위에서 하이브리드 검색(벡터 + trgm), 이론 → 연결된 시각자료·같은 페이지 표/수식 확장
3. 답변 가능 판정(판정기): 근거로 답할 수 없으면 LLM 호출 없이 "자료에서 확인 불가"
4. 답변 생성: 기본 시험모드 + 선택한 제약 프리셋, 근거 번호 인용 강제
5. 근거 일치 판정(판정기): 낮으면 강한 모델 재생성 또는 "확신 낮음" 표시
6. 저장: mingyu_app 상세 + query_logs 요약

## 판정기 (교체 가능 모듈)
- 인터페이스: `can_answer`(근거로 답 가능?), `classify`(단원·유형 선택), `choose`(객관식 후보), `verify`(답이 근거와 일치?)
- 구현체: `jev_typesafe`, `jev_cloudflare`, `llm`(Gemini 구조화 출력), `none`(판정 생략)
- `JUDGE_PROVIDER`로 선택. 신뢰도 임계값은 제공자별로 따로 둔다.

## 화면 (React + Vite)
- A. 자료 업로드: 과목 선택/생성, 자료 유형, 다중 업로드, 처리 상태
- B. 공부: 과목, 질문 또는 문제 사진, 제약 프리셋, 답변 + 근거 청크 + 출처
- C. 관리: 과목·자료 목록, 삭제/재임베딩, 사용 로그