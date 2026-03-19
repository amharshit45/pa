import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import ItemModal from './ItemModal'

function quickPredict(item) {
  const rate = item.daily_usage_rate || 0
  const qty = item.quantity || 0
  let urgency = 'ok'
  if (rate > 0) {
    const days = Math.floor(qty / rate)
    if (days <= 2) urgency = 'critical'
    else if (days <= 7) urgency = 'warning'
  }
  if (item.expiry_date) {
    const daysExp = Math.floor((new Date(item.expiry_date) - new Date()) / 86400000)
    if (daysExp < 0 || daysExp <= 3) urgency = 'critical'
    else if (daysExp <= 7 && urgency !== 'critical') urgency = 'warning'
  }
  if (rate === 0 && !item.expiry_date) urgency = 'unknown'
  return urgency
}

export default function Inventory({ items: initialItems, onRefresh }) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [categories, setCategories] = useState([])
  const [items, setItems] = useState(initialItems)
  const [modal, setModal] = useState(null) // null | 'add' | item object
  const [timer, setTimer] = useState(null)

  useEffect(() => {
    api('/categories').then(setCategories).catch(() => {})
  }, [])

  const loadItems = useCallback(async () => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (category) params.set('category', category)
    try {
      const data = await api(`/items?${params}`)
      setItems(data.items)
    } catch (e) { console.error(e) }
  }, [search, category])

  useEffect(() => {
    clearTimeout(timer)
    setTimer(setTimeout(loadItems, 300))
  }, [search, category])

  useEffect(() => { setItems(initialItems) }, [initialItems])

  const handleDelete = async (id) => {
    if (!confirm('Delete this item?')) return
    try { await api(`/items/${id}`, { method: 'DELETE' }); loadItems(); onRefresh() }
    catch (e) { alert(e.message) }
  }

  const handlePredict = async (id) => {
    try {
      const p = await api(`/items/${id}/predict`)
      let msg = `${p.item} [${p.method}${p.model ? ' - ' + p.model : ''}]\n\nUrgency: ${p.urgency}\n${p.recommendation}`
      if (p.trend) msg += `\nTrend: ${p.trend} (${p.trend_pct > 0 ? '+' : ''}${p.trend_pct}%)`
      if (p.forecast_usage_rate) msg += `\nForecast usage: ${p.forecast_usage_rate}/day`
      if (p.sustainability_tip) msg += `\n${p.sustainability_tip}`
      if (p.expiry_warning) msg += `\n${p.expiry_warning}`
      msg += `\nDays left: ${p.days_until_empty ?? 'N/A'}`
      if (p.note) msg += `\n\nNote: ${p.note}`
      alert(msg)
    } catch (e) { alert(e.message) }
  }

  const handleSaved = () => {
    setModal(null)
    loadItems()
    onRefresh()
  }

  return (
    <>
      <div className="controls">
        <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search items or suppliers..." />
        <select value={category} onChange={e => setCategory(e.target.value)}>
          <option value="">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <button className="btn-primary" onClick={() => setModal('add')}>+ Add Item</button>
      </div>
      <div className="card">
        <table>
          <thead>
            <tr><th>Name</th><th>Category</th><th>Qty</th><th>Expiry</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: 'center', color: '#888', padding: 40 }}>No items found</td></tr>
            ) : items.map(i => (
              <tr key={i.id}>
                <td>
                  <strong>{i.name}</strong>
                  {i.is_eco_certified ? <span className="badge badge-eco" style={{ marginLeft: 6 }}>ECO</span> : null}
                  <br /><small style={{ color: '#888' }}>{i.supplier}</small>
                </td>
                <td>{i.category}</td>
                <td>{i.quantity} {i.unit}</td>
                <td>{i.expiry_date || '-'}</td>
                <td><span className={`badge badge-${quickPredict(i)}`}>{quickPredict(i)}</span></td>
                <td>
                  <button className="btn-sm btn-primary" onClick={() => setModal(i)}>Edit</button>{' '}
                  <button className="btn-sm" onClick={() => handlePredict(i.id)}>Predict</button>{' '}
                  <button className="btn-sm btn-danger" onClick={() => handleDelete(i.id)}>Del</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && <ItemModal item={modal === 'add' ? null : modal} onClose={() => setModal(null)} onSaved={handleSaved} />}
    </>
  )
}
