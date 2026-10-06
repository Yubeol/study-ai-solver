import { useState } from 'react'

import type { QaResponse } from './api'

import AnswerView from './components/AnswerView'
import CitationList from './components/CitationList'
import DevInfo from './components/DevInfo'
import KnowledgeDrawer from './components/KnowledgeDrawer'
import QuestionForm from './components/QuestionForm'
import ReportDrawer from './components/ReportDrawer'
import Sidebar, { type Menu } from './components/Sidebar'

/*
  프론트 디자인 확인용 임시 데이터입니다.
  백엔드 연결이 완료되면 이 mockResult를 삭제하고
  실제 /qa 응답을 사용하면 됩니다.
*/
const mockResult: QaResponse = {
  question: '다음 중 데이터 마이닝의 특징으로 옳지 않은 것은?',

  status: 'answered',
  confidence: 'high',

  zone: 'answer',
  zone_reason: 'frontend_mock',

  scores: {
    vector_top: 0.92,
    rerank_top: 0.95,
  },

  judge: null,

  answer: '③',

  explanation: `데이터 마이닝은 대규모 데이터에서 의미 있는 패턴이나 관계를 찾아내는 과정입니다.

①은 데이터 마이닝의 특징에 해당합니다.
②는 다양한 분석 기법을 활용한다는 설명으로 옳습니다.
③은 데이터 마이닝의 특징과 맞지 않습니다.
④는 데이터에서 유용한 정보를 발견한다는 점에서 옳습니다.`,

  confusions:
      '데이터 마이닝은 단순히 데이터를 저장하거나 조회하는 과정과는 구분됩니다.',

  low_confidence: false,
  low_confidence_reasons: [],

  mcq_check: {
    is_mcq: true,
    negative: true,
    chosen: 3,

    option_verdicts: {
      '1': '옳음',
      '2': '옳음',
      '3': '틀림 · 정답',
      '4': '옳음',
    },

    consistent: true,
    reasons: [],
  },

  evidence: [
    {
      n: 1,
      chunk_id: 'mock-001',
      book_title: 'ADsP 데이터 분석 준전문가',
      page: 42,
      path: '1과목 > 데이터의 이해 > 데이터 분석',

      raw_text:
          '데이터 마이닝은 대용량 데이터로부터 의미 있는 패턴과 규칙을 찾아내는 과정이다.',

      vector_score: 0.92,
      rerank_score: 0.95,

      cited: true,
    },
  ],

  citations: [],

  timings_ms: {
    search_ms: 120,
    rerank_ms: 80,
    llm_ms: 600,
  },

  query_log_id: null,
}

export default function App() {
  const [loading, setLoading] = useState(false)

  const [result, setResult] =
      useState<QaResponse | null>(null)

  const [error, setError] =
      useState<string | null>(null)

  const [currentMenu, setCurrentMenu] =
      useState<Menu>('home')

  const [reportOpen, setReportOpen] =
      useState(false)

  const [knowledgeOpen, setKnowledgeOpen] =
      useState(false)

  const [lastQuestion, setLastQuestion] =
      useState('')

  /*
    지금은 백엔드를 호출하지 않습니다.

    문제 풀기 버튼을 누르면
    위에서 만든 mockResult를 보여줍니다.
  */
  const onSubmit = (question: string) => {
    setLoading(true)
    setError(null)
    setLastQuestion(question)

    setTimeout(() => {
      setResult({
        ...mockResult,
        question,
      })

      setLoading(false)
    }, 700)
  }

  return (
      <div className="app-shell">
        <Sidebar
            current={currentMenu}
            onChange={setCurrentMenu}
        />

        <main className="app-main">
          {currentMenu === 'home' && (
              <div className="study-grid has-result">
                <QuestionForm
                    loading={loading}
                    onSubmit={onSubmit}
                />

                <section className="result-column">
                  {!result && !error && !loading && (
                      <div className="empty-result-card">
                        <h2>정답 및 해설</h2>

                        <p>
                          문제를 입력하면 정답과 해설이
                          여기에 표시됩니다.
                        </p>
                      </div>
                  )}

                  {loading && (
                      <div className="empty-result-card">
                        <h2>문제를 분석하고 있어요</h2>

                        <p>
                          교재에서 관련 개념과 근거를 찾고 있습니다.
                        </p>
                      </div>
                  )}

                  {error && (
                      <div className="notice error">
                        {error}
                      </div>
                  )}

                  {result && (
                      <>
                        <AnswerView
                            result={result}
                            onReportOpen={() =>
                                setReportOpen(true)
                            }
                            onKnowledgeOpen={() =>
                                setKnowledgeOpen(true)
                            }
                        />

                        <CitationList
                            evidence={result.evidence}
                        />

                        <details className="developer-details">
                          <summary>
                            개발 정보 보기
                          </summary>

                          <DevInfo result={result} />
                        </details>
                      </>
                  )}
                </section>
              </div>
          )}

          {currentMenu === 'favorites' && (
              <section className="placeholder-page">
                <h1>즐겨찾기</h1>

                <p>
                  저장한 문제를 모아보는 기능은 추후
                  연결할 예정입니다.
                </p>
              </section>
          )}

          {currentMenu === 'knowledge' && (
              <section className="placeholder-page">
                <div className="placeholder-header">
                  <div>
                    <h1>자료 관리</h1>

                    <p>
                      추가된 이론, 이미지, PDF 자료를
                      관리합니다.
                    </p>
                  </div>

                  <button
                      type="button"
                      className="primary-button"
                      onClick={() =>
                          setKnowledgeOpen(true)
                      }
                  >
                    자료 추가
                  </button>
                </div>

                <div className="empty-state">
                  자료 관리 API가 연결되면 등록된 자료가
                  이곳에 표시됩니다.
                </div>
              </section>
          )}

          {currentMenu === 'settings' && (
              <section className="placeholder-page">
                <h1>설정</h1>

                <p>
                  설정 기능은 추후 추가할 예정입니다.
                </p>
              </section>
          )}
        </main>

        <ReportDrawer
            open={reportOpen}
            question={lastQuestion}
            onClose={() =>
                setReportOpen(false)
            }
        />

        <KnowledgeDrawer
            open={knowledgeOpen}
            onClose={() =>
                setKnowledgeOpen(false)
            }
        />
      </div>
  )
}