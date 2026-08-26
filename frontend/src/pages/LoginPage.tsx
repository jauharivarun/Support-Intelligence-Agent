import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'

type DemoUser = { label: string; email: string; password: string; role: string }

export default function LoginPage() {
  const { login, token } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('northstar@demo.local')
  const [password, setPassword] = useState('demo1234')
  const [error, setError] = useState('')
  const [demos, setDemos] = useState<DemoUser[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (token) navigate('/', { replace: true })
  }, [token, navigate])

  useEffect(() => {
    api.get<DemoUser[]>('/api/auth/demo-users/').then(setDemos).catch(() => undefined)
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-panel">
        <p className="eyebrow">ParcelPilot</p>
        <h1>Support Intelligence</h1>
        <p className="lede">Sign in to ask grounded questions about orders, policies, and agreements.</p>
        <form onSubmit={onSubmit} className="login-form">
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <div className="demo-grid">
          {demos.map((d) => (
            <button
              key={d.email}
              type="button"
              className="demo-card"
              onClick={() => {
                setEmail(d.email)
                setPassword(d.password)
              }}
            >
              <strong>{d.label}</strong>
              <span>{d.role}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="login-visual" aria-hidden />
    </div>
  )
}
