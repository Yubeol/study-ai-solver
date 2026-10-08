import {
  useState,
} from 'react'

import {
  approveBlockCorrection,
  createBlockCorrection,
  getBlock,
  type BlockDetail,
  type Evidence,
} from '../api'

type EvidenceCardProps = {
  e: Evidence
}

function EvidenceCard({
  e,
}: EvidenceCardProps) {
  const [
    editing,
    setEditing,
  ] = useState(false)

  const [
    loadingBlock,
    setLoadingBlock,
  ] = useState(false)

  const [
    applying,
    setApplying,
  ] = useState(false)

  const [
    block,
    setBlock,
  ] = useState<BlockDetail | null>(null)

  const [
    newCleanText,
    setNewCleanText,
  ] = useState('')

  const [
    correctionError,
    setCorrectionError,
  ] = useState<string | null>(null)

  const [
    correctionSuccess,
    setCorrectionSuccess,
  ] = useState<string | null>(null)

  const canEditTheory =
    e.kind === 'theory' &&
    Boolean(e.block_id)

  const openEditor =
    async () => {
      if (
        !e.block_id ||
        loadingBlock ||
        applying
      ) {
        return
      }

      if (editing) {
        setEditing(false)
        setCorrectionError(null)

        return
      }

      setLoadingBlock(true)
      setCorrectionError(null)
      setCorrectionSuccess(null)

      try {
        const currentBlock =
          await getBlock(
            e.block_id,
          )

        if (
          currentBlock.kind !==
          'theory'
        ) {
          setCorrectionError(
            '이론 블록만 수정할 수 있습니다.',
          )

          return
        }

        setBlock(
          currentBlock,
        )

        setNewCleanText(
          currentBlock.clean_text,
        )

        setEditing(true)
      } catch (error) {
        setCorrectionError(
          error instanceof Error
            ? error.message
            : '현재 이론 내용을 불러오지 못했습니다.',
        )
      } finally {
        setLoadingBlock(false)
      }
    }

  const applyCorrection =
    async () => {
      if (
        !block ||
        applying
      ) {
        return
      }

      const nextText =
        newCleanText.trim()

      if (!nextText) {
        setCorrectionError(
          '수정할 내용을 입력해주세요.',
        )

        return
      }

      if (
        nextText ===
        block.clean_text.trim()
      ) {
        setCorrectionError(
          '현재 내용과 수정안이 같습니다.',
        )

        return
      }

      setApplying(true)
      setCorrectionError(null)
      setCorrectionSuccess(null)

      try {
        /*
         * 1. 수정안 등록
         *
         * 이번 화면은 신고 없이 독립적으로 사용하므로
         * report_id는 보내지 않는다.
         */
        const correction =
          await createBlockCorrection({
            block_id:
              block.block_id,

            new_clean_text:
              nextText,
          })

        /*
         * 2. 방금 생성된 수정안을
         * 바로 승인해서 실제 교재에 적용한다.
         *
         * 승인 body의 모든 필드는 선택값이므로
         * 최소 형태인 {}로 호출한다.
         */
        await approveBlockCorrection(
          correction.id,
        )

        setBlock({
          ...block,
          clean_text:
            nextText,
        })

        setNewCleanText(
          nextText,
        )

        setCorrectionSuccess(
          '수정이 적용되었습니다. 다음 질문부터 반영돼요.',
        )
      } catch (error) {
        setCorrectionError(
          error instanceof Error
            ? error.message
            : '이론 수정에 실패했습니다.',
        )
      } finally {
        setApplying(false)
      }
    }

  return (
    <article
      className="evidence"
      id={`ev-${e.n}`}
    >
      <header>
        <div className="evidence-header-main">
          <div>
            <span className="ev-n">
              [{e.n}]
            </span>{' '}
            {e.book_title} ·{' '}
            {e.page ?? '?'}쪽

            {e.path && (
              <div className="ev-path">
                {e.path}
              </div>
            )}
          </div>

          {canEditTheory && (
            <button
              type="button"
              className="theory-edit-button"
              disabled={
                loadingBlock ||
                applying
              }
              onClick={
                openEditor
              }
            >
              {loadingBlock
                ? '불러오는 중...'
                : editing
                  ? '수정 닫기'
                  : '이론 수정'}
            </button>
          )}
        </div>
      </header>

      <pre className="raw-text">
        {e.raw_text}
      </pre>

      {correctionError && (
        <div className="theory-correction-message error">
          {correctionError}
        </div>
      )}

      {correctionSuccess && (
        <div className="theory-correction-message success">
          {correctionSuccess}
        </div>
      )}

      {editing && block && (
        <section className="theory-correction">
          <div className="theory-correction-heading">
            <div>
              <strong>
                이론 수정
              </strong>

              <p>
                현재 정제된 이론 내용을
                수정할 수 있습니다.
              </p>
            </div>
          </div>

          {(block.title ||
            block.title_path) && (
            <div className="theory-block-info">
              {block.title && (
                <strong>
                  {block.title}
                </strong>
              )}

              {block.title_path && (
                <span>
                  {block.title_path}
                </span>
              )}
            </div>
          )}

          <label className="theory-correction-input">
            <span>
              수정할 내용
            </span>

            <textarea
              value={
                newCleanText
              }
              maxLength={2000}
              disabled={
                applying
              }
              onChange={(event) => {
                setNewCleanText(
                  event.target.value,
                )

                setCorrectionError(
                  null,
                )

                setCorrectionSuccess(
                  null,
                )
              }}
            />

            <small>
              {newCleanText.length}
              /2000
            </small>
          </label>

          <div className="theory-correction-actions">
            <button
              type="button"
              className="cancel-button"
              disabled={
                applying
              }
              onClick={() => {
                setEditing(false)
                setCorrectionError(
                  null,
                )
              }}
            >
              취소
            </button>

            <button
              type="button"
              className="primary-button"
              disabled={
                applying ||
                !newCleanText.trim() ||
                newCleanText.trim() ===
                  block.clean_text.trim()
              }
              onClick={
                applyCorrection
              }
            >
              {applying
                ? '수정 적용 중...'
                : '수정 적용'}
            </button>
          </div>
        </section>
      )}
    </article>
  )
}

// 인용된 근거는 펼쳐 보여 주고,
// 인용되지 않은 근거는 접어 둔다.
// raw_text는 교재 원문 그대로다.
export default function CitationList({
  evidence,
}: {
  evidence: Evidence[]
}) {
  const cited =
    evidence.filter(
      (e) => e.cited,
    )

  const others =
    evidence.filter(
      (e) => !e.cited,
    )

  if (
    evidence.length === 0
  ) {
    return null
  }

  return (
    <section className="citations">
      <h2>
        근거 (교재 원문)
      </h2>

      {cited.length === 0 && (
        <p className="hint">
          답변이 인용한 근거가 없습니다.
        </p>
      )}

      {cited.map(
        (e) => (
          <EvidenceCard
            key={e.n}
            e={e}
          />
        ),
      )}

      {others.length > 0 && (
        <details>
          <summary>
            인용되지 않은 근거{' '}
            {others.length}개
          </summary>

          {others.map(
            (e) => (
              <EvidenceCard
                key={e.n}
                e={e}
              />
            ),
          )}
        </details>
      )}
    </section>
  )
}