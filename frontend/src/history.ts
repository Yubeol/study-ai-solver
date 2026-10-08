import type {
  QaResponse,
} from './api'

const HISTORY_KEY =
  'study-ai-solver-history'

const MAX_HISTORY =
  100

export type HistoryItem = {
  id: string

  created_at: string

  result: QaResponse
}

function makeHistoryId() {
  if (
    typeof crypto !== 'undefined' &&
    'randomUUID' in crypto
  ) {
    return crypto.randomUUID()
  }

  return `${Date.now()}-${Math.random()
    .toString(36)
    .slice(2)}`
}

export function loadHistory(): HistoryItem[] {
  try {
    const raw =
      localStorage.getItem(
        HISTORY_KEY,
      )

    if (!raw) {
      return []
    }

    const parsed =
      JSON.parse(raw)

    if (
      !Array.isArray(parsed)
    ) {
      return []
    }

    return parsed
      .filter(
        (
          item,
        ): item is HistoryItem =>
          Boolean(
            item &&
            typeof item.id ===
              'string' &&
            typeof item.created_at ===
              'string' &&
            item.result &&
            typeof item.result.question ===
              'string',
          ),
      )
      .slice(
        0,
        MAX_HISTORY,
      )
  } catch {
    return []
  }
}

export function saveHistoryResult(
  result: QaResponse,
): HistoryItem[] {
  try {
    const current =
      loadHistory()

    const item: HistoryItem = {
      id: makeHistoryId(),

      created_at:
        new Date().toISOString(),

      result,
    }

    const next = [
      item,
      ...current,
    ].slice(
      0,
      MAX_HISTORY,
    )

    localStorage.setItem(
      HISTORY_KEY,
      JSON.stringify(next),
    )

    return next
  } catch {
    /*
     * localStorage가 막혀 있거나
     * 용량 문제가 있어도
     * 문제 풀이 자체는 계속 동작한다.
     */
    return loadHistory()
  }
}