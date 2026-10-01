import type { Evidence } from '../api'

function EvidenceCard({ e }: { e: Evidence }) {
  return (
    <article className="evidence" id={`ev-${e.n}`}>
      <header>
        <span className="ev-n">[{e.n}]</span> {e.book_title} · {e.page ?? '?'}쪽
        {e.path && <div className="ev-path">{e.path}</div>}
      </header>
      <pre className="raw-text">{e.raw_text}</pre>
    </article>
  )
}

// 인용된 근거는 펼쳐 보여 주고, 인용되지 않은 근거는 접어 둔다. raw_text는 교재 원문 그대로다.
export default function CitationList({ evidence }: { evidence: Evidence[] }) {
  const cited = evidence.filter((e) => e.cited)
  const others = evidence.filter((e) => !e.cited)
  if (evidence.length === 0) return null
  return (
    <section className="citations">
      <h2>근거 (교재 원문)</h2>
      {cited.length === 0 && <p className="hint">답변이 인용한 근거가 없습니다.</p>}
      {cited.map((e) => (
        <EvidenceCard key={e.n} e={e} />
      ))}
      {others.length > 0 && (
        <details>
          <summary>인용되지 않은 근거 {others.length}개</summary>
          {others.map((e) => (
            <EvidenceCard key={e.n} e={e} />
          ))}
        </details>
      )}
    </section>
  )
}
