import {
  useState,
} from 'react'

import {
  ask,
  type QaResponse,
} from './api'

import {
  loadHistory,
  saveHistoryResult,
  type HistoryItem,
} from './history'

import AnswerView from './components/AnswerView'
import CitationList from './components/CitationList'
import DevInfo from './components/DevInfo'
import KnowledgeDrawer from './components/KnowledgeDrawer'
import QuestionForm from './components/QuestionForm'
import ReportDrawer from './components/ReportDrawer'
import Sidebar, {
  type Menu,
} from './components/Sidebar'

export default function App() {
  /* =========================
     문제 풀이
  ========================= */

  const [
    loading,
    setLoading,
  ] = useState(false)

  const [
    result,
    setResult,
  ] = useState<QaResponse | null>(
    null,
  )

  const [
    error,
    setError,
  ] = useState<string | null>(
    null,
  )

  /* =========================
     히스토리
  ========================= */

  const [
    history,
    setHistory,
  ] = useState<HistoryItem[]>(
    () => loadHistory(),
  )

  /* =========================
     화면
  ========================= */

  const [
    currentMenu,
    setCurrentMenu,
  ] = useState<Menu>(
    'home',
  )

  /* =========================
     Drawer
  ========================= */

  const [
    reportOpen,
    setReportOpen,
  ] = useState(false)

  const [
    knowledgeOpen,
    setKnowledgeOpen,
  ] = useState(false)

  /* =========================
     문제 풀이 API
  ========================= */

  const onSubmit = async (
    question: string,
  ) => {
    if (!question.trim()) {
      return
    }

    setLoading(true)

    setError(null)

    setResult(null)

    try {
      const response =
        await ask(
          question,
        )

      setResult(
        response,
      )

      /*
       * QA 응답을 받은 뒤
       * localStorage에 저장.
       *
       * 저장 실패가 발생해도
       * 화면은 정상 동작한다.
       */
      const nextHistory =
        saveHistoryResult(
          response,
        )

      setHistory(
        nextHistory,
      )
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : '문제 풀이 중 오류가 발생했습니다.',
      )
    } finally {
      setLoading(false)
    }
  }

  /* =========================
     히스토리 다시 보기
  ========================= */

  const openHistoryItem = (
    item: HistoryItem,
  ) => {
    setError(null)

    setLoading(false)

    setResult(
      item.result,
    )

    setCurrentMenu(
      'home',
    )

    setReportOpen(false)

    setKnowledgeOpen(false)
  }

  return (
    <div className="app-shell">
      {/* =========================
          왼쪽 메뉴
      ========================= */}

      <Sidebar
        current={
          currentMenu
        }
        onChange={
          setCurrentMenu
        }
      />

      {/* =========================
          본문
      ========================= */}

      <main className="app-main">
        {/* =========================
            문제 풀이
        ========================= */}

        {currentMenu ===
          'home' && (
          <div className="study-grid has-result">
            {/* 왼쪽 */}

            <QuestionForm
              loading={
                loading
              }
              onSubmit={
                onSubmit
              }
            />

            {/* 오른쪽 */}

            <section className="result-column">
              {/* 처음 화면 */}

              {!result &&
                !error &&
                !loading && (
                  <div className="empty-result-card">
                    <h2>
                      정답 및 해설
                    </h2>

                    <p>
                      문제를 입력하면
                      정답과 해설이
                      여기에 표시됩니다.
                    </p>
                  </div>
                )}

              {/* 로딩 */}

              {loading && (
                <div className="empty-result-card">
                  <h2>
                    문제를 분석하고 있어요
                  </h2>

                  <p>
                    교재에서 관련 개념과
                    근거를 찾고 있습니다.
                  </p>
                </div>
              )}

              {/* 에러 */}

              {error && (
                <div className="notice error">
                  {error}
                </div>
              )}

              {/* 결과 */}

              {result && (
                <>
                  <AnswerView
                    result={
                      result
                    }
                    onReportOpen={() =>
                      setReportOpen(
                        true,
                      )
                    }
                    onKnowledgeOpen={() =>
                      setKnowledgeOpen(
                        true,
                      )
                    }
                  />

                  {/* 교재 근거 */}

                  {result
                    .evidence
                    ?.length >
                    0 && (
                    <CitationList
                      evidence={
                        result.evidence
                      }
                    />
                  )}

                  {/* 개발자 확인용 */}

                  <details className="developer-details">
                    <summary>
                      개발 정보 보기
                    </summary>

                    <DevInfo
                      result={
                        result
                      }
                    />
                  </details>
                </>
              )}
            </section>
          </div>
        )}

        {/* =========================
            히스토리
        ========================= */}

        {currentMenu ===
          'history' && (
          <section className="history-page">
            <div className="history-header">
              <div>
                <h1>
                  히스토리
                </h1>

                <p>
                  최근에 풀었던 문제와
                  답변을 다시 볼 수
                  있습니다.
                </p>
              </div>

              <span className="history-count">
                {history.length}
                /100
              </span>
            </div>

            {history.length ===
            0 ? (
              <div className="empty-state">
                아직 저장된
                풀이 기록이 없습니다.
              </div>
            ) : (
              <div className="history-list">
                {history.map(
                  (
                    item,
                  ) => {
                    const date =
                      new Date(
                        item.created_at,
                      )

                    return (
                      <button
                        key={
                          item.id
                        }
                        type="button"
                        className="history-card"
                        onClick={() =>
                          openHistoryItem(
                            item,
                          )
                        }
                      >
                        <div className="history-card-top">
                          <strong>
                            {
                              item
                                .result
                                .question
                            }
                          </strong>

                          <span>
                            {date.toLocaleString(
                              'ko-KR',
                            )}
                          </span>
                        </div>

                        <p className="history-answer">
                          {
                            item
                              .result
                              .answer
                          }
                        </p>

                        <div className="history-card-bottom">
                          <span>
                            근거{' '}
                            {
                              item
                                .result
                                .evidence
                                ?.length ??
                              0
                            }
                            개
                          </span>

                          <span>
                            다시 보기
                          </span>
                        </div>
                      </button>
                    )
                  },
                )}
              </div>
            )}
          </section>
        )}

        {/* =========================
            즐겨찾기
        ========================= */}

        {currentMenu ===
          'favorites' && (
          <section className="placeholder-page">
            <h1>
              즐겨찾기
            </h1>

            <p>
              저장한 문제를 모아보는
              기능은 추후 연결할
              예정입니다.
            </p>
          </section>
        )}

        {/* =========================
            자료 관리
        ========================= */}

        {currentMenu ===
          'knowledge' && (
          <section className="placeholder-page">
            <div className="placeholder-header">
              <div>
                <h1>
                  자료 관리
                </h1>

                <p>
                  등록된 보충 이론을
                  확인하고 관리하는
                  화면입니다.
                </p>
              </div>
            </div>

            <div className="empty-state">
              검토 대기 및 승인된
              보충 자료가 이곳에
              표시될 예정입니다.
            </div>
          </section>
        )}

        {/* =========================
            설정
        ========================= */}

        {currentMenu ===
          'settings' && (
          <section className="placeholder-page">
            <h1>
              설정
            </h1>

            <p>
              설정 기능은 추후
              추가할 예정입니다.
            </p>
          </section>
        )}
      </main>

      {/* =========================
          오류 신고 Drawer
      ========================= */}

      <ReportDrawer
        open={
          reportOpen
        }
        result={
          result
        }
        onClose={() =>
          setReportOpen(
            false,
          )
        }
      />

      {/* =========================
          확인 불가 → 이론 보충
      ========================= */}

      <KnowledgeDrawer
        open={
          knowledgeOpen
        }
        result={
          result
        }
        onClose={() =>
          setKnowledgeOpen(
            false,
          )
        }
      />
    </div>
  )
}