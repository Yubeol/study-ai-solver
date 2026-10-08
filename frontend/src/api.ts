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

  /*
   * #10 이후 근거 메타데이터
   * 기존 응답과의 호환을 위해 optional 처리
   */
  kind?: 'theory' | 'table' | 'visual' | 'code' | 'formula' | string | null
  corpus?: string | null

  block_id?: string | null
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
   * wrong_concept일 때만 선택값이 들어가고
   * 그 외 신고 유형은 [] 전송
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
   이론 수정
========================= */

export type BlockDetail = {
  block_id: string
  kind: string
  title: string | null
  title_path: string | null
  clean_text: string
}

export type BlockCorrection = {
  id: string

  block_id: string

  report_id: string | null

  base_clean_text: string

  base_clean_text_hash: string

  new_clean_text: string

  reason: string | null

  status: string

  review_note: string | null

  reviewed_by: string | null

  applied_note: string | null

  created_at: string

  reviewed_at: string | null

  applied_at: string | null
}

export type CreateBlockCorrectionRequest = {
  block_id: string

  new_clean_text: string

  reason?: string
}

export type ApproveBlockCorrectionRequest = {
  reviewed_by?: string

  review_note?: string

  resolve_report?: boolean
}

/* =========================
   OCR
========================= */

export type OcrResponse = {
  text: string

  engine:
    | 'google_vision'
    | 'gemini'
    | 'paddleocr'

  model: string | null

  problem_text: string

  choices: string[]

  figure_description: string

  fallback_reason:
    | 'vision_not_configured'
    | 'vision_failed'
    | 'llm_not_configured'
    | 'llm_failed'
    | null
}

/* =========================
   공통 request
========================= */

export class ApiError extends Error {}

const QA_TIMEOUT_SECONDS =
  Number(
    import.meta.env.VITE_QA_TIMEOUT_SECONDS,
  ) || 60

const OCR_TIMEOUT_SECONDS =
  Number(
    import.meta.env.VITE_OCR_TIMEOUT_SECONDS,
  ) || 330

const CONNECTION_ERROR =
  '서버에 연결할 수 없습니다(백엔드 실행 확인)'

const TIMEOUT_ERROR =
  '응답 시간이 초과됐습니다'

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutSeconds?: number,
): Promise<T> {
  const controller =
    new AbortController()

  const timer =
    timeoutSeconds
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

  const body =
    await res.text()

  let data: unknown = null

  let jsonParsed = false

  if (body) {
    try {
      data =
        JSON.parse(body)

      jsonParsed =
        true
    } catch {
      data = null
    }
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

  /*
   * HTTP 200인데 JSON이 아닌 응답이면
   * 정상 API 응답으로 처리하지 않는다.
   *
   * Vite proxy 누락으로 index.html이
   * 반환되는 경우도 여기서 잡힌다.
   */
  if (
    body &&
    !jsonParsed
  ) {
    throw new ApiError(
      '서버 응답 형식이 올바르지 않습니다.',
    )
  }

  return data as T
}

/* =========================
   기본 API
========================= */

export function getSubjects():
  Promise<string[]> {
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
  payload:
    CreateAnswerReportRequest,
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
    input.reportId !== undefined &&
    input.reportId !== null
  ) {
    formData.append(
      'report_id',
      String(
        input.reportId,
      ),
    )
  }

  if (
    input.queryLogId
  ) {
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

  if (
    input.file
  ) {
    formData.append(
      'file',
      input.file,
    )
  }

  return request(
    '/supplements',
    {
      method: 'POST',
      body: formData,
    },
  )
}

/* =========================
   이론 수정 API
========================= */

export function getBlock(
  blockId: string,
): Promise<BlockDetail> {
  return request<BlockDetail>(
    `/blocks/${encodeURIComponent(
      blockId,
    )}`,
  )
}

export function createBlockCorrection(
  payload:
    CreateBlockCorrectionRequest,
): Promise<BlockCorrection> {
  return request<BlockCorrection>(
    '/block-corrections',
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

export function approveBlockCorrection(
  correctionId: string,
  payload:
    ApproveBlockCorrectionRequest =
      {},
): Promise<BlockCorrection> {
  return request<BlockCorrection>(
    `/block-corrections/${encodeURIComponent(
      correctionId,
    )}/approve`,
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
   OCR API
========================= */

export function ocr(
  file: File,
): Promise<OcrResponse> {
  const body =
    new FormData()

  body.append(
    'file',
    file,
  )

  return request<OcrResponse>(
    '/ocr',
    {
      method: 'POST',
      body,
    },
    OCR_TIMEOUT_SECONDS,
  )
}