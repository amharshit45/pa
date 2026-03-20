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
      {data.alternatives_available?.length > 0 && (
        <div style={{ marginTop: 24, textAlign: 'left' }}>
          <h3>Sustainable Alternatives Available</h3>
          {data.alternatives_available.map((item, i) => (
            <div key={i} style={{ marginTop: 8, padding: '12px 16px', borderLeft: '4px solid var(--ok)', background: '#f8fdf8', borderRadius: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span><strong>{item.item_name}</strong> <span style={{ color: '#888' }}>(current: ${item.current_cost}/unit)</span></span>
                {item.score_improvement > 0 && (
                  <span style={{ background: '#d4edda', color: '#155724', padding: '2px 10px', borderRadius: 12, fontSize: 13, fontWeight: 600 }}>
                    Score: {data.overall_score} → {item.projected_score} (+{item.score_improvement})
                  </span>
                )}
              </div>
              {item.alternatives.map((alt, j) => (
                <div key={j} style={{ margin: '8px 0 0 12px', fontSize: 13 }}>
                  <span style={{ fontWeight: 600 }}>{alt.alternative_name}</span> — {alt.supplier}
                  <br />
                  ${alt.estimated_cost_per_unit}/unit |{' '}
                  <span style={{ color: 'var(--ok)' }}>-{alt.carbon_footprint_reduction_pct}% carbon</span>
                  {alt.eco_certifications?.length > 0 && (
                    <span style={{ marginLeft: 8 }}>
                      {alt.eco_certifications.map(c => (
                        <span key={c} className="badge" style={{ background: '#d4edda', marginLeft: 4, fontSize: 11 }}>{c}</span>
                      ))}
                    </span>
                  )}
                  {alt.notes && <p style={{ color: '#666', margin: '2px 0 0' }}>{alt.notes}</p>}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
