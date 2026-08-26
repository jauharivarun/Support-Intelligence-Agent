const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

let authToken: string | null = localStorage.getItem('pp_token')

export function setAuthToken(token: string | null) {
  authToken = token
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`)

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
    }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: JSON.stringify(body ?? {}),
    }),
  delete: <T,>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export { API_BASE }
