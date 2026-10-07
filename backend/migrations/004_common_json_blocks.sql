-- 004: 공통 JSON(데이터 담당 결과물) 적재용 테이블 (D-M-032).
-- {{schema}} = DB_SCHEMA(팀 규격), {{app_schema}} = DB_APP_SCHEMA 로 실행기가 치환한다.
-- 팀 규격 테이블은 변경하지 않는다(books·processing_runs를 FK로 참조만, ON DELETE SET NULL).
-- 기존 검색(v_searchable_theory)과 따로 두고, /qa 검색 대상 전환은 다음 PR에서 설정값으로 한다.

SET LOCAL lock_timeout = '5s';

-- 문서 단위: 공통 JSON 과목 1개 = 1행. 나중에 사용자 업로드 자료도 문서 1행씩 들어온다.
CREATE TABLE IF NOT EXISTS {{app_schema}}.documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_key    text NOT NULL UNIQUE,                 -- 예: 'adsp_common_json:subject1'
    corpus          text NOT NULL,                        -- 'common_json' (이후 'upload' 등)
    subject         text NOT NULL,                        -- books.subject와 같은 값(예: 'ADsP')
    subject_no      integer,                              -- 과목 번호(1, 2, …)
    title           text NOT NULL,                        -- 예: manifest subject_name
    source_format   text,                                 -- blocks 파일의 format
    format_version  text,                                 -- blocks 파일의 format_version(기록용, 분기에 쓰지 않음)
    book_id         uuid REFERENCES {{schema}}.books (id) ON DELETE SET NULL,  -- 같은 교재의 기존 book(비교용)
    manifest        jsonb NOT NULL DEFAULT '{}'::jsonb,
    pages           jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(pages) = 'array'),
    page_relations  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(page_relations) = 'array'),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_corpus_subject_idx ON {{app_schema}}.documents (corpus, subject_no);

-- 블록: 공통 JSON 블록 1개 = 1행 = 검색 단위 1개. block_id는 데이터 담당이 발급한 불변 ID.
CREATE TABLE IF NOT EXISTS {{app_schema}}.blocks (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id             uuid NOT NULL REFERENCES {{app_schema}}.documents (id) ON DELETE CASCADE,
    block_id                text NOT NULL UNIQUE,         -- 예: 'S2:TABLE:TAB_104_01'
    source_id               text NOT NULL,                -- 예: 'TAB_104_01'
    block_type              text NOT NULL CHECK (block_type IN ('theory', 'table', 'visual', 'formula', 'code')),
    block_role              text NOT NULL DEFAULT 'content' CHECK (block_role IN ('content', 'learning_objective')),
    printed_page_number     integer NOT NULL,
    order_in_page           integer,
    title                   text,
    title_path              jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(title_path) = 'array'),
    concept_name            text,
    raw_text                jsonb NOT NULL,               -- 교재 원문 그대로(이론은 문자열, 표·그림은 목록 등 원본 형태)
    clean_text              text,
    table_data              jsonb,                        -- headers, row_headers, rows, merged_cells, units
    visual_data             jsonb,                        -- visual_type, visual_description, visual_observation, visual_structure, …
    image                   jsonb,                        -- s3_bucket, s3_region, original_s3_key, thumbnail_s3_key, …
    crop_s3_key             text,
    thumbnail_s3_key        text,
    duplicate_of_block_id   text,                         -- 이 이론과 같은 내용의 표 block_id(적재 시 검증)
    model_generated         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- 저장만, 임베딩에는 쓰지 않음
    confidence              real,
    review                  jsonb NOT NULL DEFAULT '{}'::jsonb,
    needs_review            boolean NOT NULL DEFAULT false,
    source                  jsonb NOT NULL DEFAULT '{}'::jsonb,  -- 위 컬럼에 넣지 않은 나머지 원본 필드
    search_enabled          boolean NOT NULL DEFAULT true,
    search_excluded_reason  text,                         -- duplicate_of_table / learning_objective
    embedding_text          text,
    embedding_text_hash     text,
    embedding               public.vector(1024),
    embedding_model         text,
    content_hash            text NOT NULL,                -- 원본 블록 JSON의 sha256(변경 감지)
    processing_run_id       uuid REFERENCES {{schema}}.processing_runs (id) ON DELETE SET NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CHECK (search_enabled OR search_excluded_reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS blocks_document_page_idx
    ON {{app_schema}}.blocks (document_id, printed_page_number, order_in_page);
CREATE INDEX IF NOT EXISTS blocks_embedding_hnsw
    ON {{app_schema}}.blocks USING hnsw (embedding public.vector_cosine_ops)
    WHERE search_enabled AND embedding IS NOT NULL;

-- 블록 관계: relations 파일의 block_relations. 방향(from → to)과 relation_source를 그대로 보존한다.
CREATE TABLE IF NOT EXISTS {{app_schema}}.block_relations (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      uuid NOT NULL REFERENCES {{app_schema}}.documents (id) ON DELETE CASCADE,
    relationship_id  text NOT NULL,
    from_block_id    text NOT NULL REFERENCES {{app_schema}}.blocks (block_id) ON DELETE CASCADE,
    to_block_id      text NOT NULL REFERENCES {{app_schema}}.blocks (block_id) ON DELETE CASCADE,
    from_page        integer,
    to_page          integer,
    link_type        text NOT NULL,                       -- 예: THEORY_TO_TABLE
    relation_types   jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(relation_types) = 'array'),
    relation_source  text NOT NULL,
    relation_scope   text,
    confidence       real,
    reason           text,
    UNIQUE (from_block_id, to_block_id),
    UNIQUE (document_id, relationship_id)
);
CREATE INDEX IF NOT EXISTS block_relations_to_idx ON {{app_schema}}.block_relations (to_block_id);

-- 검색 대상 블록(다음 PR의 /qa 전환에서 사용)
CREATE OR REPLACE VIEW {{app_schema}}.v_searchable_blocks AS
SELECT *
FROM {{app_schema}}.blocks
WHERE search_enabled AND embedding IS NOT NULL AND NOT needs_review;
