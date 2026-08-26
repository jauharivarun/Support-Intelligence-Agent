import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { api } from '../api'

type Session = { id: number; title: string; updated_at: string }
type Message = {
  id?: number
  role: string
  content: string
  metadata?: {
    decision_status?: string
    sources?: { name?: string }[]
    tool_activity?: string[]
    pending_action?: PendingAction | null
  }
}
type PendingAction = {
  pending_action_id: number
  action_type: string
  reason?: string
  payload?: Record<string, unknown>
  status: string
  expires_at?: string
  requires_confirmation?: boolean
  message?: string
}

function prepareMarkdown(content: string): string {
  let text = (content || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  text = text.replace(/(#{1,6})(?=[A-Za-z])/g, '$1 ')
  text = text.replace(/([^#\n])(#{1,6}\s)/g, '$1\n$2')
  return text
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (/^#{2,}$/.test(trimmed)) return ''
      const heading = trimmed.match(/^(#{1,6})\s*(.*)$/)
      if (heading) {
        const rest = heading[2].replace(/#+$/g, '').trim()
        return rest ? `${heading[1]} ${rest}` : ''
      }
      return line
    })
    .join('\n')
}

function normalizeBrokenLines(content: string): string {
  const prepared = prepareMarkdown(content)
  const rawLines = prepared.split('\n')
  const lines = rawLines.map((l) => l.trim()).filter(Boolean)
  if (lines.length <= 2) return prepared
  const markdown = lines.some((l) => /^#{1,6}\s/.test(l) || /^\*\*/.test(l) || /^[-*]\s/.test(l) || /^\d+\.\s/.test(l))
  if (markdown) return prepared
  const singleWord = lines.filter((l) => !l.startsWith('-') && l.split(/\s+/).length === 1).length
  if (singleWord / lines.length > 0.55) {
    return lines.join(' ')
  }
  return prepared
}

function renderInline(text: string): ReactNode[] {
  const parts: ReactNode[] = []
  const re = /\*\*(.+?)\*\*|\*(.+?)\*/g
  let last = 0
  let match: RegExpExecArray | null
  let key = 0
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index))
    }
    parts.push(<strong key={`b-${key++}`}>{match[1] || match[2]}</strong>)
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

function MessageBody({ content }: { content: string }) {
  const normalized = normalizeBrokenLines(content)
  const lines = normalized.split('\n')
  const blocks: ReactNode[] = []
  let listItems: string[] = []

  function flushList() {
    if (listItems.length === 0) return
    blocks.push(
      <ul key={`list-${blocks.length}`}>
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>,
    )
    listItems = []
  }

  for (const line of lines) {
    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      flushList()
      const level = Math.min(heading[1].length, 3)
      const Tag = (level === 1 ? 'h3' : level === 2 ? 'h4' : 'h5') as 'h3' | 'h4' | 'h5'
      blocks.push(
        <Tag key={`h-${blocks.length}`} className="bubble-heading">
          {renderInline(heading[2])}
        </Tag>,
      )
      continue
    }
    const numbered = line.match(/^\d+[.)]\s+(.*)$/)
    if (numbered) {
      listItems.push(numbered[1])
      continue
    }
    const bullet = line.match(/^[-•*]\s+(.*)$/)
    if (bullet) {
      listItems.push(bullet[1])
      continue
    }
    flushList()
    if (line.trim()) {
      blocks.push(
        <p key={`p-${blocks.length}`} className="bubble-paragraph">
          {renderInline(line)}
        </p>,
      )
    } else if (blocks.length > 0) {
      blocks.push(<div key={`sp-${blocks.length}`} className="bubble-spacer" />)
    }
  }
  flushList()

  return <div className="bubble-body formatted">{blocks}</div>
}

function IconPencil() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 20h4.2L19.3 8.9a1.5 1.5 0 0 0 0-2.1L17.2 4.7a1.5 1.5 0 0 0-2.1 0L4 15.8V20Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M13.5 6.5 17.5 10.5" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 7h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M10 4h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M6.5 7 8 20h8l1.5-13"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M10 11v5M14 11v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function shouldShowDecisionStatus(status?: string) {
  if (!status) return false
  return status !== 'RESOLVED'
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  async function loadSessions() {
    const data = await api.get<Session[]>('/api/agent/sessions/')
    setSessions(data)
  }

  useEffect(() => {
    loadSessions().catch(() => undefined)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  async function openSession(id: number) {
    const data = await api.get<{ id: number; messages?: Message[] }>(`/api/agent/sessions/${id}/`)
    const loaded = Array.isArray(data.messages) ? data.messages : []
    setSessionId(data.id)
    setMessages(loaded)
    const last = [...loaded].reverse().find((m) => m.metadata?.pending_action)
    setPending(last?.metadata?.pending_action || null)
  }

  async function onSend(e: FormEvent) {
    e.preventDefault()
    if (!input.trim() || busy) return
    const text = input.trim()
    setInput('')
    setBusy(true)
    setError('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    try {
      const result = await api.post<{
        session_id: number
        answer: string
        decision_status: string
        sources: { name?: string }[]
        tool_activity: string[]
        pending_action: PendingAction | null
      }>('/api/agent/chat/', { message: text, session_id: sessionId })
      setSessionId(result.session_id)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: result.answer,
          metadata: {
            decision_status: result.decision_status,
            sources: result.sources,
            tool_activity: result.tool_activity,
            pending_action: result.pending_action,
          },
        },
      ])
      setPending(result.pending_action)
      await loadSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  async function confirmAction(id: number) {
    await api.post(`/api/actions/${id}/confirm/`)
    setPending(null)
    setMessages((m) => [
      ...m,
      { role: 'assistant', content: 'Action confirmed and executed. An audit log entry was created.' },
    ])
  }

  async function cancelAction(id: number) {
    await api.post(`/api/actions/${id}/cancel/`)
    setPending(null)
    setMessages((m) => [...m, { role: 'assistant', content: 'Pending action cancelled. Nothing was executed.' }])
  }

  async function saveRename(id: number) {
    const title = renameDraft.trim()
    if (!title) return
    await api.patch(`/api/agent/sessions/${id}/`, { title })
    setRenamingId(null)
    await loadSessions()
  }

  async function deleteSession(id: number) {
    if (!window.confirm('Delete this chat? This cannot be undone.')) return
    await api.delete(`/api/agent/sessions/${id}/`)
    if (sessionId === id) {
      setSessionId(null)
      setMessages([])
      setPending(null)
    }
    await loadSessions()
  }

  return (
    <div className="chat-layout">
      <div className="session-list">
        <button
          type="button"
          className="primary-sm"
          onClick={() => {
            setSessionId(null)
            setMessages([])
            setPending(null)
          }}
        >
          New chat
        </button>
        {sessions.map((s) => (
          <div key={s.id} className={sessionId === s.id ? 'session-row active' : 'session-row'}>
            {renamingId === s.id ? (
              <input
                className="session-rename"
                value={renameDraft}
                autoFocus
                onChange={(e) => setRenameDraft(e.target.value)}
                onBlur={() => saveRename(s.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void saveRename(s.id)
                  }
                  if (e.key === 'Escape') setRenamingId(null)
                }}
                aria-label="Chat title"
              />
            ) : (
              <button
                type="button"
                className={sessionId === s.id ? 'session active' : 'session'}
                onClick={() => openSession(s.id)}
              >
                {s.title || `Session ${s.id}`}
              </button>
            )}
            <button
              type="button"
              className="session-action"
              title="Rename chat"
              aria-label="Rename chat"
              onClick={() => {
                setRenamingId(s.id)
                setRenameDraft(s.title || '')
              }}
            >
              <IconPencil />
            </button>
            <button
              type="button"
              className="session-action"
              title="Delete chat"
              aria-label="Delete chat"
              onClick={() => void deleteSession(s.id)}
            >
              <IconTrash />
            </button>
          </div>
        ))}
      </div>
      <div className="chat-pane">
        <div className="messages">
          {messages.length === 0 && (
            <div className="empty">
              <h2>Ask about orders, policies, or agreements</h2>
              <p>Not sure where to start? Ask: “What can you show me?”</p>
              <p>Or try: “Can ORD-1001 be cancelled without a fee?”</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              <MessageBody content={m.content} />
              {Array.isArray(m.metadata?.sources) && m.metadata.sources.length > 0 && (
                <div className="meta-row">
                  <span className="meta-label">Sources</span>
                  {m.metadata.sources.map((s, idx) => (
                    <span key={idx} className="source">
                      {s.name}
                    </span>
                  ))}
                </div>
              )}
              {Array.isArray(m.metadata?.tool_activity) && m.metadata.tool_activity.length > 0 && (
                <div className="meta-row">
                  {m.metadata.tool_activity.map((t, idx) => (
                    <span key={idx} className="chip">
                      {t}
                    </span>
                  ))}
                </div>
              )}
              {shouldShowDecisionStatus(m.metadata?.decision_status) && (
                <div className="meta-row">
                  <span className={`status ${m.metadata?.decision_status}`}>{m.metadata?.decision_status}</span>
                </div>
              )}
            </div>
          ))}
          {busy && (
            <div className="bubble assistant dim">
              Retrieving knowledge and writing an answer…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {pending?.requires_confirmation && pending.pending_action_id && (
          <div className="action-card">
            <h3>Confirm action</h3>
            <p>
              <strong>{pending.action_type}</strong> — {pending.reason || pending.message}
            </p>
            <pre>{JSON.stringify(pending.payload, null, 2)}</pre>
            <div className="action-actions">
              <button type="button" className="ghost" onClick={() => cancelAction(pending.pending_action_id)}>
                Cancel
              </button>
              <button type="button" onClick={() => confirmAction(pending.pending_action_id)}>
                Confirm
              </button>
            </div>
          </div>
        )}

        {error && <p className="error">{error}</p>}
        <form className="composer" onSubmit={onSend}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question…"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
