import { useEffect, useState } from 'react'
import { getSubjects } from '../api'

// 검색 대상 선택. 지금은 과목 목록이지만 나중에 "업로드한 자료(문서) 선택"으로 바뀐다.
// 바깥에는 value/onChange만 노출하므로 이 파일만 바꾸면 된다.
// 현재 /qa에는 과목 필터가 없어 선택값을 보내지 않는다(D-029).
type Props = {
  value: string
  onChange: (value: string) => void
}

export default function SourceSelector({ value, onChange }: Props) {
  const [subjects, setSubjects] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSubjects()
      .then((list) => {
        setSubjects(list)
        if (!value && list.length > 0) onChange(list[0])
      })
      .catch((e: Error) => setError(e.message))
    // 처음 한 번만 불러온다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="source-selector">
      <label>
        과목{' '}
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={subjects.length === 0}>
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <span className="hint">현재 검색은 전체 자료 대상</span>
      {error && <span className="error-inline">{error}</span>}
    </div>
  )
}
