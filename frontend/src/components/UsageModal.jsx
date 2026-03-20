import { useState, useEffect } from 'react'
import { api } from '../api'

export default function UsageModal({ item, onClose, onSaved }) {
  const [qty, setQty] = useState('')
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api(`/items/${item.id}/usage`).then(setHistory).catch(() => {})
  }, [item.id])

  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const val = parseFloat(qty)
    if (isNaN(val) || val <= 0) { setError('Quantity must be greater than 0'); return }
    if (val > item.quantity) { setError(`Cannot exceed current stock (${item.quantity} ${item.unit})`); return }
    setLoading(true)
    try {
      await api(`/items/${item.id}/usage`, { method: 'POST', body: JSON.stringify({ quantity_used: val }) })
      setLoading(false)
      onSaved()
    } catch (e) { setError(e.message); setLoading(false) }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <h2>Log Usage</h2>
        <p style={{ margin: '0 0 16px', color: '#555' }}>
          <strong>{item.name}</strong> — {item.quantity} {item.unit} in stock
        </p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Quantity Used ({item.unit})</label>
            <input
              type="number"
              value={qty}
              onChange={e => { setQty(e.target.value); setError('') }}
              min="0.01"
              max={item.quantity}
              step="any"
              autoFocus
            />
          </div>
          {error && <div className="error">{error}</div>}
          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Logging...' : 'Log Usage'}
            </button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>
        </form>

        {history.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Recent Usage History</h3>
            <table style={{ fontSize: 13 }}>
              <thead>
                <tr><th>Date</th><th>Quantity</th></tr>
              </thead>
              <tbody>
                {history.slice(0, 10).map(h => (
                  <tr key={h.id}>
                    <td>{new Date(h.logged_at).toLocaleDateString()}</td>
                    <td>{h.quantity_used} {item.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
