// 백엔드 API 호출.
// Vite 개발 서버 프록시가 백엔드로 넘긴다.

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
  thresholds: {
    can_answer_min: number
    confident_min: number
  }
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

  status:
    | 'answered'
    | 'unanswerable'
    | 'error'

  confidence:
    | 'high'
    | 'low'
    | 'unanswerable'
    | null

  zone:
    | 'answer'
    | 'gray'
    | 'reject'

  zone_reason: string

  scores: {
    vector_top: number | null
    rerank_top: number | null
  }

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

/* =========================
   오류 신고
========================= */

export type AnswerReportType =
  | 'wrong_answer'
  | 'wrong_explanation'
  | 'wrong_concept'
  | 'missing_concept'
  | 'wrong_ocr'
  | 'insufficient'
  | 'other'

export type ConceptDetail =
  | 'unrelated_concept'
  | 'wrong_location'
  | 'explanation_mismatch'
  | 'other'

export type CreateAnswerReportRequest = {
  query_log_id: string | null

  report_type: AnswerReportType

  /*
   * wrong_concept일 때만 값이 들어간다.
   *
   * 그 외 신고 유형은 []
   */
  concept_details: ConceptDetail[]

  detail?: string

  question: string

  answer: string

  explanation: string

  evidence: Evidence[]
}

export type CreateAnswerReportResponse = {
  id: number | string
}

/* =========================
   보충 이론
========================= */

export type SupplementSource =
  | 'report'
  | 'unanswerable'

export type SupplementInput = {
  source: SupplementSource

  reportId?: number | string | null

  queryLogId?: string | null

  title?: string

  text?: string

  file?: File | null
}

/* =========================
   공통 request
========================= */

export class ApiError extends Error {}

const QA_TIMEOUT_SECONDS =
  Number(import.meta.env.VITE_QA_TIMEOUT_SECONDS) || 60

const CONNECTION_ERROR =
  '서버에 연결할 수 없습니다(백엔드 실행 확인)'

const TIMEOUT_ERROR =
  '응답 시간이 초과됐습니다'

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutSeconds?: number,
): Promise<T> {
  const controller = new AbortController()

  const timer = timeoutSeconds
    ? setTimeout(
        () => controller.abort(),
        timeoutSeconds * 1000,
      )
    : undefined

  let res: Response

  try {
    res = await fetch(path, {
      ...init,
      signal: controller.signal,
    })
  } catch (e) {
    throw new ApiError(
      controller.signal.aborted
        ? TIMEOUT_ERROR
        : CONNECTION_ERROR,
      {
        cause: e,
      },
    )
  } finally {
    clearTimeout(timer)
  }

  const body = await res.text()

  let data: unknown = null

  try {
    data = body
      ? JSON.parse(body)
      : null
  } catch {
    data = null
  }

  if (!res.ok) {
    if (
      data === null &&
      res.status >= 500
    ) {
      throw new ApiError(
        CONNECTION_ERROR,
      )
    }

    const detail = (
      data as {
        detail?: unknown
      } | null
    )?.detail

    throw new ApiError(
      typeof detail === 'string'
        ? detail
        : `요청 실패(HTTP ${res.status})`,
    )
  }

  return data as T
}

/* =========================
   기존 API
========================= */

export function getSubjects(): Promise<string[]> {
  return request<string[]>(
    '/subjects',
  )
}

export function ask(
  question: string,
): Promise<QaResponse> {
  return request<QaResponse>(
    '/qa',
    {
      method: 'POST',

      headers: {
        'Content-Type':
          'application/json',
      },

      body: JSON.stringify({
        question,
      }),
    },
    QA_TIMEOUT_SECONDS,
  )
}

/* =========================
   오류 신고 API
========================= */

export function createAnswerReport(
  payload: CreateAnswerReportRequest,
): Promise<CreateAnswerReportResponse> {
  return request<CreateAnswerReportResponse>(
    '/answer-reports',
    {
      method: 'POST',

      headers: {
        'Content-Type':
          'application/json',
      },

      body: JSON.stringify(
        payload,
      ),
    },
  )
}

/* =========================
   보충 이론 API
========================= */

export function createSupplement(
  input: SupplementInput,
): Promise<unknown> {
  const formData =
    new FormData()

  formData.append(
    'source',
    input.source,
  )

  if (
    input.reportId !==
      undefined &&
    input.reportId !== null
  ) {
    formData.append(
      'report_id',
      String(input.reportId),
    )
  }

  if (input.queryLogId) {
    formData.append(
      'query_log_id',
      input.queryLogId,
    )
  }

  if (
    input.title?.trim()
  ) {
    formData.append(
      'title',
      input.title.trim(),
    )
  }

  if (
    input.text?.trim()
  ) {
    formData.append(
      'text',
      input.text.trim(),
    )
  }

  if (input.file) {
    formData.append(
      'file',
      input.file,
    )
  }

  /*
   * FormData를 보낼 때는
   * Content-Type을 직접 지정하지 않는다.
   *
   * 브라우저가 boundary를 자동 설정한다.
   */
  return request(
    '/supplements',
    {
      method: 'POST',
      body: formData,
    },
  )
}