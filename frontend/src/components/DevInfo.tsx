import type { QaResponse } from '../api'

const fmt = (v: number | null | undefined, digits = 3) => (v == null ? '-' : v.toFixed(digits))

// 개발 확인용 정보(작은 회색 글씨). 판정기 줄은 판정기가 호출됐을 때만 보인다.
export default function DevInfo({ result }: { result: QaResponse }) {
  const j = result.judge
  const t = result.timings_ms
  return (
    <footer className="dev-info">
      <div>
        구간 {result.zone} ({result.zone_reason}) · 벡터 1위 {fmt(result.scores.vector_top)} · 리랭커 1위{' '}
        {fmt(result.scores.rerank_top)}
      </div>
      {j && (
        <div>
          판정기 {j.provider} · 확률 {fmt(j.probability, 2)} · {j.latency_ms}ms
          {j.error ? ` · 오류 ${j.error}` : ''} (기준 {j.thresholds.can_answer_min}/{j.thresholds.confident_min})
        </div>
      )}
      <div>
        시간(ms) {Object.entries(t)
          .map(([k, v]) => `${k.replace(/_ms$/, '')} ${v}`)
          .join(' · ')}
      </div>
      {result.query_log_id && <div>query_log {result.query_log_id}</div>}
    </footer>
  )
}
