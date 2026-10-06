type Menu = 'home' | 'favorites' | 'knowledge' | 'settings'

type Props = {
    current: Menu
    onChange: (menu: Menu) => void
}

export default function Sidebar({ current, onChange }: Props) {
    return (
        <aside className="sidebar">
            <div className="brand">
                <strong>문제풀다</strong>
                <span>찍기만 하면, 해설까지.</span>
            </div>

            <nav className="sidebar-nav">
                <button
                    className={current === 'home' ? 'active' : ''}
                    onClick={() => onChange('home')}
                >
                    홈
                </button>

                <button
                    className={current === 'favorites' ? 'active' : ''}
                    onClick={() => onChange('favorites')}
                >
                    즐겨찾기
                </button>

                <button
                    className={current === 'knowledge' ? 'active' : ''}
                    onClick={() => onChange('knowledge')}
                >
                    자료 관리
                </button>

                <button
                    className={current === 'settings' ? 'active' : ''}
                    onClick={() => onChange('settings')}
                >
                    설정
                </button>
            </nav>
        </aside>
    )
}

export type { Menu }