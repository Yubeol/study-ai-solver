-- 001: 팀 규격 스키마(DB_SCHEMA) 보완 — 컬럼/인덱스/제약 "추가"만 한다.
-- 기존 컬럼의 이름·타입·제약은 건드리지 않는다. 기존 뷰(v_searchable_*)도 변경하지 않는다.
-- {{schema}} 는 실행기가 설정값 DB_SCHEMA 로 치환한다.
-- pg_trgm 확장은 public 스키마에 설치되어 있어 연산자 클래스를 public.gin_trgm_ops 로 명시한다.

SET LOCAL lock_timeout = '5s';

-- books: 과목 분리, 자료 유형(출처 표시용)
ALTER TABLE {{schema}}.books
    ADD COLUMN IF NOT EXISTS subject text,
    ADD COLUMN IF NOT EXISTS material_type text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'books_material_type_check'
          AND conrelid = '{{schema}}.books'::regclass
    ) THEN
        ALTER TABLE {{schema}}.books
            ADD CONSTRAINT books_material_type_check
            CHECK (material_type IN ('textbook', 'lecture_note', 'personal_note'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS books_subject_idx ON {{schema}}.books (subject);

-- theory_chunks: 페이지 내 순서(앞뒤 문맥 복원), 청크 단위 실행 추적
ALTER TABLE {{schema}}.theory_chunks
    ADD COLUMN IF NOT EXISTS sort_order integer,
    ADD COLUMN IF NOT EXISTS processing_run_id uuid
        REFERENCES {{schema}}.processing_runs (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS theory_chunks_page_sort_idx
    ON {{schema}}.theory_chunks (page_id, sort_order);
CREATE INDEX IF NOT EXISTS theory_chunks_run_idx
    ON {{schema}}.theory_chunks (processing_run_id);

-- visual_assets: 청크 단위 실행 추적
ALTER TABLE {{schema}}.visual_assets
    ADD COLUMN IF NOT EXISTS processing_run_id uuid
        REFERENCES {{schema}}.processing_runs (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS visual_assets_run_idx
    ON {{schema}}.visual_assets (processing_run_id);

-- 하이브리드 검색용 trgm 인덱스
CREATE INDEX IF NOT EXISTS visual_assets_embedding_text_trgm
    ON {{schema}}.visual_assets USING gin (embedding_text public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS concepts_canonical_name_trgm
    ON {{schema}}.concepts USING gin (canonical_name public.gin_trgm_ops);
