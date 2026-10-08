-- 006: 보충 이론(supplements)을 등록 즉시 검색 후보로 쓰기 위한 임베딩 칸 (D-M-035).
-- {{app_schema}} = DB_APP_SCHEMA 로 실행기가 치환한다. 기존 칸은 바꾸지 않고 추가만 한다.
-- 텍스트 보충만 채운다(이미지·PDF는 NULL로 남아 검색 대상이 아니다).

SET LOCAL lock_timeout = '5s';

ALTER TABLE {{app_schema}}.supplements
    ADD COLUMN IF NOT EXISTS embedding_text  text,                    -- 제목 + 본문(임베딩 입력 그대로)
    ADD COLUMN IF NOT EXISTS embedding       public.vector(1024),     -- /qa와 같은 임베더·정규화
    ADD COLUMN IF NOT EXISTS embedding_model text;                    -- 계산한 모델(EMBEDDING_MODEL 값)

-- 검색 대상: rejected가 아니고 벡터가 있는 행(blocks_embedding_hnsw와 같은 방식).
CREATE INDEX IF NOT EXISTS supplements_embedding_hnsw
    ON {{app_schema}}.supplements USING hnsw (embedding public.vector_cosine_ops)
    WHERE status <> 'rejected' AND embedding IS NOT NULL;
