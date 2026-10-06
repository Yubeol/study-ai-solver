-- 003: 답변 오류 신고(answer_reports)와 보충 이론 검토 대기(supplements) 테이블 (D-J-004).
-- {{schema}} = DB_SCHEMA(팀 규격), {{app_schema}} = DB_APP_SCHEMA 로 실행기가 치환한다.
-- 팀 규격 query_logs는 FK로 참조만 한다. 로그를 정리해도 신고·보충 자료는 남도록 ON DELETE SET NULL.

SET LOCAL lock_timeout = '5s';

-- 답변 오류 신고: 한 답변에 여러 건이면 행을 여러 개 쌓는다.
CREATE TABLE IF NOT EXISTS {{app_schema}}.answer_reports (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query_log_id       uuid REFERENCES {{schema}}.query_logs (id) ON DELETE SET NULL,
    question_text      text NOT NULL,                     -- 신고 당시 질문(스냅샷)
    answer_text        text,                              -- 신고 당시 답(스냅샷)
    report_type        text NOT NULL
                       CHECK (report_type IN ('wrong_answer', 'wrong_explanation', 'wrong_concept',
                                              'missing_concept', 'wrong_ocr', 'insufficient', 'other')),
    concept_details    jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(concept_details) = 'array'),
    detail             text NOT NULL DEFAULT '' CHECK (char_length(detail) <= 500),
    -- 근거 스냅샷: [{n, chunk_id, book_title, page, path, raw_text, vector_score, rerank_score, cited}]
    -- 재적재로 청크 id가 바뀌어도 신고 당시 근거를 볼 수 있게 원문까지 남긴다.
    evidence_snapshot  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence_snapshot) = 'array'),
    status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    resolved_at        timestamptz,
    CHECK ((status = 'resolved') = (resolved_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS answer_reports_query_log_idx ON {{app_schema}}.answer_reports (query_log_id);
CREATE INDEX IF NOT EXISTS answer_reports_status_created_idx ON {{app_schema}}.answer_reports (status, created_at);

-- 보충 이론: 바로 임베딩하지 않고 검토 대기로 둔다. 텍스트는 본문을, 이미지·PDF는 저장소 URI를 저장한다.
CREATE TABLE IF NOT EXISTS {{app_schema}}.supplements (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id          uuid REFERENCES {{app_schema}}.answer_reports (id) ON DELETE SET NULL,
    query_log_id       uuid REFERENCES {{schema}}.query_logs (id) ON DELETE SET NULL,
    source             text NOT NULL CHECK (source IN ('report', 'unanswerable')),  -- 오류 신고 안 / "확인 불가" 버튼
    kind               text NOT NULL CHECK (kind IN ('text', 'image', 'pdf')),
    title              text NOT NULL DEFAULT '',
    subject            text,
    question_text      text,                              -- 어떤 질문 때문에 넣은 자료인지(스냅샷)
    content_text       text,                              -- kind = text
    file_uri           text,                              -- kind = image / pdf (저장소 URI)
    original_filename  text,
    mime_type          text,
    byte_size          integer CHECK (byte_size >= 0),
    page_count         integer CHECK (page_count >= 1),   -- kind = pdf
    status             text NOT NULL DEFAULT 'pending_review'
                       CHECK (status IN ('pending_review', 'approved', 'rejected')),
    review_note        text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    reviewed_at        timestamptz,
    CHECK (kind <> 'text' OR content_text IS NOT NULL),
    CHECK (kind = 'text' OR file_uri IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS supplements_status_created_idx ON {{app_schema}}.supplements (status, created_at);
CREATE INDEX IF NOT EXISTS supplements_report_idx ON {{app_schema}}.supplements (report_id);
