import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import './layout.css'

export default function AppLayout() {
  const { user, logout } = useAuth()
  const internal = user?.role === 'INTERNAL_SUPPORT' || user?.role === 'ADMIN'
  const admin = user?.role === 'ADMIN'

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">PP</span>
          <div>
            <div className="brand-name">ParcelPilot</div>
            <div className="brand-sub">Support Intelligence</div>
          </div>
        </div>
        <div className="user-meta">
          <span>{user?.name || user?.email}</span>
          <span className="pill">{user?.role}</span>
          {user?.account_code && <span className="pill muted">{user.account_code}</span>}
          <button type="button" className="ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <div className="body">
        <aside className="sidebar">
          <nav>
            <NavLink to="/" end>
              Chat
            </NavLink>
            {internal && <NavLink to="/intelligence">Issue Intelligence</NavLink>}
            {admin && <NavLink to="/documents">Documents</NavLink>}
          </nav>
          <p className="sidebar-note">
            Answers are grounded in agreements, policies, and operational data. State changes require
            confirmation.
          </p>
        </aside>
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
