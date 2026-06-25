'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { dashboardApi, modelsApi } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import { useClassificationStore } from '@/lib/classificationStore'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, Database, Loader2, AlertCircle, Sparkles, ArrowRight, Zap, CheckCircle2, Target } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import GraphSelector from '@/components/charts/GraphSelector'

const COLORS = ['#6c63ff', '#00e599', '#f59e0b', '#ef4444', '#3b82f6']

export default function DashboardPage() {
  const { selectedConnectionId } = useConnectionStore()
  const { availableTables } = useClassificationStore()
  const router = useRouter()

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

  const kpis    = data?.widgets?.filter((w: any) => w.type === 'kpi')   || []
  const stats   = data?.widgets?.filter((w: any) => w.type === 'stat')  || []
  const charts  = data?.widgets?.filter((w: any) => w.type === 'chart') || []
  const models  = data?.models  || []
  const queries = data?.recent_queries || []

  // Build a flat list of all column names from all chart widgets for GraphSelector
  const allChartData: Record<string, unknown>[] = charts.flatMap((w: any) => w.data || [])
  const allChartCols: string[] = allChartData.length > 0
    ? Object.keys(allChartData[0])
    : []

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-muted text-sm mt-0.5">Auto-generated from your connected database</p>
      </div>

      {/* KPI row */}
      {(kpis.length > 0 || stats.length > 0) && (
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
                <p className="text-xs text-muted mt-1">min {w.min} · max {w.max}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* CRM Model Opportunities */}
      <CRMOpportunitiesPanel connectionId={selectedConnectionId} />

      {/* Graph Selector — interactive chart explorer */}
      {allChartData.length > 0 && allChartCols.length > 0 && (
        <GraphSelector
          data={allChartData}
          availableCols={allChartCols}
          title="Data Explorer"
          height={280}
        />
      )}

      {/* Static charts from dashboard API */}
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
                <div className={`w-1.5 h-1.5 rounded-full mt-1.5 ${q.success ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{q.question}</p>
                  <p className="text-xs text-muted">{q.row_count ?? '—'} rows</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Trained models */}
        <div className="glass p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium">Trained Models</h3>
            <Link href="/models" className="text-xs text-accent hover:underline">View all →</Link>
          </div>
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

function CRMOpportunitiesPanel({ connectionId }: { connectionId: string }) {
  const router = useRouter()
  const qc = useQueryClient()
  const [selectedGoal, setSelectedGoal] = useState<string | null>(null)
  const [recommendation, setRecommendation] = useState<any>(null)
  const [showRec, setShowRec] = useState(false)

  const { data: availableGoals = [], isLoading } = useQuery({
    queryKey: ['available-goals', connectionId],
    queryFn:  () => modelsApi.availableGoals(connectionId).then(r => r.data),
  })

  const recommendMutation = useMutation({
    mutationFn: (data: any) => modelsApi.recommend(data),
    onSuccess: (r: any) => {
      setRecommendation(r.data)
      setShowRec(true)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Failed to get recommendation'),
  })

  const trainMutation = useMutation({
    mutationFn: (d: any) => modelsApi.train(d),
    onSuccess: () => {
      toast.success('Training queued! Check the Models page.')
      setShowRec(false)
      setSelectedGoal(null)
      setRecommendation(null)
      qc.invalidateQueries({ queryKey: ['models'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Training failed'),
  })

  const handleGetRecommendation = () => {
    if (!selectedGoal) return
    recommendMutation.mutate({ connection_id: connectionId, goal_key: selectedGoal })
  }

  const handleTrain = () => {
    if (!recommendation) return
    trainMutation.mutate({
      name: `${recommendation.crm_model} Model`,
      goal: recommendation.ml_goal,
      target_column: recommendation.target_col,
      source_table: recommendation.source_table,
      connection_id: connectionId,
    })
  }

  return (
    <div className="glass p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-accent" />
          <h3 className="text-sm font-semibold">CRM Model Opportunities</h3>
        </div>
        <span className="text-xs text-muted">Based on your connected database</span>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted">
          <Loader2 size={12} className="animate-spin" /> Analysing your schema…
        </div>
      ) : (
        <>
          <p className="text-xs text-muted">
            {availableGoals.length} CRM models are possible with your data. Select a business goal to get started.
          </p>

          {!showRec ? (
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                {availableGoals.map((g: any) => (
                  <button key={g.key} onClick={() => setSelectedGoal(g.key)}
                    className={`text-left p-3 rounded-lg border transition-all
                      ${selectedGoal === g.key
                        ? 'border-accent bg-accent/10 text-white'
                        : 'border-border bg-surface-2 text-muted hover:text-white hover:border-accent/50'}`}>
                    <div className="text-sm font-medium">{g.label}</div>
                    <div className="text-xs opacity-60 mt-0.5">{g.crm_model}</div>
                  </button>
                ))}
              </div>
              <button
                onClick={handleGetRecommendation}
                disabled={!selectedGoal || recommendMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                           disabled:opacity-50 rounded-lg text-sm transition-all"
              >
                {recommendMutation.isPending
                  ? <Loader2 size={14} className="animate-spin" />
                  : <Sparkles size={14} />}
                Get CRM Model Recommendation
              </button>
            </div>
          ) : recommendation && (
            <div className="space-y-3">
              <div className="bg-surface-3 rounded-xl p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-muted mb-1">RECOMMENDED MODEL</p>
                    <p className="font-semibold text-accent text-base">{recommendation.crm_model}</p>
                    <p className="text-xs text-muted mt-1">{recommendation.description}</p>
                  </div>
                  <span className="px-2 py-1 bg-accent/20 text-accent rounded text-xs font-medium shrink-0 ml-2">
                    {recommendation.ml_model}
                  </span>
                </div>
                <div className="border-t border-border pt-3 text-xs text-muted">
                  <p className="font-medium text-white mb-1">Business Value</p>
                  <p>{recommendation.business_value}</p>
                </div>
                <div className="border-t border-border pt-3 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <p className="text-muted mb-1">Table</p>
                    <p className="text-white font-mono">{recommendation.source_table}</p>
                  </div>
                  <div>
                    <p className="text-muted mb-1">Target</p>
                    <p className="text-white font-mono">{recommendation.target_col}</p>
                  </div>
                </div>
                <div className="border-t border-border pt-3 text-xs">
                  <p className="text-muted mb-1">Features</p>
                  <div className="flex flex-wrap gap-1">
                    {recommendation.feature_cols?.map((f: string) => (
                      <span key={f} className="px-2 py-0.5 bg-surface-2 rounded font-mono text-white">{f}</span>
                    ))}
                  </div>
                </div>
                <div className={`flex items-center gap-1.5 text-xs ${recommendation.data_quality === 'good' ? 'text-emerald-400' : 'text-yellow-400'}`}>
                  {recommendation.data_quality === 'good'
                    ? <CheckCircle2 size={12} />
                    : <AlertCircle size={12} />}
                  {recommendation.data_quality_note}
                </div>
              </div>

              <div className="flex gap-2">
                <button onClick={() => { setShowRec(false); setRecommendation(null) }}
                  className="px-4 py-2 bg-surface-3 hover:bg-surface-2 border border-border rounded-lg text-sm transition-all">
                  ← Back
                </button>
                <button onClick={handleTrain} disabled={trainMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                             disabled:opacity-50 rounded-lg text-sm transition-all">
                  {trainMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
                  Train {recommendation.crm_model}
                </button>
                <Link href="/models"
                  className="flex items-center gap-2 px-4 py-2 bg-surface-3 hover:bg-surface-2
                             border border-border rounded-lg text-sm transition-all">
                  View Models <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          )}
        </>
      )}
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