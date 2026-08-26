import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'

type Doc = {
  id: number
  name: string
  source_type: string
  status: string
  authority_level: number
  scope_type: string
  account_code: string | null
  chunk_count: number
  original_filename: string
}

export default function AdminDocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    name: '',
    source_type: 'POLICY_SOP',
    status: 'CURRENT',
    authority_level: '80',
    scope_type: 'GENERAL',
    account_code: '',
    effective_date: '',
    expiry_date: '',
    explicit_override_domains: '',
  })
  const [file, setFile] = useState<File | null>(null)

  async function load() {
    const data = await api.get<Doc[]>('/api/documents/')
    setDocs(data)
  }

  useEffect(() => {
    load().catch((e) => setError(e.message))
  }, [])

  async function onUpload(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const body = new FormData()
      body.append('file', file)
      Object.entries(form).forEach(([k, v]) => {
        if (v) body.append(k, v)
      })
      await api.post('/api/documents/upload/', body)
      setFile(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="docs-page">
      <header className="intel-header">
        <h1>Document administration</h1>
        <p>Upload, update, or delete sources with authority metadata. Only admins can change the knowledge base; the agent reads these files through RAG tools.</p>
      </header>
      <form className="upload-form" onSubmit={onUpload}>
        <label>
          File
          <input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
        <label>
          Name
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </label>
        <label>
          Source type
          <select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
            <option value="CUSTOMER_AGREEMENT">Customer Agreement</option>
            <option value="POLICY_SOP">Policy / SOP</option>
            <option value="PRODUCT_DOC">Product Documentation</option>
            <option value="HISTORICAL_CONTEXT">Historical Context</option>
            <option value="DEPRECATED">Deprecated</option>
          </select>
        </label>
        <label>
          Status
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            <option value="ACTIVE">ACTIVE</option>
            <option value="CURRENT">CURRENT</option>
            <option value="DEPRECATED">DEPRECATED</option>
            <option value="CONTEXT_ONLY">CONTEXT_ONLY</option>
          </select>
        </label>
        <label>
          Authority level
          <input
            value={form.authority_level}
            onChange={(e) => setForm({ ...form, authority_level: e.target.value })}
            required
          />
        </label>
        <label>
          Scope
          <select value={form.scope_type} onChange={(e) => setForm({ ...form, scope_type: e.target.value })}>
            <option value="GENERAL">GENERAL</option>
            <option value="CUSTOMER_SPECIFIC">CUSTOMER_SPECIFIC</option>
            <option value="PRODUCT">PRODUCT</option>
          </select>
        </label>
        <label>
          Account code (optional)
          <input
            value={form.account_code}
            onChange={(e) => setForm({ ...form, account_code: e.target.value })}
            placeholder="ACCT-001"
          />
        </label>
        <label>
          Effective date
          <input
            type="date"
            value={form.effective_date}
            onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
          />
        </label>
        <label>
          Expiry date
          <input
            type="date"
            value={form.expiry_date}
            onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
          />
        </label>
        <label>
          Explicit override domains
          <input
            value={form.explicit_override_domains}
            onChange={(e) => setForm({ ...form, explicit_override_domains: e.target.value })}
            placeholder="CANCELLATION,SLA"
          />
        </label>
        <button type="submit" disabled={busy || !file || !form.name}>
          {busy ? 'Uploading…' : 'Upload & ingest'}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <table className="docs-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Status</th>
            <th>Auth</th>
            <th>Account</th>
            <th>Chunks</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td>{d.source_type}</td>
              <td>{d.status}</td>
              <td>{d.authority_level}</td>
              <td>{d.account_code || '—'}</td>
              <td>{d.chunk_count}</td>
              <td>
                <button
                  type="button"
                  className="ghost"
                  onClick={async () => {
                    if (!confirm(`Delete “${d.name}”? This removes it from the knowledge base.`)) return
                    setBusy(true)
                    setError('')
                    try {
                      await api.delete(`/api/documents/${d.id}/`)
                      await load()
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Delete failed')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
