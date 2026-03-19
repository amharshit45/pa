import { useState } from 'react'
import { api } from '../api'

function DeltaDisplay({ value, invert }) {
  if (value === 0) return <span className="delta-neutral">No change</span>
  const better = invert ? value > 0 : value < 0
  const cls = better ? 'delta-positive' : 'delta-negative'
  const sign = value > 0 ? '+' : ''
  const display = Number.isInteger(value) ? value : value.toFixed(2)
  return <span className={cls}>{sign}{display}</span>
}

export default function WhatIf({ items }) {
  const [action, setAction] = useState('reduce_usage')
  const [itemId, setItemId] = useState(items[0]?.id || '')
  const [pct, setPct] = useState(20)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const showItem = action !== 'all_eco'
  const showPct = action !== 'switch_eco' && action !== 'all_eco'

  const run = async () => {
    setError('')
    const body = { action, reduce_pct: pct }
    if (showItem) body.item_id = parseInt(itemId)
    try {
      const r = await api('/what-if', { method: 'POST', body: JSON.stringify(body) })
      setResult(r)
    } catch (e) { setError(e.message); setResult(null) }
  }

  return (
    <div className="card">
      <h2>What-If Scenario Simulator</h2>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>
        Model procurement changes and see the impact on waste, cost, and carbon footprint.
      </p>
      <div className="form-row">
        <div className="form-group">
          <label>Scenario</label>
          <select value={action} onChange={e => setAction(e.target.value)}>
            <option value="reduce_usage">Reduce item usage</option>
            <option value="reduce_order">Reduce order quantity</option>
            <option value="switch_eco">Switch to eco-certified supplier</option>
            <option value="all_eco">Switch ALL items to eco-certified</option>
          </select>
        </div>
        {showItem && (
          <div className="form-group">
            <label>Item</label>
            <select value={itemId} onChange={e => setItemId(e.target.value)}>
              {items.map(i => <option key={i.id} value={i.id}>{i.name} ({i.quantity} {i.unit})</option>)}
            </select>
          </div>
        )}
        {showPct && (
          <div className="form-group">
            <label>Reduction %</label>
            <input type="number" value={pct} onChange={e => setPct(e.target.value)} min={1} max={100} />
          </div>
        )}
      </div>
      <button className="btn-primary" onClick={run}>Run Simulation</button>
      {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
      {result && !result.error && (
        <div className="card" style={{ marginTop: 16, borderLeft: '4px solid var(--green)' }}>
          <h3 style={{ marginBottom: 12 }}>Scenario: {result.scenario}</h3>
          <div className="comparison-grid">
            <div className="metric">
              <div className="label">Weekly Waste Cost</div>
              <div className="value">${result.projected.estimated_weekly_waste_cost}</div>
              <div className="delta"><DeltaDisplay value={result.delta.waste_cost_change} /></div>
            </div>
            <div className="metric">
              <div className="label">Eco-Certified %</div>
              <div className="value">{result.projected.eco_pct}%</div>
              <div className="delta"><DeltaDisplay value={result.delta.eco_pct_change} invert />%</div>
            </div>
            <div className="metric">
              <div className="label">Carbon Score</div>
              <div className="value">{result.projected.carbon_score}/100</div>
              <div className="delta"><DeltaDisplay value={result.delta.carbon_score_change} invert /></div>
            </div>
          </div>
          <div className="comparison-grid" style={{ marginTop: 8 }}>
            <div className="metric">
              <div className="label">Weekly Procurement</div>
              <div className="value">${result.projected.weekly_procurement_cost}</div>
              <div className="delta"><DeltaDisplay value={result.delta.weekly_cost_change} /></div>
            </div>
            <div className="metric">
              <div className="label">Waste Risk Items</div>
              <div className="value">{result.projected.waste_risk_items.length}</div>
            </div>
            <div className="metric">
              <div className="label">Baseline Carbon</div>
              <div className="value">{result.baseline.carbon_score}/100</div>
              <div className="delta" style={{ color: '#888' }}>before change</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
