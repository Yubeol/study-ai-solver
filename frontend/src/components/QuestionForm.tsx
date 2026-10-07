import {
  useEffect,
  useRef,
  useState,
} from 'react'

import { ApiError, ocr } from '../api'

type Props = {
  loading: boolean
  onSubmit: (question: string) => void
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
    ocrLoading,
    setOcrLoading,
  ] = useState(false)

  const [
    ocrError,
    setOcrError,
  ] = useState<string | null>(null)

  // OCR이 끝났을 때의 입력칸 값과 직전 OCR 결과(사용자가 입력·수정한 내용은 덮어쓰지 않기 위해)
  const questionRef =
      useRef('')

  const lastOcrText =
      useRef('')

  useEffect(() => {
    questionRef.current = question
  }, [question])

  const [
    elapsed,
    setElapsed,
  ] = useState(0)

  const [
    preview,
    setPreview,
  ] = useState<string | null>(null)

  const fileRef =
      useRef<HTMLInputElement>(null)

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
                  (Date.now() - started) /
                  1000,
              ),
          )
        }, 1000)

    return () => {
      clearInterval(timer)

      setElapsed(0)
    }
  }, [loading])

  const submit = () => {
    const q =
        question.trim()

    if (
        q &&
        !loading
    ) {
      onSubmit(q)
    }
  }

  const handleImage = async (
      file?: File,
  ) => {
    if (!file || ocrLoading) {
      return
    }

    if (preview) {
      URL.revokeObjectURL(
          preview,
      )
    }

    setPreview(
        URL.createObjectURL(
            file,
        ),
    )

    // 사진 → /ocr → "추출된 문제" 칸. 칸이 비었거나 직전 OCR 결과 그대로일 때만 채운다.
    setOcrError(null)
    setOcrLoading(true)

    try {
      const result = await ocr(file)
      const current = questionRef.current

      if (
          !current.trim() ||
          current === lastOcrText.current
      ) {
        setQuestion(result.text)
        lastOcrText.current = result.text
      } else {
        setOcrError('직접 입력한 문제가 있어 사진 결과로 바꾸지 않았어요. 칸을 비우고 다시 사진을 선택하면 채워져요.')
      }

      if (!result.text) {
        setOcrError('사진에서 글자를 찾지 못했어요. 문제를 직접 입력해주세요.')
      }
    } catch (e) {
      setOcrError(
          e instanceof ApiError
              ? e.message
              : '문제를 읽지 못했어요.',
      )
    } finally {
      setOcrLoading(false)
    }
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
                onClick={() =>
                    fileRef.current?.click()
                }
            >
              <div className="upload-symbol">
                +
              </div>

              <h2>
                문제 이미지를 올려주세요
              </h2>

              <p>
                JPG, PNG 이미지를
                선택할 수 있어요.
              </p>

              <button
                  type="button"
                  className="primary-button"
              >
                사진 선택하기
              </button>

              <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  hidden
                  disabled={ocrLoading}
                  onChange={(e) =>
                      handleImage(
                          e.target.files?.[0],
                      )
                  }
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
                    onClick={() => {
                      if (preview) {
                        URL.revokeObjectURL(
                            preview,
                        )
                      }

                      setPreview(null)

                      if (
                          fileRef.current
                      ) {
                        fileRef.current.value =
                            ''
                      }
                    }}
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
                  disabled={ocrLoading}
                  onClick={() =>
                      fileRef.current?.click()
                  }
              >
                다른 이미지 선택
              </button>

              <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  hidden
                  disabled={ocrLoading}
                  onChange={(e) =>
                      handleImage(
                          e.target.files?.[0],
                      )
                  }
              />
            </div>
        )}

        <div className="panel-card extracted-card">
          <div className="panel-title-row">
            <div>
              <h2>
                추출된 문제
              </h2>

              <p className="panel-description">
                잘못 인식된 부분은
                직접 수정할 수 있어요.
              </p>

              {ocrLoading && (
                  <span className="loading-text">
                    사진에서 문제를 읽는 중…
                  </span>
              )}
            </div>
          </div>

          {ocrError && (
              <div className="notice error">
                {ocrError}
              </div>
          )}

          <textarea
              className="question-textarea"
              value={question}
              onChange={(e) =>
                  setQuestion(
                      e.target.value,
                  )
              }
              onKeyDown={(e) => {
                if (
                    e.key === 'Enter' &&
                    (e.ctrlKey ||
                        e.metaKey)
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
            {loading && (
                <span className="loading-text">
              교재에서 근거를
              찾는 중… {elapsed}초
            </span>
            )}

            <button
                type="button"
                className="primary-button"
                onClick={submit}
                disabled={
                    loading ||
                    ocrLoading ||
                    !question.trim()
                }
            >
              {loading
                  ? '분석 중…'
                  : '문제 풀기'}
            </button>
          </div>
        </div>
      </section>
  )
}