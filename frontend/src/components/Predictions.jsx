import { useState, useEffect } from 'react'
import { api } from '../api'

export default function Predictions() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/predictions').then(setData).catch(e => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!data) return <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>Loading predictions...</div>

  const sorted = [...data.predictions].sort((a, b) => {
    const order = { critical: 0, warning: 1, ok: 2, unknown: 3 }
    return (order[a.urgency] ?? 3) - (order[b.urgency] ?? 3)
  })

  return (
    <>
      <div className="stats-row">
        <div className="stat-card card"><div className="num">{data.predictions.length}</div><div className="label">Total Items</div></div>
        <div className="stat-card card"><div className="num" style={{ color: 'var(--danger)' }}>{data.critical_count}</div><div className="label">Critical</div></div>
        <div className="stat-card card"><div className="num" style={{ color: 'var(--warn)' }}>{data.warning_count}</div><div className="label">Warnings</div></div>
      </div>
      {sorted.map((p, i) => (
        <div key={i} className={`prediction-card ${p.urgency}`}>
          <strong>{p.item}</strong>{' '}
          <span className={`badge badge-${p.urgency}`}>{p.urgency}</span>{' '}
          <span className="badge" style={{ background: '#e8e8e8' }}>{p.method}</span>
          {p.model && <span className="badge" style={{ background: '#d0e8ff', marginLeft: 4 }}>{p.model}</span>}
          {p.trend && (
            <span className="badge" style={{
              background: p.trend === 'increasing' ? '#ffe0e0' : p.trend === 'decreasing' ? '#e0ffe0' : '#f0f0f0',
              marginLeft: 4
            }}>
              {p.trend === 'increasing' ? '↑' : p.trend === 'decreasing' ? '↓' : '→'}{' '}
              {p.trend_pct != null ? `${p.trend_pct > 0 ? '+' : ''}${p.trend_pct}%` : p.trend}
            </span>
          )}
          {p.confidence && (
            <span className="badge" style={{
              background: p.confidence === 'high' ? '#d4edda' : p.confidence === 'medium' ? '#fff3cd' : '#f8d7da',
              marginLeft: 4, fontSize: 11
            }}>
              {p.confidence} confidence
            </span>
          )}
          <p style={{ marginTop: 6 }}>{p.recommendation}</p>
          {p.seasonality && p.seasonality.detected && (
            <p style={{ color: '#7b2d8e', fontSize: 13 }}>{p.seasonality.description}</p>
          )}
          {p.expiry_warning && <p style={{ color: 'var(--warn)', fontSize: 13 }}>{p.expiry_warning}</p>}
          {p.sustainability_tip && <p style={{ color: 'var(--green)', fontSize: 13 }}>{p.sustainability_tip}</p>}
          {p.days_until_empty != null && (
            <small>
              Days left: {p.days_until_empty}{p.estimated_runout ? ` (runs out ~${p.estimated_runout})` : ''}
              {p.forecast_usage_rate != null && p.configured_usage_rate != null && (
                <span style={{ marginLeft: 8, color: '#888' }}>
                  Forecast: {p.forecast_usage_rate}/day | Configured: {p.configured_usage_rate}/day
                </span>
              )}
            </small>
          )}
        </div>
      ))}
    </>
  )
}
