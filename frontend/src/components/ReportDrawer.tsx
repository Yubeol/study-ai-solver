import { useState } from 'react'

type Props = {
    open: boolean
    question: string
    onClose: () => void
}

type ReportType =
    | 'wrong_answer'
    | 'wrong_explanation'
    | 'wrong_concept'
    | 'wrong_ocr'
    | 'insufficient'
    | 'other'

const REPORTS: {
    value: ReportType
    title: string
    description: string
}[] = [
    {
        value: 'wrong_answer',
        title: '답이 틀렸어요',
        description: '선택된 정답이 실제 정답과 다른 것 같아요.',
    },
    {
        value: 'wrong_explanation',
        title: '해설이 틀렸어요',
        description: '정답은 맞지만 풀이 과정이나 설명에 오류가 있어요.',
    },
    {
        value: 'wrong_concept',
        title: '개념이나 근거가 이상해요',
        description: '사용한 개념이나 교재 근거가 적절하지 않은 것 같아요.',
    },
    {
        value: 'wrong_ocr',
        title: '문제를 잘못 읽었어요',
        description: '문제나 선지를 잘못 인식했어요.',
    },
    {
        value: 'insufficient',
        title: '설명이 부족해요',
        description: '관련 개념이나 설명이 조금 더 필요해요.',
    },
    {
        value: 'other',
        title: '기타',
        description: '위 항목에 해당하지 않는 문제가 있어요.',
    },
]

export default function ReportDrawer({
                                         open,
                                         question,
                                         onClose,
                                     }: Props) {
    const [type, setType] = useState<ReportType | null>(null)

    const [detail, setDetail] = useState('')

    const [conceptDetails, setConceptDetails] = useState<
        string[]
    >([])

    if (!open) return null

    const dirty =
        type !== null ||
        detail.trim().length > 0 ||
        conceptDetails.length > 0

    const requestClose = () => {
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

    const reset = () => {
        setType(null)
        setDetail('')
        setConceptDetails([])
    }

    const toggleConceptDetail = (value: string) => {
        setConceptDetails((current) =>
            current.includes(value)
                ? current.filter((v) => v !== value)
                : [...current, value],
        )
    }

    const submit = () => {
        if (!type) {
            alert('오류 유형을 선택해주세요.')
            return
        }

        /*
          TODO:
          백엔드 feedback API가 생기면
          이 payload를 POST로 보내면 됨.
        */

        const payload = {
            question,
            type,
            concept_details: conceptDetails,
            detail,
        }

        console.log('feedback:', payload)

        alert('오류 신고가 접수되었습니다.')

        reset()
        onClose()
    }

    return (
        <>
            <button
                type="button"
                aria-label="오류 신고 닫기"
                className="drawer-backdrop"
                onClick={requestClose}
            />

            <aside className="drawer">
                <div className="drawer-header">
                    <div>
                        <h2>오류 신고하기</h2>
                        <p>어떤 부분이 잘못되었는지 알려주세요.</p>
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
                    <div className="report-list">
                        {REPORTS.map((item) => (
                            <label
                                key={item.value}
                                className={
                                    type === item.value
                                        ? 'report-card selected'
                                        : 'report-card'
                                }
                            >
                                <input
                                    type="radio"
                                    name="report-type"
                                    checked={type === item.value}
                                    onChange={() => setType(item.value)}
                                />

                                <span>
                  <strong>{item.title}</strong>
                  <small>{item.description}</small>
                </span>
                            </label>
                        ))}
                    </div>

                    {type === 'wrong_concept' && (
                        <div className="concept-detail-box">
                            <strong>어떤 문제가 있었나요?</strong>

                            {[
                                '관련 개념이 빠져 있어요',
                                '다른 개념을 사용했어요',
                                '공식이나 정의가 잘못됐어요',
                                '교재 근거가 적절하지 않아요',
                            ].map((item) => (
                                <label key={item}>
                                    <input
                                        type="checkbox"
                                        checked={conceptDetails.includes(item)}
                                        onChange={() =>
                                            toggleConceptDetail(item)
                                        }
                                    />

                                    {item}
                                </label>
                            ))}
                        </div>
                    )}

                    <label className="detail-input">
            <span>
              상세 내용 <small>선택</small>
            </span>

                        <textarea
                            value={detail}
                            maxLength={500}
                            onChange={(e) => setDetail(e.target.value)}
                            placeholder="어떤 부분이 이상했는지 알려주세요."
                        />

                        <small>{detail.length}/500</small>
                    </label>
                </div>

                <div className="drawer-footer">
                    <button
                        type="button"
                        className="cancel-button"
                        onClick={requestClose}
                    >
                        취소
                    </button>

                    <button
                        type="button"
                        className="primary-button"
                        onClick={submit}
                    >
                        신고하기
                    </button>
                </div>
            </aside>
        </>
    )
}