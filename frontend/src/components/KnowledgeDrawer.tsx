import {
    useState,
} from 'react'

import {
    createSupplement,
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

export default function KnowledgeDrawer({
                                            open,
                                            result,
                                            onClose,
                                        }: Props) {
    const [
        type,
        setType,
    ] = useState<SupplementType>('text')

    const [
        title,
        setTitle,
    ] = useState('')

    const [
        content,
        setContent,
    ] = useState('')

    const [
        file,
        setFile,
    ] = useState<File | null>(null)

    const [
        submitting,
        setSubmitting,
    ] = useState(false)

    const [
        error,
        setError,
    ] = useState<string | null>(null)

    if (!open) {
        return null
    }

    const dirty =
        title.trim() !== '' ||
        content.trim() !== '' ||
        file !== null

    const reset = () => {
        setType('text')

        setTitle('')

        setContent('')

        setFile(null)

        setError(null)
    }

    const requestClose = () => {
        if (submitting) {
            return
        }

        if (
            dirty &&
            !window.confirm(
                '작성 중인 자료가 있습니다.\n등록을 취소할까요?',
            )
        ) {
            return
        }

        reset()

        onClose()
    }

    const changeType = (
        next: SupplementType,
    ) => {
        setType(next)

        setFile(null)

        setError(null)
    }

    const submit = async () => {
        if (!result) {
            setError(
                '문제 정보를 찾을 수 없습니다.',
            )

            return
        }

        if (
            type === 'text' &&
            !content.trim()
        ) {
            setError(
                '보충 이론 내용을 입력해주세요.',
            )

            return
        }

        if (
            type !== 'text' &&
            !file
        ) {
            setError(
                '파일을 선택해주세요.',
            )

            return
        }

        setSubmitting(true)

        setError(null)

        try {
            await createSupplement({
                source: 'unanswerable',

                queryLogId:
                result.query_log_id,

                title,

                text:
                    type === 'text'
                        ? content
                        : undefined,

                file:
                    type === 'text'
                        ? null
                        : file,
            })

            alert(
                '보충 이론이 등록되었습니다.\n검토 후 반영됩니다.',
            )

            reset()

            onClose()
        } catch (e) {
            setError(
                e instanceof Error
                    ? e.message
                    : '자료 등록에 실패했습니다.',
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
                aria-label="이론 보충 닫기"
                onClick={requestClose}
            />

            <aside className="drawer">
                <div className="drawer-header">
                    <div>
                        <h2>
                            이론 보충
                        </h2>

                        <p>
                            이 문제에 필요한 자료를 추가할 수 있습니다.
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
                    <div className="knowledge-notice">
                        <strong>
                            검토 후 반영됩니다.
                        </strong>

                        <span>
              등록한 자료는 바로 임베딩되지 않습니다.
            </span>
                    </div>

                    <div className="knowledge-tabs">
                        <button
                            type="button"
                            className={
                                type === 'text'
                                    ? 'active'
                                    : ''
                            }
                            onClick={() =>
                                changeType('text')
                            }
                        >
                            텍스트
                        </button>

                        <button
                            type="button"
                            className={
                                type === 'image'
                                    ? 'active'
                                    : ''
                            }
                            onClick={() =>
                                changeType('image')
                            }
                        >
                            이미지
                        </button>

                        <button
                            type="button"
                            className={
                                type === 'pdf'
                                    ? 'active'
                                    : ''
                            }
                            onClick={() =>
                                changeType('pdf')
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
                            value={title}
                            onChange={(e) =>
                                setTitle(
                                    e.target.value,
                                )
                            }
                            placeholder="자료 제목을 입력해주세요."
                        />
                    </label>

                    {type === 'text' && (
                        <label className="knowledge-field">
              <span>
                이론 내용
              </span>

                            <textarea
                                value={content}
                                onChange={(e) =>
                                    setContent(
                                        e.target.value,
                                    )
                                }
                                placeholder="추가할 이론이나 개념을 입력해주세요."
                            />
                        </label>
                    )}

                    {type === 'image' && (
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
                                    setFile(
                                        e.target.files?.[0] ??
                                        null,
                                    )
                                }
                            />

                            {file && (
                                <small>
                                    {file.name}
                                </small>
                            )}
                        </label>
                    )}

                    {type === 'pdf' && (
                        <label className="knowledge-file-box">
                            <strong>
                                PDF 선택
                            </strong>

                            <span>
                PDF 자료를 선택해주세요.
              </span>

                            <input
                                type="file"
                                accept="application/pdf"
                                onChange={(e) =>
                                    setFile(
                                        e.target.files?.[0] ??
                                        null,
                                    )
                                }
                            />

                            {file && (
                                <small>
                                    {file.name}
                                </small>
                            )}
                        </label>
                    )}

                    {error && (
                        <div className="notice error">
                            {error}
                        </div>
                    )}
                </div>

                <div className="drawer-footer">
                    <button
                        type="button"
                        className="cancel-button"
                        disabled={submitting}
                        onClick={requestClose}
                    >
                        취소
                    </button>

                    <button
                        type="button"
                        className="primary-button"
                        disabled={submitting}
                        onClick={submit}
                    >
                        {submitting
                            ? '등록 중...'
                            : '등록하기'}
                    </button>
                </div>
            </aside>
        </>
    )
}