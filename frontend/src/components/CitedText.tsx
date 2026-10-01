// 본문의 [n] 인용 번호를 해당 근거 카드로 가는 링크로 바꿔 보여 준다.
export default function CitedText({ text }: { text: string }) {
  const parts = text.split(/(\[\d+\])/g)
  return (
    <>
      {parts.map((p, i) => {
        const m = /^\[(\d+)\]$/.exec(p)
        return m ? (
          <a key={i} className="cite" href={`#ev-${m[1]}`}>
            {p}
          </a>
        ) : (
          <span key={i}>{p}</span>
        )
      })}
    </>
  )
}
