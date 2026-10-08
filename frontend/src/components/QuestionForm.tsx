import {
  useEffect,
  useRef,
  useState,
} from 'react'

import {
  ocr,
} from '../api'

type Props = {
  loading: boolean

  onSubmit: (
    question: string,
  ) => void
}

export default function QuestionForm({
  loading,
  onSubmit,
}: Props) {
  const [
    question,
    setQuestion,
  ] = useState('')

  const [
    elapsed,
    setElapsed,
  ] = useState(0)

  const [
    preview,
    setPreview,
  ] =
    useState<string | null>(
      null,
    )

  const [
    ocrLoading,
    setOcrLoading,
  ] = useState(false)

  const [
    ocrError,
    setOcrError,
  ] =
    useState<string | null>(
      null,
    )

  const lastOcrTextRef =
    useRef('')

  const fileRef =
    useRef<HTMLInputElement>(
      null,
    )

  useEffect(() => {
    if (!loading) {
      return
    }

    const started =
      Date.now()

    const timer =
      setInterval(() => {
        setElapsed(
          Math.floor(
            (
              Date.now() -
              started
            ) / 1000,
          ),
        )
      }, 1000)

    return () => {
      clearInterval(
        timer,
      )

      setElapsed(0)
    }
  }, [loading])

  const submit = () => {
    const q =
      question.trim()

    if (
      q &&
      !loading &&
      !ocrLoading
    ) {
      onSubmit(q)
    }
  }

  const getOcrText = (
    result: Awaited<
      ReturnType<typeof ocr>
    >,
  ) => {
    if (
      result.text?.trim()
    ) {
      return result.text.trim()
    }

    const parts: string[] =
      []

    if (
      result.problem_text?.trim()
    ) {
      parts.push(
        result.problem_text.trim(),
      )
    }

    if (
      result.choices?.length
    ) {
      parts.push(
        result.choices
          .filter(
            (choice) =>
              choice?.trim(),
          )
          .join('\n'),
      )
    }

    return parts
      .filter(Boolean)
      .join('\n\n')
      .trim()
  }

  const handleImage =
    async (
      file?: File,
    ) => {
      if (
        !file ||
        ocrLoading
      ) {
        return
      }

      if (preview) {
        URL.revokeObjectURL(
          preview,
        )
      }

      const nextPreview =
        URL.createObjectURL(
          file,
        )

      setPreview(
        nextPreview,
      )

      setOcrLoading(
        true,
      )

      setOcrError(
        null,
      )

      try {
        const result =
          await ocr(file)

        const nextOcrText =
          getOcrText(
            result,
          )

        if (
          !nextOcrText
        ) {
          throw new Error(
            '이미지에서 문제를 인식하지 못했습니다.',
          )
        }

        setQuestion(
          (
            currentQuestion,
          ) => {
            const current =
              currentQuestion.trim()

            const previousOcr =
              lastOcrTextRef.current.trim()

            if (
              !current ||
              current ===
                previousOcr
            ) {
              lastOcrTextRef.current =
                nextOcrText

              return nextOcrText
            }

            return currentQuestion
          },
        )
      } catch (error) {
        setOcrError(
          error instanceof Error
            ? error.message
            : '문제 이미지 인식에 실패했습니다.',
        )
      } finally {
        setOcrLoading(
          false,
        )
      }
    }

  const removeImage =
    () => {
      if (
        ocrLoading
      ) {
        return
      }

      if (preview) {
        URL.revokeObjectURL(
          preview,
        )
      }

      setPreview(null)

      setOcrError(null)

      if (
        fileRef.current
      ) {
        fileRef.current.value =
          ''
      }
    }

  const openFilePicker =
    () => {
      if (
        ocrLoading
      ) {
        return
      }

      fileRef.current?.click()
    }

  return (
    <section className="question-column">
      <div className="page-heading">
        <h1>
          문제 풀기
        </h1>

        <p>
          문제 사진을 올리거나
          직접 입력해주세요.
        </p>
      </div>

      {!preview ? (
        <div
          className="upload-box"
          onClick={
            openFilePicker
          }
        >
          <div className="upload-symbol">
            +
          </div>

          <h2>
            문제 이미지를
            올려주세요
          </h2>

          <p>
            JPG, PNG 이미지를
            선택할 수 있어요.
          </p>

          <button
            type="button"
            className="primary-button"
            disabled={
              ocrLoading
            }
            onClick={(
              event,
            ) => {
              event.stopPropagation()

              openFilePicker()
            }}
          >
            {ocrLoading
              ? '문제 인식 중...'
              : '사진 선택하기'}
          </button>

          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            disabled={
              ocrLoading
            }
            onChange={(
              event,
            ) => {
              void handleImage(
                event.target
                  .files?.[0],
              )
            }}
          />
        </div>
      ) : (
        <div className="panel-card">
          <div className="panel-title-row">
            <h2>
              업로드한 이미지
            </h2>

            <button
              type="button"
              className="text-button danger"
              disabled={
                ocrLoading
              }
              onClick={
                removeImage
              }
            >
              삭제
            </button>
          </div>

          <img
            src={preview}
            alt="업로드한 문제"
            className="question-image"
          />

          <button
            type="button"
            className="secondary-button full-button"
            disabled={
              ocrLoading
            }
            onClick={
              openFilePicker
            }
          >
            {ocrLoading
              ? '문제 인식 중...'
              : '다른 이미지 선택'}
          </button>

          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            disabled={
              ocrLoading
            }
            onChange={(
              event,
            ) => {
              void handleImage(
                event.target
                  .files?.[0],
              )
            }}
          />

          {ocrLoading && (
            <div className="notice muted">
              이미지에서 문제를
              인식하고 있습니다.
              잠시 기다려주세요.
            </div>
          )}

          {ocrError && (
            <div className="notice error">
              {ocrError}
            </div>
          )}
        </div>
      )}

      <div className="panel-card extracted-card">
        <div className="panel-title-row">
          <div>
            <h2>
              추출된 문제
            </h2>

            <p className="panel-description">
              {ocrLoading
                ? 'OCR이 끝나면 내용을 수정할 수 있어요.'
                : '잘못 인식된 부분은 직접 수정할 수 있어요.'}
            </p>
          </div>
        </div>

        <textarea
          className="question-textarea"
          value={question}
          disabled={
            ocrLoading
          }
          onChange={(
            event,
          ) =>
            setQuestion(
              event.target.value,
            )
          }
          onKeyDown={(
            event,
          ) => {
            if (
              event.key ===
                'Enter' &&
              (
                event.ctrlKey ||
                event.metaKey
              )
            ) {
              submit()
            }
          }}
          placeholder={`문제를 입력해주세요.

예)
다음 중 데이터 마이닝의 특징으로 옳지 않은 것은?

① ...
② ...
③ ...
④ ...`}
        />

        <div className="question-actions">
          {ocrLoading && (
            <span className="loading-text">
              이미지에서 문제를
              인식하는 중…
            </span>
          )}

          {!ocrLoading &&
            loading && (
              <span className="loading-text">
                교재에서 근거를
                찾는 중…{' '}
                {elapsed}초
              </span>
            )}

          <button
            type="button"
            className="primary-button"
            onClick={
              submit
            }
            disabled={
              loading ||
              ocrLoading ||
              !question.trim()
            }
          >
            {ocrLoading
              ? '문제 인식 중…'
              : loading
                ? '분석 중…'
                : '문제 풀기'}
          </button>
        </div>
      </div>
    </section>
  )
}