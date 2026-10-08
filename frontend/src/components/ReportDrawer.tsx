import {
    useState,
} from 'react'

import {
    createAnswerReport,
    createSupplement,
    type AnswerReportType,
    type ConceptDetail,
    type QaResponse,
} from '../api'

type Props = {
    open: boolean

    result: QaResponse | null

    onClose: () => void
}

type SupplementType =
    | 'text'
    | 'image'
    | 'pdf'

const CONCEPT_DETAILS: {
    value: ConceptDetail
    title: string
}[] = [
    {
        value: 'unrelated_concept',
        title: '관련 없는 개념',
    },
    {
        value: 'wrong_location',
        title: '근거 위치 오류',
    },
    {
        value: 'explanation_mismatch',
        title: '근거 내용과 해설 불일치',
    },
    {
        value: 'other',
        title: '기타',
    },
]

const REPORTS: {
    value: AnswerReportType
    title: string
    description: string
}[] = [
    {
        value: 'wrong_answer',
        title: '답이 틀렸어요',
        description:
            '선택된 정답이 실제 정답과 다른 것 같아요.',
    },

    {
        value: 'wrong_explanation',
        title: '해설이 틀렸어요',
        description:
            '정답은 맞지만 풀이 과정이나 설명에 오류가 있어요.',
    },

    {
        value: 'wrong_concept',
        title: '개념/근거가 이상해요',
        description:
            '사용한 개념이나 교재 근거가 적절하지 않은 것 같아요.',
    },

    {
        value: 'missing_concept',
        title: '관련 개념이 부족해요',
        description:
            '문제를 풀기 위한 이론이나 개념 자료가 부족한 것 같아요.',
    },

    {
        value: 'wrong_ocr',
        title: '문제를 잘못 읽었어요',
        description:
            '문제나 선지를 잘못 인식했어요.',
    },

    {
        value: 'insufficient',
        title: '설명이 부족해요',
        description:
            '조금 더 자세한 설명이 필요해요.',
    },

    {
        value: 'other',
        title: '기타',
        description:
            '위 항목에 해당하지 않는 문제가 있어요.',
    },
]

