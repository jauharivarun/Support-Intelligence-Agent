import { useEffect, useState } from 'react'
import { api } from '../api'

type Dashboard = {
  sla_risks: Array<Record<string, unknown>>
  recurring_issues: Array<Record<string, unknown>>
  known_issue_correlations: Array<Record<string, unknown>>
  cross_customer_patterns: Array<Record<string, unknown>>
  source_conflicts: number
  action_failures: number
  reference_time: string
}

export default function IssueIntelligencePage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get<Dashboard>('/api/issue-intelligence/')
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (!data) return <p>Loading intelligence…</p>

  return (
    <div className="intel">
      <header className="intel-header">
        <h1>Issue Intelligence</h1>
        <p>Signals as of {data.reference_time}. Pattern detection is not proof of root cause.</p>
      </header>
      <div className="intel-grid">
        <section>
          <h2>SLA Risks</h2>
          {data.sla_risks.length === 0 && <p className="muted">None currently flagged.</p>}
          {data.sla_risks.map((r) => (
            <article key={String(r.ticket_id)} className="intel-item">
              <strong>
                {String(r.ticket_id)} · {String(r.severity)}
              </strong>
              <p>{String(r.subject)}</p>
              <p className="muted">
                {String(r.account_id)} · {String(r.hours_remaining)}h remaining · {String(r.sla_source)}
              </p>
            </article>
          ))}
        </section>
        <section>
          <h2>Recurring Issues</h2>
          {data.recurring_issues.map((r) => (
            <article key={String(r.theme)} className="intel-item">
              <strong>{String(r.theme)}</strong>
              <p>
                Count {String(r.count)} · {String(r.label)}
              </p>
            </article>
          ))}
        </section>
        <section>
          <h2>Known Issue Correlations</h2>
          {data.known_issue_correlations.map((r, i) => (
            <article key={i} className="intel-item">
              <strong>
                {String(r.known_issue_id)} ({String(r.known_issue_status)})
              </strong>
              <p>Tickets: {(r.tickets as string[]).join(', ')}</p>
              <p className="muted">{String(r.note)}</p>
            </article>
          ))}
        </section>
        <section>
          <h2>Cross-Customer Patterns</h2>
          {data.cross_customer_patterns.map((r) => (
            <article key={String(r.theme)} className="intel-item">
              <strong>{String(r.theme)}</strong>
              <p>{(r.accounts as string[]).join(', ')}</p>
            </article>
          ))}
        </section>
        <section>
          <h2>System Signals</h2>
          <article className="intel-item">
            <p>Source conflicts logged: {data.source_conflicts}</p>
            <p>Action failures: {data.action_failures}</p>
          </article>
        </section>
      </div>
    </div>
  )
}
