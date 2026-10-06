import { useEffect, useRef, useState } from 'react'

type Props = {
  loading: boolean
  onSubmit: (question: string) => void
}

export default function QuestionForm({ loading, onSubmit }: Props) {
  const [question, setQuestion] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [preview, setPreview] = useState<string | null>(null)

  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!loading) return

    const started = Date.now()

    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000))
    }, 1000)

    return () => {
      clearInterval(timer)
      setElapsed(0)
    }
  }, [loading])

  const submit = () => {
    const q = question.trim()

    if (q && !loading) {
      onSubmit(q)
    }
  }

  const handleImage = (file?: File) => {
    if (!file) return

    if (preview) {
      URL.revokeObjectURL(preview)
    }

    setPreview(URL.createObjectURL(file))

    /*
      TODO:
      OCR API가 생기면 여기에서 이미지 파일을 백엔드로 보내고,
      반환받은 OCR 문자열을 setQuestion(ocrText) 하면 됨.

      현재 팀 api.ts에는 이미지 OCR 엔드포인트가 없으므로
      지금은 이미지 미리보기까지만 처리한다.
    */
  }

  return (
      <section className="question-area">
        <div className="section-heading">
          <div>
            <h1>문제 풀기</h1>
            <p>기출 문제 사진을 올리거나 문제를 직접 입력해주세요.</p>
          </div>
        </div>

        <div className="upload-card">
          {!preview ? (
              <button
                  type="button"
                  className="upload-empty"
                  onClick={() => fileRef.current?.click()}
              >
                <span className="upload-plus">＋</span>

                <strong>문제 이미지를 올려주세요</strong>

                <span>
              JPG, PNG 이미지 파일을 선택할 수 있어요.
            </span>

                <span className="fake-upload-button">
              사진 선택하기
            </span>
              </button>
          ) : (
              <div className="image-preview-wrap">
                <div className="card-header">
                  <strong>업로드한 문제</strong>

                  <button
                      type="button"
                      className="text-button"
                      onClick={() => {
                        URL.revokeObjectURL(preview)
                        setPreview(null)

                        if (fileRef.current) {
                          fileRef.current.value = ''
                        }
                      }}
                  >
                    이미지 삭제
                  </button>
                </div>

                <img
                    className="question-preview"
                    src={preview}
                    alt="업로드한 문제"
                />

                <button
                    type="button"
                    className="change-image-button"
                    onClick={() => fileRef.current?.click()}
                >
                  다른 이미지 선택
                </button>
              </div>
          )}

          <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(e) => handleImage(e.target.files?.[0])}
          />
        </div>

        <div className="question-text-card">
          <div className="card-header">
            <div>
              <strong>추출된 문제</strong>
              <span className="card-description">
              OCR 결과를 확인하고 잘못된 부분은 직접 수정할 수 있어요.
            </span>
            </div>
          </div>

          <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (
                    e.key === 'Enter' &&
                    (e.ctrlKey || e.metaKey)
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
              rows={10}
          />

          <div className="question-actions">
            {loading && (
                <span className="loading-text">
              교재에서 근거를 찾는 중… {elapsed}초
            </span>
            )}

            <button
                type="button"
                className="solve-button"
                onClick={submit}
                disabled={loading || !question.trim()}
            >
              {loading ? '분석 중…' : '문제 풀기'}
            </button>
          </div>
        </div>
      </section>
  )
}