export default function ReportDrawer({
    open,
    result,
    onClose,
}: Props) {
    const [
        type,
        setType,
    ] = useState<AnswerReportType | null>(
        null,
    )

    const [
        conceptDetails,
        setConceptDetails,
    ] = useState<ConceptDetail[]>([])

    const [
        detail,
        setDetail,
    ] = useState('')

    const [
        supplementType,
        setSupplementType,
    ] = useState<SupplementType>('text')

    const [
        supplementTitle,
        setSupplementTitle,
    ] = useState('')

    const [
        supplementText,
        setSupplementText,
    ] = useState('')

    const [
        supplementFile,
        setSupplementFile,
    ] = useState<File | null>(null)

    const [
        submitting,
        setSubmitting,
    ] = useState(false)

    const [
        submitError,
        setSubmitError,
    ] = useState<string | null>(null)

    if (!open) {
        return null
    }

    const showSupplement =
        type === 'wrong_concept' ||
        type === 'missing_concept'

    const hasSupplement =
        supplementText.trim() !== '' ||
        supplementFile !== null

    const dirty =
        type !== null ||
        conceptDetails.length > 0 ||
        detail.trim() !== '' ||
        supplementTitle.trim() !== '' ||
        hasSupplement

    const reset = () => {
        setType(null)

        setConceptDetails([])

        setDetail('')

        setSupplementType('text')

        setSupplementTitle('')

        setSupplementText('')

        setSupplementFile(null)

        setSubmitError(null)
    }

    const requestClose = () => {
        if (submitting) {
            return
        }

        if (
            dirty &&
            !window.confirm(
                '작성 중인 내용이 있습니다.\n오류 신고를 취소할까요?',
            )
        ) {
            return
        }

        reset()

        onClose()
    }

    const handleReportType = (
        nextType: AnswerReportType,
    ) => {
        setType(nextType)

        /*
         * concept_details는
         * wrong_concept일 때만 사용한다.
         *
         * 다른 신고 유형으로 바꾸면
         * 기존 선택값을 비운다.
         */
        if (
            nextType !== 'wrong_concept'
        ) {
            setConceptDetails([])
        }

        setSubmitError(null)
    }

    const toggleConceptDetail = (
        value: ConceptDetail,
    ) => {
        setConceptDetails(
            (current) =>
                current.includes(value)
                    ? current.filter(
                        (item) =>
                            item !== value,
                    )
                    : [
                        ...current,
                        value,
                    ],
        )
    }

    const handleSupplementType = (
        next: SupplementType,
    ) => {
        setSupplementType(next)

        setSupplementFile(null)

        setSubmitError(null)
    }

    const submit = async () => {
        if (!result) {
            setSubmitError(
                '신고할 문제 정보를 찾을 수 없습니다.',
            )

            return
        }

        if (!type) {
            setSubmitError(
                '오류 유형을 선택해주세요.',
            )

            return
        }

        /*
         * 텍스트 자료에서 제목을 작성했다면
         * 실제 내용도 입력해야 한다.
         */
        if (
            showSupplement &&
            supplementType === 'text' &&
            supplementTitle.trim() !== '' &&
            supplementText.trim() === ''
        ) {
            setSubmitError(
                '보충 이론 내용을 입력해주세요.',
            )

            return
        }

        setSubmitting(true)

        setSubmitError(null)

        try {
            /*
             * 1. 오류 신고 등록
             *
             * wrong_concept일 때만
             * concept_details 값을 보낸다.
             *
             * 나머지는 빈 배열을 보낸다.
             */

            const report =
                await createAnswerReport({
                    query_log_id:
                        result.query_log_id,

                    report_type:
                        type,

                    concept_details:
                        type ===
                        'wrong_concept'
                            ? conceptDetails
                            : [],

                    detail:
                        detail.trim() ||
                        undefined,

                    question:
                        result.question,

                    answer:
                        result.answer,

                    explanation:
                        result.explanation,

                    evidence:
                        result.evidence,
                })

            /*
             * 2. 보충 이론이 실제로 입력된 경우
             * 방금 등록된 신고 id에 연결한다.
             */

            if (
                showSupplement &&
                hasSupplement
            ) {
                await createSupplement({
                    source:
                        'report',

                    reportId:
                        report.id,

                    queryLogId:
                        result.query_log_id,

                    title:
                        supplementTitle,

                    text:
                        supplementType ===
                        'text'
                            ? supplementText
                            : undefined,

                    file:
                        supplementType ===
                        'text'
                            ? null
                            : supplementFile,
                })
            }

            alert(
                showSupplement &&
                hasSupplement
                    ? '신고와 보충 이론이 등록되었습니다.\n검토 후 반영됩니다.'
                    : '오류 신고가 등록되었습니다.',
            )

            reset()

            onClose()
        } catch (e) {
            setSubmitError(
                e instanceof Error
                    ? e.message
                    : '신고 등록에 실패했습니다.',
            )
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <>
            <button
                type="button"
                className="drawer-backdrop"
                aria-label="오류 신고 닫기"
                onClick={requestClose}
            />

            <aside className="drawer">
                <div className="drawer-header">
                    <div>
                        <h2>
                            오류 신고
                        </h2>

                        <p>
                            문제가 있는 부분을
                            선택해주세요.
                        </p>
                    </div>

                    <button
                        type="button"
                        className="drawer-close"
                        onClick={requestClose}
                        aria-label="닫기"
                    >
                        ×
                    </button>
                </div>

                <div className="drawer-body">
                    {/* =========================
                        신고 유형
                    ========================= */}

                    <div className="report-list">
                        {REPORTS.map(
                            (item) => (
                                <label
                                    key={
                                        item.value
                                    }
                                    className={
                                        type ===
                                        item.value
                                            ? 'report-card selected'
                                            : 'report-card'
                                    }
                                >
                                    <input
                                        type="radio"
                                        name="report-type"
                                        checked={
                                            type ===
                                            item.value
                                        }
                                        onChange={() =>
                                            handleReportType(
                                                item.value,
                                            )
                                        }
                                    />

                                    <span>
                                        <strong>
                                            {
                                                item.title
                                            }
                                        </strong>

                                        <small>
                                            {
                                                item.description
                                            }
                                        </small>
                                    </span>
                                </label>
                            ),
                        )}
                    </div>

                    {/* =========================
                        개념/근거 세부 항목

                        wrong_concept에서만 표시
                        여러 개 선택 가능
                    ========================= */}

                    {type ===
                        'wrong_concept' && (
                        <section className="concept-detail-section">
                            <div className="concept-detail-heading">
                                <strong>
                                    어떤 부분이
                                    이상한가요?
                                </strong>

                                <span>
                                    복수 선택 가능
                                </span>
                            </div>

                            <div className="concept-detail-list">
                                {CONCEPT_DETAILS.map(
                                    (item) => (
                                        <label
                                            key={
                                                item.value
                                            }
                                            className={
                                                conceptDetails.includes(
                                                    item.value,
                                                )
                                                    ? 'concept-detail-card selected'
                                                    : 'concept-detail-card'
                                            }
                                        >
                                            <input
                                                type="checkbox"
                                                checked={
                                                    conceptDetails.includes(
                                                        item.value,
                                                    )
                                                }
                                                onChange={() =>
                                                    toggleConceptDetail(
                                                        item.value,
                                                    )
                                                }
                                            />

                                            <span>
                                                {
                                                    item.title
                                                }
                                            </span>
                                        </label>
                                    ),
                                )}
                            </div>
                        </section>
                    )}

                    {/* =========================
                        상세 내용
                    ========================= */}

                    <label className="detail-input">
                        <span>
                            상세 내용
                            <small>
                                {' '}
                                선택
                            </small>
                        </span>

                        <textarea
                            value={detail}
                            maxLength={500}
                            onChange={(e) =>
                                setDetail(
                                    e.target.value,
                                )
                            }
                            placeholder="어떤 부분이 이상했는지 알려주세요."
                        />

                        <small>
                            {detail.length}/500
                        </small>
                    </label>

                    {/* =========================
                        보충 이론

                        wrong_concept
                        missing_concept
                    ========================= */}

                    {showSupplement && (
                        <section className="report-supplement">
                            <div className="report-supplement-heading">
                                <strong>
                                    보충 이론
                                </strong>

                                <span>
                                    선택
                                </span>
                            </div>

                            <p className="report-supplement-description">
                                관련 자료가 있다면
                                함께 등록해주세요.
                                등록된 자료는 바로
                                반영되지 않으며 검토 후
                                반영됩니다.
                            </p>

                            <div className="knowledge-tabs">
                                <button
                                    type="button"
                                    className={
                                        supplementType ===
                                        'text'
                                            ? 'active'
                                            : ''
                                    }
                                    onClick={() =>
                                        handleSupplementType(
                                            'text',
                                        )
                                    }
                                >
                                    텍스트
                                </button>

                                <button
                                    type="button"
                                    className={
                                        supplementType ===
                                        'image'
                                            ? 'active'
                                            : ''
                                    }
                                    onClick={() =>
                                        handleSupplementType(
                                            'image',
                                        )
                                    }
                                >
                                    이미지
                                </button>

                                <button
                                    type="button"
                                    className={
                                        supplementType ===
                                        'pdf'
                                            ? 'active'
                                            : ''
                                    }
                                    onClick={() =>
                                        handleSupplementType(
                                            'pdf',
                                        )
                                    }
                                >
                                    PDF
                                </button>
                            </div>

                            <label className="knowledge-field">
                                <span>
                                    자료 제목
                                </span>

                                <input
                                    value={
                                        supplementTitle
                                    }
                                    onChange={(e) =>
                                        setSupplementTitle(
                                            e.target.value,
                                        )
                                    }
                                    placeholder="자료 제목을 입력해주세요."
                                />
                            </label>

                            {/* 텍스트 */}

                            {supplementType ===
                                'text' && (
                                <label className="knowledge-field">
                                    <span>
                                        이론 내용
                                    </span>

                                    <textarea
                                        value={
                                            supplementText
                                        }
                                        onChange={(e) =>
                                            setSupplementText(
                                                e.target.value,
                                            )
                                        }
                                        placeholder="보충할 이론이나 개념을 입력해주세요."
                                    />
                                </label>
                            )}

                            {/* 이미지 */}

                            {supplementType ===
                                'image' && (
                                <label className="knowledge-file-box">
                                    <strong>
                                        이미지 선택
                                    </strong>

                                    <span>
                                        JPG, PNG
                                    </span>

                                    <input
                                        type="file"
                                        accept="image/png,image/jpeg"
                                        onChange={(e) =>
                                            setSupplementFile(
                                                e
                                                    .target
                                                    .files?.[0] ??
                                                null,
                                            )
                                        }
                                    />

                                    {supplementFile && (
                                        <small>
                                            {
                                                supplementFile.name
                                            }
                                        </small>
                                    )}
                                </label>
                            )}

                            {/* PDF */}

                            {supplementType ===
                                'pdf' && (
                                <label className="knowledge-file-box">
                                    <strong>
                                        PDF 선택
                                    </strong>

                                    <span>
                                        PDF 자료를
                                        선택해주세요.
                                    </span>

                                    <input
                                        type="file"
                                        accept="application/pdf"
                                        onChange={(e) =>
                                            setSupplementFile(
                                                e
                                                    .target
                                                    .files?.[0] ??
                                                null,
                                            )
                                        }
                                    />

                                    {supplementFile && (
                                        <small>
                                            {
                                                supplementFile.name
                                            }
                                        </small>
                                    )}
                                </label>
                            )}
                        </section>
                    )}

                    {/* =========================
                        오류
                    ========================= */}

                    {submitError && (
                        <div className="notice error report-error">
                            {submitError}
                        </div>
                    )}
                </div>

                {/* =========================
                    하단 버튼
                ========================= */}

                <div className="drawer-footer">
                    <button
                        type="button"
                        className="cancel-button"
                        disabled={
                            submitting
                        }
                        onClick={
                            requestClose
                        }
                    >
                        취소
                    </button>

                    <button
                        type="button"
                        className="primary-button"
                        disabled={
                            submitting
                        }
                        onClick={submit}
                    >
                        {submitting
                            ? '등록 중...'
                            : '신고하기'}
                    </button>
                </div>
            </aside>
        </>
    )
}