'use client'
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import toast from 'react-hot-toast'
import {
  ScanLine, BrainCircuit, ChevronDown, ChevronUp,
  CheckSquare, Square, Loader2, Zap, Database,
  TableProperties, Target, BarChart2
} from 'lucide-react'
import Link from 'next/link'

interface Suggestion {
  id: string
  table: string
  target_column: string
  goal: string
  title: string
  description: string
  feature_columns: string[]
  row_count: number
  confidence: number
}

interface TableProfile {
  name: string
  row_count: number
  column_count: number
  columns: { name: string; dtype: string; tag: string; null_pct: number }[]
}

const GOAL_COLORS: Record<string, string> = {
  churn:            'bg-red-500/10 text-red-400 border-red-500/20',
  revenue_forecast: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  classification:   'bg-blue-500/10 text-blue-400 border-blue-500/20',
  regression:       'bg-purple-500/10 text-purple-400 border-purple-500/20',
}

const TAG_COLORS: Record<string, string> = {
  target_churn:   'text-red-400',
  target_revenue: 'text-emerald-400',
  datetime:       'text-blue-400',
  numeric:        'text-purple-400',
  categorical:    'text-amber-400',
  id:             'text-gray-500',
}

export default function ETLPage() {
  const { selectedConnectionId } = useConnectionStore()
  const [scanResult, setScanResult]   = useState<{ tables: TableProfile[]; suggestions: Suggestion[] } | null>(null)
  const [selected, setSelected]       = useState<Set<string>>(new Set())
  const [expandedTable, setExpandedTable] = useState<string | null>(null)
  const [taskId, setTaskId]           = useState<string | null>(null)
  const [trainResults, setTrainResults] = useState<any[]>([])

  const scanMutation = useMutation({
    mutationFn: () => api.post('/etl/scan', { connection_id: selectedConnectionId }),
    onSuccess: (res) => {
      setScanResult(res.data)
      setSelected(new Set())
      toast.success(`Found ${res.data.suggestions.length} possible features`)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Scan failed'),
  })

  const trainMutation = useMutation({
    mutationFn: () => api.post('/etl/train', {
      connection_id: selectedConnectionId,
      selected_ids:  Array.from(selected),
      suggestions:   scanResult?.suggestions || [],
    }),
    onSuccess: (res) => {
      setTaskId(res.data.task_id)
      toast.success(`Training ${res.data.count} model(s) started`)
      // poll for results
      pollResults(res.data.task_id)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Training failed'),
  })

  const pollResults = async (tid: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/etl/status/${tid}`)
        if (res.data.state === 'SUCCESS') {
          clearInterval(interval)
          setTrainResults(res.data.result?.results || [])
          toast.success('All models trained!')
        } else if (res.data.state === 'FAILURE') {
          clearInterval(interval)
          toast.error('Training failed')
        }
      } catch { clearInterval(interval) }
    }, 3000)
  }

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (!scanResult) return
    if (selected.size === scanResult.suggestions.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(scanResult.suggestions.map(s => s.id)))
    }
  }

  if (!selectedConnectionId) return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8 text-center">
      <Database size={40} className="text-muted" />
      <p className="text-muted text-sm">Select a database connection first</p>
      <Link href="/connections" className="px-4 py-2 bg-accent hover:bg-accent-hover rounded-lg text-sm">
        Go to Connections
      </Link>
    </div>
  )

  return (
    <div className="p-6 space-y-6 animate-fade-in max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">ETL Pipeline</h1>
          <p className="text-muted text-sm mt-1">
            Scan your database → see what's possible → select features → train models
          </p>
        </div>
        <button
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                     disabled:opacity-50 rounded-lg text-sm transition-all"
        >
          {scanMutation.isPending
            ? <Loader2 size={14} className="animate-spin" />
            : <ScanLine size={14} />}
          Scan Database
        </button>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-3 text-xs text-muted">
        <div className={`flex items-center gap-1.5 ${scanResult ? 'text-emerald-400' : ''}`}>
          <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium
            ${scanResult ? 'bg-emerald-500/20 text-emerald-400' : 'bg-surface-3 text-muted'}`}>1</div>
          Scan DB
        </div>
        <div className="w-8 h-px bg-border" />
        <div className={`flex items-center gap-1.5 ${selected.size > 0 ? 'text-emerald-400' : ''}`}>
          <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium
            ${selected.size > 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-surface-3 text-muted'}`}>2</div>
          Select features
        </div>
        <div className="w-8 h-px bg-border" />
        <div className={`flex items-center gap-1.5 ${trainResults.length > 0 ? 'text-emerald-400' : ''}`}>
          <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium
            ${trainResults.length > 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-surface-3 text-muted'}`}>3</div>
          Train models
        </div>
      </div>

      {/* Scan results — tables overview */}
      {scanResult && (
        <div className="glass p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium flex items-center gap-2">
              <TableProperties size={14} className="text-accent" />
              {scanResult.tables.length} tables found
            </h2>
            <span className="text-xs text-muted">{scanResult.tables.reduce((a, t) => a + t.row_count, 0).toLocaleString()} total rows</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {scanResult.tables.map(t => (
              <button key={t.name} onClick={() => setExpandedTable(expandedTable === t.name ? null : t.name)}
                className={`text-left p-3 rounded-lg border transition-all
                  ${expandedTable === t.name
                    ? 'border-accent/50 bg-accent/5'
                    : 'border-border bg-surface-2 hover:border-accent/30'}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium truncate">{t.name}</span>
                  {expandedTable === t.name ? <ChevronUp size={12} className="text-muted" /> : <ChevronDown size={12} className="text-muted" />}
                </div>
                <div className="text-xs text-muted">{t.row_count.toLocaleString()} rows · {t.column_count} cols</div>

                {expandedTable === t.name && (
                  <div className="mt-2 pt-2 border-t border-border space-y-1">
                    {t.columns.slice(0, 8).map(c => (
                      <div key={c.name} className="flex items-center justify-between">
                        <span className="text-xs truncate" style={{ maxWidth: '120px' }}>{c.name}</span>
                        <span className={`text-xs font-mono ${TAG_COLORS[c.tag] || 'text-muted'}`}>{c.tag}</span>
                      </div>
                    ))}
                    {t.columns.length > 8 && (
                      <p className="text-xs text-muted">+{t.columns.length - 8} more</p>
                    )}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Suggestions */}
      {scanResult && scanResult.suggestions.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium flex items-center gap-2">
              <Zap size={14} className="text-accent" />
              {scanResult.suggestions.length} features detected
              {selected.size > 0 && (
                <span className="px-2 py-0.5 bg-accent/20 text-accent rounded-full text-xs">
                  {selected.size} selected
                </span>
              )}
            </h2>
            <button onClick={toggleAll} className="text-xs text-muted hover:text-white transition-colors">
              {selected.size === scanResult.suggestions.length ? 'Deselect all' : 'Select all'}
            </button>
          </div>

          <div className="space-y-2">
            {scanResult.suggestions.map(s => (
              <SuggestionCard
                key={s.id}
                suggestion={s}
                selected={selected.has(s.id)}
                onToggle={() => toggleSelect(s.id)}
              />
            ))}
          </div>

          {/* Train button */}
          {selected.size > 0 && (
            <div className="sticky bottom-4 pt-2">
              <button
                onClick={() => trainMutation.mutate()}
                disabled={trainMutation.isPending || !!taskId}
                className="w-full flex items-center justify-center gap-2 py-3
                           bg-accent hover:bg-accent-hover disabled:opacity-50
                           rounded-xl text-sm font-medium transition-all shadow-lg"
              >
                {trainMutation.isPending || taskId
                  ? <><Loader2 size={15} className="animate-spin" /> Training {selected.size} model(s)…</>
                  : <><BrainCircuit size={15} /> Train {selected.size} selected model{selected.size > 1 ? 's' : ''}</>}
              </button>
            </div>
          )}
        </div>
      )}

      {scanResult && scanResult.suggestions.length === 0 && (
        <div className="glass p-8 text-center">
          <p className="text-muted text-sm">No trainable features detected in this database.</p>
          <p className="text-muted text-xs mt-1">Make sure your tables have numeric or boolean target columns.</p>
        </div>
      )}

      {/* Train results */}
      {trainResults.length > 0 && (
        <div className="glass p-4 space-y-3">
          <h2 className="text-sm font-medium flex items-center gap-2">
            <BarChart2 size={14} className="text-accent" />
            Training results
          </h2>
          {trainResults.map((r, i) => (
            <div key={i} className={`p-3 rounded-lg border ${
              r.status === 'success'
                ? 'border-emerald-500/20 bg-emerald-500/5'
                : 'border-red-500/20 bg-red-500/5'
            }`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{r.table} → {r.target_column}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  r.status === 'success'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-red-500/20 text-red-400'
                }`}>{r.status}</span>
              </div>
              {r.metrics && (
                <div className="flex gap-3 mt-1">
                  {Object.entries(r.metrics).slice(0, 4).map(([k, v]: any) =>
                    typeof v === 'number' && (
                      <span key={k} className="text-xs text-muted">
                        {k}: <span className="text-white font-mono">{v < 1 ? `${(v*100).toFixed(1)}%` : v}</span>
                      </span>
                    )
                  )}
                </div>
              )}
              {r.error && <p className="text-xs text-red-400 mt-1">{r.error}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SuggestionCard({
  suggestion: s, selected, onToggle
}: {
  suggestion: Suggestion
  selected: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className={`w-full text-left p-4 rounded-xl border transition-all
        ${selected
          ? 'border-accent/60 bg-accent/8 shadow-sm'
          : 'border-border bg-surface-2 hover:border-accent/30'}`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex-shrink-0">
          {selected
            ? <CheckSquare size={16} className="text-accent" />
            : <Square size={16} className="text-muted" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium">{s.title}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${GOAL_COLORS[s.goal] || 'bg-surface-3 text-muted border-border'}`}>
              {s.goal.replace('_', ' ')}
            </span>
            <span className="text-xs text-muted ml-auto">{Math.round(s.confidence * 100)}% confidence</span>
          </div>
          <p className="text-xs text-muted">{s.description}</p>
          <div className="flex items-center gap-3 mt-2 text-xs text-muted">
            <span className="flex items-center gap-1"><Database size={10} />{s.table}</span>
            <span className="flex items-center gap-1"><Target size={10} />{s.target_column}</span>
            <span className="flex items-center gap-1"><BarChart2 size={10} />{s.feature_columns.length} features</span>
          </div>
        </div>
      </div>
    </button>
  )
}
