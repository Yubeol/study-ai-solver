import {
  useState,
} from 'react'

import {
  approveBlockCorrection,
  createBlockCorrection,
  getBlock,
  type BlockDetail,
  type Evidence,
  type RelatedVisual,
} from '../api'

type EvidenceImageProps = {
  title: string
  thumbnailUrl?: string | null
  imageUrl?: string | null
}

function EvidenceImage({
  title,
  thumbnailUrl,
  imageUrl,
}: EvidenceImageProps) {
  const [
    imageError,
    setImageError,
  ] = useState(false)

  const previewUrl =
    thumbnailUrl ||
    imageUrl

  const originalUrl =
    imageUrl ||
    thumbnailUrl

  if (!previewUrl) {
    return null
  }

  if (imageError) {
    return (
      <div className="evidence-image-error">
        이미지를 불러올 수 없어요.
      </div>
    )
  }

  const openOriginal =
    () => {
      if (!originalUrl) {
        return
      }

      window.open(
        originalUrl,
        '_blank',
        'noopener,noreferrer',
      )
    }

  return (
    <button
      type="button"
      className="evidence-image-button"
      onClick={
        openOriginal
      }
      aria-label={`${title} 원본 이미지 열기`}
    >
      <img
        src={previewUrl}
        alt={title}
        className="evidence-image"
        onError={() =>
          setImageError(
            true,
          )
        }
      />
    </button>
  )
}

function RelatedVisualCard({
  visual,
}: {
  visual: RelatedVisual
}) {
  const title =
    visual.title ||
    '관련 이미지'

  return (
    <div className="related-visual-card">
      <EvidenceImage
        title={title}
        thumbnailUrl={
          visual.thumbnail_url
        }
        imageUrl={
          visual.image_url
        }
      />

      <div className="related-visual-info">
        <span className="related-visual-kind">
          {visual.kind ===
          'table'
            ? '표'
            : '그림'}
        </span>

        <span className="related-visual-title">
          {title}
        </span>
      </div>
    </div>
  )
}

function EvidenceCard({
  e,
}: {
  e: Evidence
}) {
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
  ] =
    useState<BlockDetail | null>(
      null,
    )

  const [
    newCleanText,
    setNewCleanText,
  ] = useState('')

  const [
    correctionError,
    setCorrectionError,
  ] =
    useState<string | null>(
      null,
    )

  const [
    correctionSuccess,
    setCorrectionSuccess,
  ] =
    useState<string | null>(
      null,
    )

  const canEditTheory =
    e.kind === 'theory' &&
    Boolean(
      e.block_id,
    )

  const hasOwnImage =
    Boolean(
      e.thumbnail_url ||
      e.image_url,
    )

  const relatedVisuals =
    e.related_visuals ??
    []

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

        setCorrectionError(
          null,
        )

        return
      }

      setLoadingBlock(
        true,
      )

      setCorrectionError(
        null,
      )

      setCorrectionSuccess(
        null,
      )

      try {
        const currentBlock =
          await getBlock(
            e.block_id,
          )

        if (
          !currentBlock
        ) {
          setCorrectionError(
            '이론 정보를 불러오지 못했습니다.',
          )

          return
        }

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
          currentBlock.clean_text ??
            '',
        )

        setEditing(
          true,
        )
      } catch (error) {
        setCorrectionError(
          error instanceof
            Error
            ? error.message
            : '현재 이론 내용을 불러오지 못했습니다.',
        )
      } finally {
        setLoadingBlock(
          false,
        )
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

      setApplying(
        true,
      )

      setCorrectionError(
        null,
      )

      setCorrectionSuccess(
        null,
      )

      try {
        const correction =
          await createBlockCorrection(
            {
              block_id:
                block.block_id,

              new_clean_text:
                nextText,
            },
          )

        if (
          !correction ||
          !correction.id
        ) {
          setCorrectionError(
            '수정안 등록 결과를 확인할 수 없습니다.',
          )

          return
        }

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
          error instanceof
            Error
            ? error.message
            : '이론 수정에 실패했습니다.',
        )
      } finally {
        setApplying(
          false,
        )
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

            {e.book_title}

            {' · '}

            {e.page ?? '?'}

            쪽

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

      {hasOwnImage && (
        <div className="evidence-visual-section">
          <div className="evidence-visual-label">
            근거 이미지
          </div>

          <EvidenceImage
            title={
              e.path ||
              e.book_title ||
              '근거 이미지'
            }
            thumbnailUrl={
              e.thumbnail_url
            }
            imageUrl={
              e.image_url
            }
          />
        </div>
      )}

      {relatedVisuals.length >
        0 && (
        <div className="related-visuals-section">
          <div className="evidence-visual-label">
            관련 그림·표
          </div>

          <div className="related-visuals-list">
            {relatedVisuals.map(
              (visual) => (
                <RelatedVisualCard
                  key={
                    visual.block_id
                  }
                  visual={
                    visual
                  }
                />
              ),
            )}
          </div>
        </div>
      )}

      {correctionError && (
        <div className="theory-correction-message error">
          {
            correctionError
          }
        </div>
      )}

      {correctionSuccess && (
        <div className="theory-correction-message success">
          {
            correctionSuccess
          }
        </div>
      )}

      {editing &&
        block && (
          <section className="theory-correction">
            <div className="theory-correction-heading">
              <div>
                <strong>
                  이론 수정
                </strong>

                <p>
                  현재 정제된 이론
                  내용을 수정할 수
                  있습니다.
                </p>
              </div>
            </div>

            {(block.title ||
              block.title_path) && (
              <div className="theory-block-info">
                {block.title && (
                  <strong>
                    {
                      block.title
                    }
                  </strong>
                )}

                {block.title_path && (
                  <span>
                    {
                      block.title_path
                    }
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
                maxLength={
                  2000
                }
                disabled={
                  applying
                }
                onChange={(
                  event,
                ) => {
                  setNewCleanText(
                    event
                      .target
                      .value,
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
                {
                  newCleanText.length
                }
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
                  setEditing(
                    false,
                  )

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
    evidence.length ===
    0
  ) {
    return null
  }

  return (
    <section className="citations">
      <h2>
        근거 (교재 원문)
      </h2>

      {cited.length ===
        0 && (
        <p className="hint">
          답변이 인용한
          근거가 없습니다.
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

      {others.length >
        0 && (
        <details>
          <summary>
            인용되지 않은 근거{' '}
            {
              others.length
            }
            개
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