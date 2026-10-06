import { useState } from 'react'

type Props = {
    open: boolean
    onClose: () => void
}

type UploadType = 'text' | 'image' | 'pdf'

export default function KnowledgeDrawer({
                                            open,
                                            onClose,
                                        }: Props) {
    const [type, setType] = useState<UploadType>('text')
    const [title, setTitle] = useState('')
    const [content, setContent] = useState('')
    const [file, setFile] = useState<File | null>(null)

    if (!open) return null

    const dirty =
        title.trim() !== '' ||
        content.trim() !== '' ||
        file !== null

    const reset = () => {
        setType('text')
        setTitle('')
        setContent('')
        setFile(null)
    }

    const requestClose = () => {
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

    const submit = () => {
        if (type === 'text' && !content.trim()) {
            alert('이론 내용을 입력해주세요.')
            return
        }

        if (
            (type === 'image' || type === 'pdf') &&
            !file
        ) {
            alert('파일을 선택해주세요.')
            return
        }

        /*
          TODO:
          백엔드 자료 등록 API 연결 예정.

          텍스트 → JSON
          이미지/PDF → FormData

          검토 승인 이후 임베딩하도록 백엔드와 연결.
        */

        console.log({
            type,
            title,
            content,
            file,
        })

        alert(
            '자료가 등록되었습니다.\n검토 후 지식 자료에 반영됩니다.',
        )

        reset()
        onClose()
    }

    return (
        <>
            <button
                type="button"
                className="drawer-backdrop"
                aria-label="자료 추가 닫기"
                onClick={requestClose}
            />

            <aside className="drawer">
                <div className="drawer-header">
                    <div>
                        <h2>관련 이론 추가</h2>
                        <p>
                            해설에 필요한 자료를 추가할 수 있습니다.
                        </p>
                    </div>

                    <button
                        type="button"
                        className="drawer-close"
                        onClick={requestClose}
                    >
                        ×
                    </button>
                </div>

                <div className="drawer-body">
                    <div className="knowledge-notice">
                        <strong>바로 학습 데이터에 반영되지 않습니다.</strong>
                        <span>
              등록된 자료는 검토 후 임베딩 자료에 반영됩니다.
            </span>
                    </div>

                    <div className="knowledge-tabs">
                        <button
                            type="button"
                            className={type === 'text' ? 'active' : ''}
                            onClick={() => {
                                setType('text')
                                setFile(null)
                            }}
                        >
                            텍스트
                        </button>

                        <button
                            type="button"
                            className={
                                type === 'image' ? 'active' : ''
                            }
                            onClick={() => {
                                setType('image')
                                setFile(null)
                            }}
                        >
                            이미지
                        </button>

                        <button
                            type="button"
                            className={type === 'pdf' ? 'active' : ''}
                            onClick={() => {
                                setType('pdf')
                                setFile(null)
                            }}
                        >
                            PDF
                        </button>
                    </div>

                    <label className="knowledge-field">
                        <span>자료 제목</span>

                        <input
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="자료 제목을 입력해주세요."
                        />
                    </label>

                    {type === 'text' && (
                        <label className="knowledge-field">
                            <span>이론 내용</span>

                            <textarea
                                value={content}
                                onChange={(e) => setContent(e.target.value)}
                                placeholder="추가할 개념이나 이론을 입력해주세요."
                            />
                        </label>
                    )}

                    {type === 'image' && (
                        <label className="knowledge-file-box">
                            <strong>이미지 추가</strong>

                            <span>
                JPG, PNG 파일을 선택해주세요.
              </span>

                            <input
                                type="file"
                                accept="image/png,image/jpeg"
                                onChange={(e) =>
                                    setFile(e.target.files?.[0] ?? null)
                                }
                            />

                            {file && (
                                <small>선택됨: {file.name}</small>
                            )}
                        </label>
                    )}

                    {type === 'pdf' && (
                        <label className="knowledge-file-box">
                            <strong>PDF 추가</strong>

                            <span>
                이론이 포함된 PDF를 선택해주세요.
              </span>

                            <input
                                type="file"
                                accept="application/pdf"
                                onChange={(e) =>
                                    setFile(e.target.files?.[0] ?? null)
                                }
                            />

                            {file && (
                                <small>선택됨: {file.name}</small>
                            )}
                        </label>
                    )}
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
                        자료 등록
                    </button>
                </div>
            </aside>
        </>
    )
}