import { useState } from 'react'
import { ask, type QaResponse } from './api'
import AnswerView from './components/AnswerView'
import CitationList from './components/CitationList'
import DevInfo from './components/DevInfo'
import QuestionForm from './components/QuestionForm'
import SourceSelector from './components/SourceSelector'

// 최소 공부 화면: 질문 입력 → 답변과 근거 표시 (ARCHITECTURE "화면" B의 일부)
export default function App() {
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<QaResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (question: string) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await ask(question))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <SourceSelector value={source} onChange={setSource} />
      <QuestionForm loading={loading} onSubmit={onSubmit} />
      {error && <div className="notice error">{error}</div>}
      {result && (
        <>
          <AnswerView result={result} />
          <CitationList evidence={result.evidence} />
          <DevInfo result={result} />
        </>
      )}
    </main>
  )
}
