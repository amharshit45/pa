import { useState } from 'react'
import { api } from '../api'

export default function ItemModal({ item, onClose, onSaved }) {
  const isEdit = !!item
  const [form, setForm] = useState({
    name: item?.name || '',
    category: item?.category || 'Supplies',
    quantity: item?.quantity ?? '',
    unit: item?.unit || 'pieces',
    cost_per_unit: item?.cost_per_unit ?? 0,
    expiry_date: item?.expiry_date || '',
    daily_usage_rate: item?.daily_usage_rate ?? 0,
    supplier: item?.supplier || '',
    is_eco_certified: !!item?.is_eco_certified,
    notes: item?.notes || '',
  })
  const [error, setError] = useState('')

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required'); return }
    const qty = parseFloat(form.quantity)
    if (isNaN(qty) || qty < 0) { setError('Quantity must be >= 0'); return }
    const body = {
      ...form,
      quantity: qty,
      cost_per_unit: parseFloat(form.cost_per_unit) || 0,
      daily_usage_rate: parseFloat(form.daily_usage_rate) || 0,
      expiry_date: form.expiry_date || null,
    }
    try {
      if (isEdit) {
        await api(`/items/${item.id}`, { method: 'PUT', body: JSON.stringify(body) })
      } else {
        await api('/items', { method: 'POST', body: JSON.stringify(body) })
      }
      onSaved()
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <h2>{isEdit ? 'Edit Item' : 'Add Item'}</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Name *</label>
            <input value={form.name} onChange={e => set('name', e.target.value)} maxLength={200} />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Category</label>
              <select value={form.category} onChange={e => set('category', e.target.value)}>
                <option>Perishable</option><option>Supplies</option><option>Equipment</option><option>Other</option>
              </select>
            </div>
            <div className="form-group">
              <label>Unit</label>
              <input value={form.unit} onChange={e => set('unit', e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Quantity *</label>
              <input type="number" value={form.quantity} onChange={e => set('quantity', e.target.value)} min="0" step="any" />
            </div>
            <div className="form-group">
              <label>Cost/Unit</label>
              <input type="number" value={form.cost_per_unit} onChange={e => set('cost_per_unit', e.target.value)} min="0" step="0.01" />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Expiry Date</label>
              <input type="date" value={form.expiry_date} onChange={e => set('expiry_date', e.target.value)} />
            </div>
            <div className="form-group">
              <label>Daily Usage Rate</label>
              <input type="number" value={form.daily_usage_rate} onChange={e => set('daily_usage_rate', e.target.value)} min="0" step="any" />
            </div>
          </div>
          <div className="form-group">
            <label>Supplier</label>
            <input value={form.supplier} onChange={e => set('supplier', e.target.value)} />
          </div>
          <div className="form-group">
            <label><input type="checkbox" checked={form.is_eco_certified} onChange={e => set('is_eco_certified', e.target.checked)} /> Eco-Certified</label>
          </div>
          <div className="form-group">
            <label>Notes</label>
            <textarea rows={2} value={form.notes} onChange={e => set('notes', e.target.value)} />
          </div>
          {error && <div className="error">{error}</div>}
          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <button type="submit" className="btn-primary">Save</button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}
