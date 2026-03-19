import { useState, useEffect } from 'react'
import { api } from './api'
import CoPilot from './components/CoPilot'
import Inventory from './components/Inventory'
import WhatIf from './components/WhatIf'
import Predictions from './components/Predictions'
import Sustainability from './components/Sustainability'

const TABS = ['copilot', 'inventory', 'whatif', 'predictions', 'sustainability']
const TAB_LABELS = { copilot: 'Co-Pilot', inventory: 'Inventory', whatif: 'What-If', predictions: 'Predictions', sustainability: 'Sustainability' }

export default function App() {
  const [tab, setTab] = useState('copilot')
  const [items, setItems] = useState([])
  const [badge, setBadge] = useState('')

  const refreshItems = async () => {
    try {
      const data = await api('/items')
      setItems(data.items)
    } catch (e) { console.error(e) }
  }

  const loadBadge = async () => {
    try {
      const s = await api('/sustainability')
      setBadge(`Score: ${s.overall_score} (${s.grade})`)
    } catch (e) {}
  }

  useEffect(() => { refreshItems(); loadBadge() }, [])

  return (
    <>
      <header>
        <h1>Green-Tech Inventory Co-Pilot</h1>
        <span style={{ fontSize: 14, cursor: 'pointer' }} onClick={() => setTab('sustainability')}>{badge}</span>
      </header>
      <div className="container">
        <div className="tabs">
          {TABS.map(t => (
            <div key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {TAB_LABELS[t]}
            </div>
          ))}
        </div>
        {tab === 'copilot' && <CoPilot />}
        {tab === 'inventory' && <Inventory items={items} onRefresh={refreshItems} />}
        {tab === 'whatif' && <WhatIf items={items} />}
        {tab === 'predictions' && <Predictions />}
        {tab === 'sustainability' && <Sustainability onLoad={loadBadge} />}
      </div>
    </>
  )
}
