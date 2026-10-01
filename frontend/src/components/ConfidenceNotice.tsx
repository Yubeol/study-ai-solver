import type { McqCheck } from '../api'

// low_confidence_reasons 코드 → 사람이 읽는 문구(백엔드 app/qa/service.py low_confidence_reasons)
const REASON_TEXT: Record<string, string> = {
  gray_no_judge: '검색 근거와 질문의 관련도가 애매합니다(판정기 꺼짐).',
  gray_judge_not_confident: '판정기가 근거로 답할 수 있다고 봤지만 확신이 높지 않습니다.',
  gray_judge_error: '판정기 호출에 실패해 근거 확인을 못 했습니다.',
  no_valid_citation: '답변이 유효한 근거를 인용하지 않았습니다.',
  mcq_inconsistent: '보기별 판단과 고른 번호가 맞지 않습니다.',
}

type Props = {
  reasons: string[]
  mcqCheck: McqCheck | null
}

export default function ConfidenceNotice({ reasons, mcqCheck }: Props) {
  if (reasons.length === 0) return null
  return (
    <div className="notice warn">
      <strong>근거 확신 낮음</strong> — 교재 원문과 직접 대조해 확인하세요.
      <ul>
        {reasons.map((r) => (
          <li key={r}>
            {REASON_TEXT[r] ?? r}
            {r === 'mcq_inconsistent' && mcqCheck && mcqCheck.reasons.length > 0 && (
              <ul>
                {mcqCheck.reasons.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
