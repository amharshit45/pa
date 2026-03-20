import { useState, useRef, useEffect } from 'react'
import { api } from '../api'

const SUGGESTIONS = [
  'How can I reduce waste this week?',
  'What items are running low?',
  'How can I improve our sustainability score?',
  'Give me a cost overview',
  'Summary of inventory status',
]

export default function CoPilot() {
  const [messages, setMessages] = useState([
    { role: 'bot', text: 'Welcome! I\'m your sustainability co-pilot. Ask me about waste reduction, stock levels, costs, or sustainability improvements.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const sendChat = async (query) => {
    setMessages(prev => [...prev, { role: 'user', text: query }])
    setInput('')
    setLoading(true)
    try {
      const data = await api('/chat', { method: 'POST', body: JSON.stringify({ query }) })
      setMessages(prev => [...prev, { role: 'bot', data }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'bot', text: `Error: ${e.message}`, error: true }])
    }
    setLoading(false)
  }

  return (
    <div className="card">
      <h2 style={{ marginBottom: 12 }}>Sustainability Co-Pilot</h2>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 12 }}>
        Ask questions about your inventory, waste reduction, costs, or sustainability.
      </p>
      <div className="suggestion-chips">
        {SUGGESTIONS.map(s => (
          <span key={s} className="chip" onClick={() => sendChat(s)}>{s.replace(/\?$/, '').replace(/^How can I /, '').replace(/^Give me a /, '').replace(/^Summary of /, '')}</span>
        ))}
      </div>
      <div className="chat-container">
        <div className="chat-messages">
          {messages.map((m, i) => (
            <div key={i} className={`chat-msg ${m.role}`} style={m.error ? { color: 'var(--danger)' } : {}}>
              {m.text || null}
              {m.data && <BotMessage data={m.data} onSend={sendChat} />}
            </div>
          ))}
          {loading && <div className="chat-msg bot" style={{ color: '#888' }}>Thinking...</div>}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && input.trim() && sendChat(input.trim())}
            placeholder="Ask: 'How can I reduce waste?' or 'What's running low?'"
          />
          <button className="btn-primary" onClick={() => input.trim() && sendChat(input.trim())}>Send</button>
        </div>
      </div>
    </div>
  )
}

function BotMessage({ data, onSend }) {
  return (
    <>
      <strong>{data.answer}</strong>
      {data.actions?.length > 0 && (
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {data.actions.map((a, i) => <li key={i} style={{ marginBottom: 4 }}>{a}</li>)}
        </ul>
      )}
      {data.waste_items?.length > 0 && (
        <div style={{ marginTop: 8, fontSize: 13 }}>
          {data.waste_items.map((w, i) => (
            <div key={i} style={{ margin: '4px 0', padding: '4px 8px', background: '#fff8f0', borderRadius: 4 }}>
              {w.name}: {w.wasted_qty} {w.unit} at risk (${w.wasted_cost})
            </div>
          ))}
        </div>
      )}
      {data.alternative_details?.length > 0 && (
        <div style={{ marginTop: 8, fontSize: 13 }}>
          <strong>Recommended alternatives:</strong>
          {data.alternative_details.map((ad, i) => (
            <div key={i} style={{ margin: '4px 0', padding: '4px 8px', background: '#e8f5e9', borderRadius: 4 }}>
              <strong>{ad.current_item}</strong> →{' '}
              {ad.alternatives[0]?.alternative_name} ({ad.alternatives[0]?.supplier},{' '}
              ~{ad.alternatives[0]?.carbon_footprint_reduction_pct}% less carbon)
            </div>
          ))}
        </div>
      )}
      {data.suggestions && (
        <div style={{ marginTop: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {data.suggestions.map((s, i) => (
            <span key={i} className="chip" onClick={() => onSend(s)}>{s}</span>
          ))}
        </div>
      )}
    </>
  )
}
