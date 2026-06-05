'use client'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
         XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, Database, Loader2, AlertCircle } from 'lucide-react'
import Link from 'next/link'

const COLORS = ['#6c63ff', '#00e599', '#f59e0b', '#ef4444', '#3b82f6']

export default function DashboardPage() {
  const { selectedConnectionId } = useConnectionStore()

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard', selectedConnectionId],
    queryFn:  () => dashboardApi.getWidgets(selectedConnectionId!).then(r => r.data),
    enabled:  !!selectedConnectionId,
    staleTime: 60_000,
  })

  if (!selectedConnectionId) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <Database size={48} className="text-muted mb-4" />
        <h2 className="text-xl font-semibold mb-2">No connection selected</h2>
        <p className="text-muted text-sm mb-4">Connect a database to see your dashboard</p>
        <Link href="/connections"
          className="px-4 py-2 bg-accent hover:bg-accent-hover rounded-lg text-sm transition-all">
          Connect database
        </Link>
      </div>
    )
  }

  if (isLoading) return (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="animate-spin text-accent" size={32} />
    </div>
  )

  if (error) return (
    <div className="flex items-center justify-center h-full gap-2 text-red-400">
      <AlertCircle size={20} />
      <span>Failed to load dashboard</span>
    </div>
  )

  const kpis    = data?.widgets?.filter((w: any) => w.type === 'kpi')  || []
  const stats   = data?.widgets?.filter((w: any) => w.type === 'stat') || []
  const charts  = data?.widgets?.filter((w: any) => w.type === 'chart')|| []
  const models  = data?.models  || []
  const queries = data?.recent_queries || []

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-muted text-sm mt-0.5">Auto-generated from your connected database</p>
      </div>

      {/* KPI row */}
      {kpis.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {kpis.map((w: any, i: number) => (
            <div key={i} className="glass p-4">
              <p className="text-xs text-muted mb-1">{w.title}</p>
              <p className="text-2xl font-bold">{w.value?.toLocaleString()}</p>
            </div>
          ))}
          {stats.map((w: any, i: number) => (
            <div key={`s${i}`} className="glass p-4">
              <p className="text-xs text-muted mb-1">{w.title}</p>
              <p className="text-2xl font-bold">{w.value?.toLocaleString()}</p>
              {w.min != null && (
                <p className="text-xs text-muted mt-1">
                  min {w.min} · max {w.max}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Charts */}
      {charts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {charts.map((w: any, i: number) => (
            <div key={i} className="glass p-4">
              <h3 className="text-sm font-medium mb-4">{w.title}</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={w.data}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2a38" />
                  <XAxis dataKey="label" tick={{ fill: '#6b6b80', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#6b6b80', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#18181f', border: '1px solid #2a2a38', borderRadius: 8 }}
                    labelStyle={{ color: '#e8e8f0' }}
                  />
                  <Bar dataKey="value" fill="#6c63ff" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Recent queries */}
        <div className="glass p-4">
          <h3 className="text-sm font-medium mb-3">Recent Queries</h3>
          <div className="space-y-2">
            {queries.length === 0 && <p className="text-muted text-sm">No queries yet</p>}
            {queries.map((q: any) => (
              <div key={q.id} className="flex items-start gap-2 py-2 border-b border-border last:border-0">
                <div className={`w-1.5 h-1.5 rounded-full mt-1.5 ${q.success ? 'bg-emerald-glow' : 'bg-red-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{q.question}</p>
                  <p className="text-xs text-muted">{q.row_count ?? '–'} rows</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Models */}
        <div className="glass p-4">
          <h3 className="text-sm font-medium mb-3">Models</h3>
          <div className="space-y-2">
            {models.length === 0 && <p className="text-muted text-sm">No models trained yet</p>}
            {models.map((m: any) => (
              <div key={m.id} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                <div>
                  <p className="text-sm font-medium">{m.name}</p>
                  <p className="text-xs text-muted capitalize">{m.goal}</p>
                </div>
                <StatusBadge status={m.status} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ready:    'bg-emerald-500/20 text-emerald-400',
    training: 'bg-yellow-500/20 text-yellow-400',
    failed:   'bg-red-500/20 text-red-400',
    pending:  'bg-blue-500/20 text-blue-400',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] || 'bg-surface-3 text-muted'}`}>
      {status}
    </span>
  )
}
