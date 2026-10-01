import { useEffect, useState } from 'react'

type Props = {
  loading: boolean
  onSubmit: (question: string) => void
}

export default function QuestionForm({ loading, onSubmit }: Props) {
  const [question, setQuestion] = useState('')
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!loading) return
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => {
      clearInterval(timer)
      setElapsed(0)
    }
  }, [loading])

  const submit = () => {
    const q = question.trim()
    if (q && !loading) onSubmit(q)
  }

  return (
    <div className="question-form">
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit()
        }}
        placeholder="질문 또는 객관식 문제(보기 ①~④ 포함)를 입력하세요. Ctrl+Enter로 질문"
        rows={6}
      />
      <div className="form-row">
        <button onClick={submit} disabled={loading || !question.trim()}>
          {loading ? '처리 중…' : '질문'}
        </button>
        {loading && <span className="hint">검색 중… {elapsed}초 (보통 6~15초)</span>}
      </div>
    </div>
  )
}
