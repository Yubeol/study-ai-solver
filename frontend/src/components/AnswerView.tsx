import type { QaResponse } from '../api'
import { circled, splitOptionLines } from '../text'
import CitedText from './CitedText'
import ConfidenceNotice from './ConfidenceNotice'

export default function AnswerView({ result }: { result: QaResponse }) {
  if (result.status === 'error') {
    return <div className="notice error">{result.answer}</div>
  }
  if (result.status === 'unanswerable') {
    return (
      <section className="answer">
        <div className="notice muted">
          <strong>자료에서 확인 불가</strong>
        </div>
        {result.explanation && (
          <p>
            <CitedText text={result.explanation} />
          </p>
        )}
      </section>
    )
  }

  const mcq = result.mcq_check
  const { intro, lines } = mcq ? splitOptionLines(result.explanation) : { intro: result.explanation, lines: [] }

  return (
    <section className="answer">
      <ConfidenceNotice reasons={result.low_confidence_reasons} mcqCheck={mcq} />

      <h2>답</h2>
      <p className={mcq ? 'mcq-answer' : 'answer-text'}>
        <CitedText text={result.answer} />
      </p>

      {(intro || lines.length > 0) && <h2>{mcq ? '보기별 판단' : '설명'}</h2>}
      {intro && (
        <p>
          <CitedText text={intro} />
        </p>
      )}
      {lines.length > 0 && (
        <ul className="option-lines">
          {lines.map((line) => (
            <li key={line.num} className={line.num === mcq?.chosen ? 'chosen' : undefined}>
              {mcq?.option_verdicts[String(line.num)] && (
                <span className="verdict">
                  {circled(line.num)} {mcq.option_verdicts[String(line.num)]}
                </span>
              )}
              <CitedText text={line.text} />
            </li>
          ))}
        </ul>
      )}

      {result.confusions && (
        <>
          <h2>헷갈리는 점</h2>
          <p>
            <CitedText text={result.confusions} />
          </p>
        </>
      )}
    </section>
  )
}
