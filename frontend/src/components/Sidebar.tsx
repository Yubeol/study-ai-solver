type Menu =
  | 'home'
  | 'history'
  | 'favorites'
  | 'knowledge'
  | 'settings'

type Props = {
  current: Menu
  onChange: (
    menu: Menu,
  ) => void
}

export default function Sidebar({
  current,
  onChange,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <strong>
          문제풀다
        </strong>

        <span>
          찍기만 하면, 해설까지.
        </span>
      </div>

      <nav className="sidebar-menu">
        <button
          type="button"
          className={
            current === 'home'
              ? 'sidebar-menu-item active'
              : 'sidebar-menu-item'
          }
          onClick={() =>
            onChange('home')
          }
        >
          문제 풀기
        </button>

        <button
          type="button"
          className={
            current === 'history'
              ? 'sidebar-menu-item active'
              : 'sidebar-menu-item'
          }
          onClick={() =>
            onChange('history')
          }
        >
          히스토리
        </button>

        <button
          type="button"
          className={
            current === 'favorites'
              ? 'sidebar-menu-item active'
              : 'sidebar-menu-item'
          }
          onClick={() =>
            onChange('favorites')
          }
        >
          즐겨찾기
        </button>

        <button
          type="button"
          className={
            current === 'knowledge'
              ? 'sidebar-menu-item active'
              : 'sidebar-menu-item'
          }
          onClick={() =>
            onChange('knowledge')
          }
        >
          자료 관리
        </button>

        <button
          type="button"
          className={
            current === 'settings'
              ? 'sidebar-menu-item active'
              : 'sidebar-menu-item'
          }
          onClick={() =>
            onChange('settings')
          }
        >
          설정
        </button>
      </nav>
    </aside>
  )
}

export type {
  Menu,
}