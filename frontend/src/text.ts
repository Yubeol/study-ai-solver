// 답변 문자열을 화면용으로 나누는 함수들(표시만 바꾸고 내용은 바꾸지 않는다).

const CIRCLED = ['①', '②', '③', '④']

// 백엔드 app/qa/mcq_check.py의 option_lines와 같은 규칙: 글 처음·줄바꿈·문장 끝(".", "]", "다") 뒤의 "①은" 형태만 보기 줄 머리로 본다.
const OPTION_HEAD = /([①②③④]|\(\s*[1-4]\s*\))\s*(?:은|는)/g

export type OptionLine = { num: number; text: string }

function optionNum(head: string): number {
  const i = CIRCLED.indexOf(head)
  return i >= 0 ? i + 1 : Number(head.replace(/[^1-4]/g, ''))
}

export function splitOptionLines(explanation: string): { intro: string; lines: OptionLine[] } {
  const heads: { index: number; num: number }[] = []
  for (const m of explanation.matchAll(OPTION_HEAD)) {
    const before = explanation.slice(0, m.index).replace(/[ \t]+$/, '')
    if (!before || /[\n.\]다]$/.test(before)) heads.push({ index: m.index, num: optionNum(m[1]) })
  }
  if (heads.length === 0) return { intro: explanation, lines: [] }
  const lines = heads.map((h, i) => ({
    num: h.num,
    text: explanation.slice(h.index, i + 1 < heads.length ? heads[i + 1].index : undefined).trim(),
  }))
  return { intro: explanation.slice(0, heads[0].index).trim(), lines }
}

export function circled(n: number): string {
  return CIRCLED[n - 1] ?? `(${n})`
}
