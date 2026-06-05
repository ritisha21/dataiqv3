'use client'
import { useState, useRef, useEffect } from 'react'
import { useConnectionStore } from '@/lib/store'
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
         ScatterChart, Scatter, XAxis, YAxis, Tooltip,
         ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import { Send, Loader2, Database, ChevronDown, ChevronUp,
         BarChart2, MessageSquare, Zap } from 'lucide-react'
import Link from 'next/link'
import clsx from 'clsx'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const COLORS = ['#6c63ff', '#00e599', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899']

interface Message {
  id:        string
  role:      'user' | 'assistant'
  content:   string
  data?:     any[]
  columns?:  string[]
  chart?:    any
  sql?:      string
  insight?:  string
  ml_task?:  any
  response_type?: string
  loading?:  boolean
}

function uid() { return Math.random().toString(36).slice(2, 9) }

export default function ChatPage() {
  const { selectedConnectionId } = useConnectionStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    if (!input.trim() || streaming || !selectedConnectionId) return
    const userMsg = input.trim()
    setInput('')

    const userBubble: Message = { id: uid(), role: 'user', content: userMsg }
    const asstBubble: Message = { id: uid(), role: 'assistant', content: '', loading: true }
    setMessages(prev => [...prev, userBubble, asstBubble])
    setStreaming(true)

    try {
      const token = document.cookie.split('; ')
        .find(r => r.startsWith('access_token='))
        ?.split('=')[1]

      const resp = await fetch(`${API}/api/v1/chat/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body:    JSON.stringify({ connection_id: selectedConnectionId, message: userMsg }),
      })

      const reader = resp.body!.getReader()
      const dec    = new TextDecoder()
      let progressText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = dec.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (!line.startsWith('data: ') || line === 'data: [DONE]') continue
          try {
            const evt = JSON.parse(line.slice(6))

            if (evt.event === 'progress') {
              progressText = evt.message
              setMessages(prev => prev.map(m =>
                m.id === asstBubble.id
                  ? { ...m, content: progressText, loading: true }
                  : m
              ))
            }

            if (evt.event === 'done' && evt.payload) {
              const p = evt.payload
              setMessages(prev => prev.map(m =>
                m.id === asstBubble.id ? {
                  ...m,
                  content:       p.text || '',
                  data:          p.data,
                  columns:       p.columns,
                  chart:         p.chart,
                  sql:           p.sql,
                  insight:       p.insight,
                  ml_task:       p.ml_task,
                  response_type: p.response_type,
                  loading:       false,
                } : m
              ))
            }

            if (evt.event === 'error') {
              setMessages(prev => prev.map(m =>
                m.id === asstBubble.id
                  ? { ...m, content: `Error: ${evt.message}`, loading: false }
                  : m
              ))
            }
          } catch { /* malformed line */ }
        }
      }
    } catch (err: any) {
      setMessages(prev => prev.map(m =>
        m.id === asstBubble.id
          ? { ...m, content: 'Network error. Please try again.', loading: false }
          : m
      ))
    } finally {
      setStreaming(false)
    }
  }

  if (!selectedConnectionId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8">
        <Database size={40} className="text-muted" />
        <p className="text-muted text-sm">Select a database connection first</p>
        <Link href="/connections"
          className="px-4 py-2 bg-accent hover:bg-accent-hover rounded-lg text-sm transition-all">
          Go to Connections
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="border-b border-border px-6 py-3 flex items-center gap-2">
        <MessageSquare size={16} className="text-accent" />
        <span className="text-sm font-medium">AI Chat</span>
        <span className="ml-auto text-xs text-muted">SSE streaming · LangGraph</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center">
              <Zap size={24} className="text-accent" />
            </div>
            <div>
              <h3 className="font-medium mb-1">Ask anything about your data</h3>
              <p className="text-muted text-sm">
                "Show revenue by month" · "Why did churn increase?" · "Train a churn model"
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => { setInput(s) }}
                  className="glass px-3 py-2 text-xs text-muted hover:text-white
                             hover:border-accent/40 transition-all text-left rounded-lg">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border p-4">
        <div className="flex gap-3 items-end bg-surface-2 border border-border rounded-xl p-3">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }}}
            placeholder="Ask a question about your data…"
            rows={1}
            className="flex-1 bg-transparent text-sm text-white placeholder-muted
                       resize-none focus:outline-none min-h-[20px] max-h-[120px]"
          />
          <button onClick={sendMessage} disabled={streaming || !input.trim()}
            className="w-8 h-8 bg-accent hover:bg-accent-hover disabled:opacity-40
                       rounded-lg flex items-center justify-center transition-all flex-shrink-0">
            {streaming ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </div>
      </div>
    </div>
  )
}

const SUGGESTIONS = [
  'Show revenue trends by month',
  'Which customers have highest churn risk?',
  'Why did sales drop last quarter?',
  'Train a churn prediction model',
]

function MessageBubble({ message: m }: { message: Message }) {
  const [showSql, setShowSql]   = useState(false)
  const [showData, setShowData] = useState(false)

  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-xl bg-accent/10 border border-accent/20 rounded-2xl
                        rounded-tr-sm px-4 py-3 text-sm">
          {m.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 max-w-4xl">
      <div className="w-7 h-7 rounded-lg bg-surface-3 flex-shrink-0 flex items-center justify-center mt-1">
        <Zap size={12} className="text-accent" />
      </div>
      <div className="flex-1 space-y-3">
        {/* Main text */}
        <div className="glass rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed">
          {m.loading
            ? <span className="text-muted animate-pulse2">{m.content || 'Thinking…'}</span>
            : <span className="whitespace-pre-wrap">{m.content}</span>
          }
        </div>

        {/* Chart */}
        {m.chart && !m.loading && <ChartBlock spec={m.chart} />}

        {/* Data table */}
        {m.data && m.data.length > 0 && !m.loading && (
          <div className="glass rounded-xl overflow-hidden">
            <button onClick={() => setShowData(!showData)}
              className="w-full flex items-center justify-between px-4 py-2.5
                         text-xs text-muted hover:text-white transition-colors">
              <span className="flex items-center gap-2">
                <BarChart2 size={12} />
                {m.data.length} rows · {m.columns?.length} columns
              </span>
              {showData ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {showData && (
              <div className="overflow-x-auto max-h-60">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-t border-border bg-surface-3">
                      {m.columns?.map(c => (
                        <th key={c} className="px-3 py-2 text-left text-muted font-medium">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {m.data.slice(0, 50).map((row, i) => (
                      <tr key={i} className="border-t border-border hover:bg-surface-3 transition-colors">
                        {m.columns?.map(c => (
                          <td key={c} className="px-3 py-2 text-muted max-w-[160px] truncate">
                            {String(row[c] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* SQL */}
        {m.sql && !m.loading && (
          <div className="glass rounded-xl overflow-hidden">
            <button onClick={() => setShowSql(!showSql)}
              className="w-full flex items-center justify-between px-4 py-2.5
                         text-xs text-muted hover:text-white transition-colors">
              <span>View SQL</span>
              {showSql ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {showSql && (
              <pre className="px-4 pb-3 text-xs text-emerald-400 font-mono
                              overflow-x-auto leading-relaxed whitespace-pre-wrap">
                {m.sql}
              </pre>
            )}
          </div>
        )}

        {/* ML task */}
        {m.ml_task?.triggered && !m.loading && (
          <div className="glass rounded-xl px-4 py-3 border-accent/30">
            <p className="text-xs text-accent font-medium mb-1">🤖 Model Training Queued</p>
            <p className="text-xs text-muted">
              Goal: {m.ml_task.goal} · Target: {m.ml_task.target_col} · Table: {m.ml_task.source_table}
            </p>
            <p className="text-xs text-muted mt-1 font-mono">Task: {m.ml_task.task_id}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function ChartBlock({ spec }: { spec: any }) {
  const { chart_type, x_col, y_col, title, data, color_col } = spec
  if (!data || data.length === 0) return null

  return (
    <div className="glass rounded-xl p-4">
      <h4 className="text-sm font-medium mb-4">{title}</h4>
      <ResponsiveContainer width="100%" height={220}>
        {chart_type === 'line' ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a38" />
            <XAxis dataKey={x_col} tick={{ fill: '#6b6b80', fontSize: 10 }} />
            <YAxis tick={{ fill: '#6b6b80', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#18181f', border: '1px solid #2a2a38', borderRadius: 8 }} />
            <Line type="monotone" dataKey={y_col} stroke="#6c63ff" strokeWidth={2} dot={false} />
          </LineChart>
        ) : chart_type === 'pie' ? (
          <PieChart>
            <Pie data={data} dataKey={y_col} nameKey={x_col} cx="50%" cy="50%" outerRadius={80} label>
              {data.map((_: any, i: number) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={{ background: '#18181f', border: '1px solid #2a2a38', borderRadius: 8 }} />
            <Legend />
          </PieChart>
        ) : chart_type === 'scatter' ? (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a38" />
            <XAxis dataKey="x" name={x_col} tick={{ fill: '#6b6b80', fontSize: 10 }} />
            <YAxis dataKey="y" name={y_col} tick={{ fill: '#6b6b80', fontSize: 10 }} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }}
              contentStyle={{ background: '#18181f', border: '1px solid #2a2a38', borderRadius: 8 }} />
            <Scatter data={data} fill="#6c63ff" />
          </ScatterChart>
        ) : (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a38" />
            <XAxis dataKey={x_col} tick={{ fill: '#6b6b80', fontSize: 10 }} />
            <YAxis tick={{ fill: '#6b6b80', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#18181f', border: '1px solid #2a2a38', borderRadius: 8 }} />
            <Bar dataKey={y_col} fill="#6c63ff" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
