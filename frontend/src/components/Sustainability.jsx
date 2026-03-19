import { useState, useEffect } from 'react'
import { api } from '../api'

export default function Sustainability({ onLoad }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/sustainability')
      .then(d => { setData(d); onLoad?.() })
      .catch(e => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!data) return <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>Loading...</div>

  const color = data.overall_score >= 80 ? 'var(--ok)' : data.overall_score >= 60 ? 'var(--warn)' : 'var(--danger)'

  return (
    <div className="card" style={{ textAlign: 'center' }}>
      <h2>Sustainability Impact Score</h2>
      <div className="score-ring" style={{ border: `8px solid ${color}`, color }}>{data.overall_score}</div>
      <p style={{ fontSize: '1.5rem', fontWeight: 700 }}>Grade: {data.grade}</p>
      <div className="stats-row" style={{ marginTop: 20, justifyContent: 'center' }}>
        <div className="stat-card"><div className="num">{data.eco_certified_pct}%</div><div className="label">Eco-Certified</div></div>
        <div className="stat-card"><div className="num">{data.eco_certified_count}/{data.total_items}</div><div className="label">Eco Items</div></div>
        <div className="stat-card">
          <div className="num" style={{ color: data.waste_risk_items > 0 ? 'var(--danger)' : 'var(--ok)' }}>{data.waste_risk_items}</div>
          <div className="label">Waste Risk Items</div>
        </div>
        <div className="stat-card"><div className="num">{data.waste_management_score}</div><div className="label">Waste Score</div></div>
      </div>
    </div>
  )
}
