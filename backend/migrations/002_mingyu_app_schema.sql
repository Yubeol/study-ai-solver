-- 002: 서비스 전용 스키마(DB_APP_SCHEMA)와 테이블 생성.
-- {{schema}} = DB_SCHEMA(팀 규격), {{app_schema}} = DB_APP_SCHEMA 로 실행기가 치환한다.
-- 팀 규격 테이블은 참조만 하고(ON DELETE SET NULL) 변경하지 않는다.

SET LOCAL lock_timeout = '5s';

CREATE SCHEMA IF NOT EXISTS {{app_schema}};

-- 마이그레이션 적용 이력
CREATE TABLE IF NOT EXISTS {{app_schema}}.schema_migrations (
    filename    text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

-- 사용자가 올린 문제(사진 또는 텍스트)
CREATE TABLE IF NOT EXISTS {{app_schema}}.problems (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject        text,
    input_type     text NOT NULL CHECK (input_type IN ('image', 'text')),
    image_uri      text,
    question_text  text,
    status         text NOT NULL DEFAULT 'RECEIVED'
                   CHECK (status IN ('RECEIVED', 'EXTRACTED', 'SOLVED', 'FAILED')),
    metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (input_type <> 'image' OR image_uri IS NOT NULL),
    CHECK (input_type <> 'text' OR question_text IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS problems_created_idx ON {{app_schema}}.problems (created_at);

-- 문제 사진에서 추출한 구조화 결과
CREATE TABLE IF NOT EXISTS {{app_schema}}.problem_extractions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    problem_id    uuid NOT NULL REFERENCES {{app_schema}}.problems (id) ON DELETE CASCADE,
    extractor     text NOT NULL,                       -- 사용 모델/도구 이름
    problem_text  text,
    choices       jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(choices) = 'array'),
    formulas      jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(formulas) = 'array'),
    confidence    real CHECK (confidence BETWEEN 0 AND 1),
    raw_output    jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS problem_extractions_problem_idx
    ON {{app_schema}}.problem_extractions (problem_id);

-- 답변(풀이)
CREATE TABLE IF NOT EXISTS {{app_schema}}.solutions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    problem_id            uuid REFERENCES {{app_schema}}.problems (id) ON DELETE CASCADE,
    query_log_id          uuid REFERENCES {{schema}}.query_logs (id) ON DELETE SET NULL,
    question_text         text NOT NULL,
    model                 text,                          -- NULL: LLM 호출 없이 끝남(확인 불가 등)
    answer                text NOT NULL,
    explanation           text,
    path                  text NOT NULL DEFAULT 'fast' CHECK (path IN ('fast', 'retry')),
    confidence_label      text CHECK (confidence_label IN ('high', 'medium', 'low', 'unanswerable')),
    constraint_preset_id  uuid REFERENCES {{schema}}.constraint_presets (id) ON DELETE SET NULL,
    preset_snapshot       jsonb,
    latency_ms            integer CHECK (latency_ms >= 0),
    token_usage           jsonb,
    cost_usd              numeric,
    created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS solutions_problem_idx ON {{app_schema}}.solutions (problem_id);
CREATE INDEX IF NOT EXISTS solutions_created_idx ON {{app_schema}}.solutions (created_at);

-- 답변 근거 (검색 결과 스냅샷)
CREATE TABLE IF NOT EXISTS {{app_schema}}.solution_evidence (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    solution_id    uuid NOT NULL REFERENCES {{app_schema}}.solutions (id) ON DELETE CASCADE,
    source_schema  text NOT NULL,
    source_kind    text NOT NULL CHECK (source_kind IN ('theory', 'visual', 'table', 'formula')),
    source_id      uuid NOT NULL,
    rank           integer NOT NULL CHECK (rank >= 1),
    score          real,
    quoted_text    text,                                 -- 답변 당시 인용 원문 스냅샷
    UNIQUE (solution_id, rank)
);
CREATE INDEX IF NOT EXISTS solution_evidence_source_idx
    ON {{app_schema}}.solution_evidence (source_kind, source_id);

-- 판정기 호출 기록
CREATE TABLE IF NOT EXISTS {{app_schema}}.judgments (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    solution_id   uuid REFERENCES {{app_schema}}.solutions (id) ON DELETE CASCADE,
    problem_id    uuid REFERENCES {{app_schema}}.problems (id) ON DELETE CASCADE,
    provider      text NOT NULL,                         -- JUDGE_PROVIDER 값
    question_key  text NOT NULL CHECK (question_key IN ('can_answer', 'classify', 'choose', 'verify')),
    answer        jsonb NOT NULL,
    confidence    real CHECK (confidence BETWEEN 0 AND 1),
    latency_ms    integer CHECK (latency_ms >= 0),
    cost_usd      numeric,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS judgments_solution_idx ON {{app_schema}}.judgments (solution_id);
CREATE INDEX IF NOT EXISTS judgments_problem_idx ON {{app_schema}}.judgments (problem_id);
