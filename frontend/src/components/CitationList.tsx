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
  thumbnailUrl:
    | string
    | null
    | undefined

  imageUrl:
    | string
    | null
    | undefined

  alt: string
}

function EvidenceImage({
  thumbnailUrl,
  imageUrl,
  alt,
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
        이미지를 불러올 수
        없어요.
      </div>
    )
  }

  return (
    <button
      type="button"
      className="evidence-image-button"
      onClick={() => {
        if (
          originalUrl
        ) {
          window.open(
            originalUrl,
            '_blank',
            'noopener,noreferrer',
          )
        }
      }}
    >
      <img
        src={previewUrl}
        alt={alt}
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
  const label =
    visual.kind ===
    'table'
      ? '표'
      : '그림'

  return (
    <div className="related-visual-card">
      <EvidenceImage
        thumbnailUrl={
          visual.thumbnail_url
        }
        imageUrl={
          visual.image_url
        }
        alt={
          visual.title ||
          '관련 이미지'
        }
      />

      <div className="related-visual-info">
        <span className="related-visual-kind">
          {label}
        </span>

        <span className="related-visual-title">
          {visual.title ||
            '관련 이미지'}
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
        const detail =
          await getBlock(
            e.block_id,
          )

        if (!detail) {
          throw new Error(
            '이론 정보를 불러오지 못했습니다.',
          )
        }

        if (
          detail.kind !==
          'theory'
        ) {
          throw new Error(
            '이론 블록만 수정할 수 있습니다.',
          )
        }

        setBlock(
          detail,
        )

        setNewCleanText(
          detail.clean_text,
        )

        setEditing(
          true,
        )
      } catch (error) {
        setCorrectionError(
          error instanceof
            Error
            ? error.message
            : '이론 정보를 불러오지 못했습니다.',
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
          '수정할 이론 내용을 입력해주세요.',
        )

        return
      }

      if (
        nextText ===
        block.clean_text.trim()
      ) {
        setCorrectionError(
          '수정된 내용이 없습니다.',
        )

        return
      }

      setApplying(true)

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
          throw new Error(
            '수정안을 등록하지 못했습니다.',
          )
        }

        await approveBlockCorrection(
          String(
            correction.id,
          ),
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

        setEditing(false)
      } catch (error) {
        setCorrectionError(
          error instanceof
            Error
            ? error.message
            : '이론 수정 중 오류가 발생했습니다.',
        )
      } finally {
        setApplying(
          false,
        )
      }
    }

  const sourceLabel =
    e.kind ===
    'supplement'
      ? '사용자 보충'
      : e.book_title

  const pageLabel =
    e.kind !==
      'supplement' &&
    e.page !== null &&
    e.page !==
      undefined &&
    String(e.page)
      .trim() !== ''
      ? ` · ${e.page}쪽`
      : ''

  return (
    <article
      className="evidence"
      id={`ev-${e.n}`}
    >
      <header>
        <span className="ev-n">
          [{e.n}]
        </span>{' '}
        {sourceLabel}
        {pageLabel}

        {e.kind !==
          'supplement' &&
          e.path && (
            <div className="ev-path">
              {e.path}
            </div>
          )}
      </header>

      <pre className="raw-text">
        {e.raw_text}
      </pre>

      {hasOwnImage && (
        <section className="evidence-visual-section">
          <div className="evidence-visual-label">
            근거 이미지
          </div>

          <EvidenceImage
            thumbnailUrl={
              e.thumbnail_url
            }
            imageUrl={
              e.image_url
            }
            alt="근거 이미지"
          />
        </section>
      )}

      {relatedVisuals.length >
        0 && (
        <section className="related-visuals-section">
          <div className="evidence-visual-label">
            관련 그림·표
          </div>

          <div className="related-visuals-list">
            {relatedVisuals.map(
              (
                visual,
                index,
              ) => (
                <RelatedVisualCard
                  key={
                    visual.block_id ||
                    index
                  }
                  visual={
                    visual
                  }
                />
              ),
            )}
          </div>
        </section>
      )}

      {canEditTheory && (
        <div className="theory-correction-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={
              loadingBlock ||
              applying
            }
            onClick={() => {
              void openEditor()
            }}
          >
            {loadingBlock
              ? '불러오는 중…'
              : editing
                ? '수정 닫기'
                : '이론 수정'}
          </button>
        </div>
      )}

      {editing &&
        block && (
          <div className="theory-correction-editor">
            <label>
              <span>
                이론 내용
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
                ) =>
                  setNewCleanText(
                    event
                      .target
                      .value,
                  )
                }
              />
            </label>

            <div className="theory-correction-footer">
              <small>
                {
                  newCleanText.length
                }
                /2000
              </small>

              <button
                type="button"
                className="primary-button"
                disabled={
                  applying
                }
                onClick={() => {
                  void applyCorrection()
                }}
              >
                {applying
                  ? '적용 중…'
                  : '수정 적용'}
              </button>
            </div>
          </div>
        )}

      {correctionError && (
        <div className="notice error">
          {correctionError}
        </div>
      )}

      {correctionSuccess && (
        <div className="notice success">
          {
            correctionSuccess
          }
        </div>
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
    evidence.length === 0
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