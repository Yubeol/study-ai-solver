import type { QaResponse } from '../api'
import { circled, splitOptionLines } from '../text'
import CitedText from './CitedText'
import ConfidenceNotice from './ConfidenceNotice'

type Props = {
    result: QaResponse
    onReportOpen: () => void
    onKnowledgeOpen: () => void
}

export default function AnswerView({
                                       result,
                                       onReportOpen,
                                       onKnowledgeOpen,
                                   }: Props) {
    if (result.status === 'error') {
        return (
            <section className="answer-panel">
                <div className="notice error">
                    {result.answer}
                </div>
            </section>
        )
    }

    if (result.status === 'unanswerable') {
        return (
            <section className="answer-panel">
                <div className="knowledge-missing-card">
                    <span className="status-chip">자료 부족</span>

                    <h2>해설에 필요한 자료가 부족합니다.</h2>

                    <p>
                        현재 등록되어 있는 교재 자료에서는 이 문제를
                        충분히 설명할 수 있는 근거를 찾지 못했습니다.
                    </p>

                    {result.explanation && (
                        <div className="missing-description">
                            <CitedText text={result.explanation} />
                        </div>
                    )}

                    <button
                        type="button"
                        className="primary-button"
                        onClick={onKnowledgeOpen}
                    >
                        관련 이론 추가하기
                    </button>
                </div>
            </section>
        )
    }

    const mcq = result.mcq_check

    const { intro, lines } = mcq
        ? splitOptionLines(result.explanation)
        : {
            intro: result.explanation,
            lines: [],
        }

    return (
        <section className="answer-panel">
            <div className="answer-panel-header">
                <div>
                    <h2>정답 및 해설</h2>
                    <p>교재 근거를 바탕으로 분석한 결과입니다.</p>
                </div>

                <button
                    type="button"
                    className="report-open-button"
                    onClick={onReportOpen}
                >
                    오류 신고
                </button>
            </div>

            <ConfidenceNotice
                reasons={result.low_confidence_reasons}
                mcqCheck={mcq}
            />

            <div className="result-card answer-result-card">
                <span className="result-label">정답</span>

                <div
                    className={
                        mcq ? 'answer-number' : 'subjective-answer'
                    }
                >
                    <CitedText text={result.answer} />
                </div>
            </div>

            {intro && (
                <div className="result-card">
                    <h3>해설</h3>

                    <div className="explanation-text">
                        <CitedText text={intro} />
                    </div>
                </div>
            )}

            {lines.length > 0 && (
                <div className="result-card">
                    <h3>선지별 해설</h3>

                    <div className="choice-list">
                        {lines.map((line) => {
                            const selected = line.num === mcq?.chosen

                            return (
                                <div
                                    key={line.num}
                                    className={
                                        selected
                                            ? 'choice-item selected'
                                            : 'choice-item'
                                    }
                                >
                                    <div className="choice-number">
                                        {circled(line.num)}
                                    </div>

                                    <div className="choice-content">
                                        {mcq?.option_verdicts[String(line.num)] && (
                                            <span className="choice-verdict">
                        {mcq.option_verdicts[String(line.num)]}
                      </span>
                                        )}

                                        <p>
                                            ㄴ <CitedText text={line.text} />
                                        </p>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {result.confusions && (
                <div className="result-card subtle-card">
                    <h3>헷갈리기 쉬운 부분</h3>

                    <p>
                        <CitedText text={result.confusions} />
                    </p>
                </div>
            )}

            <div className="answer-bottom-actions">
                <span>답변에 문제가 있나요?</span>

                <button
                    type="button"
                    onClick={onReportOpen}
                >
                    오류 신고하기
                </button>
            </div>
        </section>
    )
}