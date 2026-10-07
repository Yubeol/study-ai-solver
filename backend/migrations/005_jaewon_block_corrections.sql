-- 005: 오류 신고 처리 기록과 이론 블록 수정안 (D-JW-007).
-- {{schema}} = DB_SCHEMA(팀 규격), {{app_schema}} = DB_APP_SCHEMA 로 실행기가 치환한다.
-- 팀 규격 테이블은 바꾸지 않는다. 바꾸는 것은 mingyu_app의 blocks(칸 1개 추가)·answer_reports(칸 4개 추가)와 새 테이블 block_corrections.

SET LOCAL lock_timeout = '5s';

-- 1) blocks: JSON 원문 clean_text의 해시. 수정안이 어떤 원문을 기준으로 만들어졌는지 남겨, 원문이 바뀌면 낡은 수정을 잡는다.
--    정규화(기준은 app/core/text_hash.py의 clean_text_hash): CRLF·CR → LF → 앞뒤 스페이스·탭·LF 제거 → UTF-8 sha256 hex.
--    지금은 적용된 수정이 없어 DB clean_text = JSON 원문이므로 바로 채운다. clean_text가 NULL(표·시각자료)이면 NULL.
ALTER TABLE {{app_schema}}.blocks ADD COLUMN IF NOT EXISTS source_clean_text_hash text;
UPDATE {{app_schema}}.blocks
SET source_clean_text_hash = encode(sha256(convert_to(
        btrim(replace(replace(clean_text, E'\r\n', E'\n'), E'\r', E'\n'), E' \t\n'), 'UTF8')), 'hex')
WHERE clean_text IS NOT NULL AND source_clean_text_hash IS NULL;

-- 2) answer_reports: 처리 결과. status(open/resolved)는 그대로 두고, resolved면 resolution 필수.
ALTER TABLE {{app_schema}}.answer_reports
    ADD COLUMN IF NOT EXISTS resolution text
        CHECK (resolution IN ('block_corrected', 'supplement_added', 'source_fix_requested', 'prompt_issue',
                              'retrieval_issue', 'not_an_error', 'duplicate', 'other')),
    ADD COLUMN IF NOT EXISTS resolution_note text NOT NULL DEFAULT '' CHECK (char_length(resolution_note) <= 500),
    -- team_text 근거로 들어온 신고를 검토자가 대응 block_id에 연결
    ADD COLUMN IF NOT EXISTS linked_block_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(linked_block_ids) = 'array'),
    ADD COLUMN IF NOT EXISTS reviewed_by text CHECK (char_length(reviewed_by) <= 100);
ALTER TABLE {{app_schema}}.answer_reports DROP CONSTRAINT IF EXISTS answer_reports_resolution_required;
ALTER TABLE {{app_schema}}.answer_reports
    ADD CONSTRAINT answer_reports_resolution_required CHECK (status <> 'resolved' OR resolution IS NOT NULL);

-- 3) block_corrections: 이론 블록 clean_text 수정안. block_id는 재적재해도 안 바뀌는 ID라 FK 없이 둔다(블록이 빠져도 적재를 막지 않게).
--    상태: proposed → applied(승인 시 API가 clean_text 수정 + 재임베딩) / rejected / withdrawn.
--          applied → 같은 블록의 새 수정 적용 시 superseded.
--          approved·stale은 적재 코드가 수정을 다시 적용하는 단계(후속)에서 쓴다.
CREATE TABLE IF NOT EXISTS {{app_schema}}.block_corrections (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id              text NOT NULL,                     -- 예: 'S1:THEORY:TH_62_02' (이론 블록만, API에서 검사)
    report_id             uuid REFERENCES {{app_schema}}.answer_reports (id) ON DELETE SET NULL,
    base_clean_text       text NOT NULL,                     -- 작성 당시 DB clean_text(비교 화면용)
    base_clean_text_hash  text NOT NULL,                     -- 작성 당시 blocks.source_clean_text_hash 복사(DB clean_text 해시 아님)
    new_clean_text        text NOT NULL
                          CHECK (char_length(new_clean_text) BETWEEN 1 AND 2000 AND btrim(new_clean_text) <> ''),
    reason                text NOT NULL DEFAULT '' CHECK (char_length(reason) <= 500),
    status                text NOT NULL DEFAULT 'proposed'
                          CHECK (status IN ('proposed', 'approved', 'applied', 'rejected', 'withdrawn', 'stale', 'superseded')),
    review_note           text NOT NULL DEFAULT '' CHECK (char_length(review_note) <= 500),
    reviewed_by           text CHECK (char_length(reviewed_by) <= 100),
    applied_note          text,                              -- 적용 결과(재임베딩 모델, stale 사유 등)
    created_at            timestamptz NOT NULL DEFAULT now(),
    reviewed_at           timestamptz,
    applied_at            timestamptz,
    CHECK (status <> 'applied' OR applied_at IS NOT NULL)  -- applied면 적용 시각 필수
);
CREATE INDEX IF NOT EXISTS block_corrections_block_status_idx ON {{app_schema}}.block_corrections (block_id, status);
CREATE INDEX IF NOT EXISTS block_corrections_report_idx ON {{app_schema}}.block_corrections (report_id);
-- 한 블록에 "현재 적용 대상" 수정은 1개만
CREATE UNIQUE INDEX IF NOT EXISTS block_corrections_one_active_idx
    ON {{app_schema}}.block_corrections (block_id) WHERE status IN ('approved', 'applied');
