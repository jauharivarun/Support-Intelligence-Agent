import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, setAuthToken } from './api'

export type User = {
  id: number
  email: string
  name: string
  role: 'CUSTOMER' | 'INTERNAL_SUPPORT' | 'ADMIN'
  account_code: string | null
}

type AuthState = {
  token: string | null
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('pp_token'))
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setAuthToken(token)
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    api
      .get<User>('/api/auth/me/')
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem('pp_token')
        setToken(null)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [token])

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post<{ access: string; user: User }>('/api/auth/login/', {
      email,
      password,
    })
    localStorage.setItem('pp_token', data.access)
    setAuthToken(data.access)
    setToken(data.access)
    setUser(data.user)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('pp_token')
    setToken(null)
    setUser(null)
    setAuthToken(null)
  }, [])

  const value = useMemo(
    () => ({ token, user, loading, login, logout }),
    [token, user, loading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside provider')
  return ctx
}
