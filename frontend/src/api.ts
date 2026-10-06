// 백엔드 API 호출. 경로는 Vite 개발 서버 프록시가 백엔드로 넘긴다(vite.config.ts).

export type Evidence = {
  n: number
  chunk_id: string
  book_title: string
  page: string | number | null
  path: string
  raw_text: string
  vector_score: number | null
  rerank_score: number | null
  cited: boolean
}

export type JudgeInfo = {
  provider: string
  model: string | null
  probability: number | null
  can_answer: boolean | null
  confident: boolean
  thresholds: { can_answer_min: number; confident_min: number }
  latency_ms: number
  attempts: number
  error: string | null
}

export type McqCheck = {
  is_mcq: boolean
  negative: boolean
  chosen: number
  option_verdicts: Record<string, string>
  consistent: boolean
  reasons: string[]
}

export type QaResponse = {
  question: string
  status: 'answered' | 'unanswerable' | 'error'
  confidence: 'high' | 'low' | 'unanswerable' | null
  zone: 'answer' | 'gray' | 'reject'
  zone_reason: string
  scores: { vector_top: number | null; rerank_top: number | null }
  judge: JudgeInfo | null
  answer: string
  explanation: string
  confusions: string
  low_confidence: boolean
  low_confidence_reasons: string[]
  mcq_check: McqCheck | null
  evidence: Evidence[]
  citations: Evidence[]
  timings_ms: Record<string, number>
  query_log_id: string | null
  error?: string
}

export class ApiError extends Error {}

const QA_TIMEOUT_SECONDS = Number(import.meta.env.VITE_QA_TIMEOUT_SECONDS) || 60
const CONNECTION_ERROR = '서버에 연결할 수 없습니다(백엔드 실행 확인)'
const TIMEOUT_ERROR = '응답 시간이 초과됐습니다'

async function request<T>(path: string, init: RequestInit = {}, timeoutSeconds?: number): Promise<T> {
  const controller = new AbortController()
  const timer = timeoutSeconds ? setTimeout(() => controller.abort(), timeoutSeconds * 1000) : undefined
  let res: Response
  try {
    res = await fetch(path, { ...init, signal: controller.signal })
  } catch (e) {
    throw new ApiError(controller.signal.aborted ? TIMEOUT_ERROR : CONNECTION_ERROR, { cause: e })
  } finally {
    clearTimeout(timer)
  }
  const body = await res.text()
  let data: unknown = null
  try {
    data = body ? JSON.parse(body) : null
  } catch {
    data = null
  }
  if (!res.ok) {
    // 백엔드가 꺼져 있으면 Vite 프록시가 JSON 없는 5xx를 돌려준다.
    if (data === null && res.status >= 500) throw new ApiError(CONNECTION_ERROR)
    const detail = (data as { detail?: unknown } | null)?.detail
    throw new ApiError(typeof detail === 'string' ? detail : `요청 실패(HTTP ${res.status})`)
  }
  return data as T
}

export function getSubjects(): Promise<string[]> {
  return request<string[]>('/subjects')
}

export function ask(question: string): Promise<QaResponse> {
  return request<QaResponse>(
    '/qa',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) },
    QA_TIMEOUT_SECONDS,
  )
}

export type OcrResponse = {
  text: string
  engine: 'google_vision' | 'gemini' | 'paddleocr'
  model: string | null
  problem_text: string
  choices: string[]
  figure_description: string
  fallback_reason: 'vision_not_configured' | 'vision_failed' | 'llm_not_configured' | 'llm_failed' | null
}

// 문제 사진 → 문제 텍스트(POST /ocr). Google Vision(기본)·Gemini, 실패하면 PaddleOCR(첫 호출은 모델 로드로 느림).
export function ocr(file: File): Promise<OcrResponse> {
  const body = new FormData()
  body.append('file', file)
  return request<OcrResponse>('/ocr', { method: 'POST', body }, QA_TIMEOUT_SECONDS)
}
