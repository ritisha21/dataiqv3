'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { modelsApi, connectionsApi } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import toast from 'react-hot-toast'
import {
  BrainCircuit, Plus, Loader2, ChevronDown, ChevronUp,
  BarChart2, Zap, AlertCircle
} from 'lucide-react'

const GOALS = ['churn', 'revenue_forecast', 'classification', 'regression']

export default function ModelsPage() {
  const { selectedConnectionId } = useConnectionStore()
  const [showTrain, setShowTrain] = useState(false)
  const qc = useQueryClient()

  const { data: models = [], isLoading } = useQuery({
    queryKey: ['models'],
    queryFn:  () => modelsApi.list().then(r => r.data),
    refetchInterval: 8_000,  // poll while models may be training
  })

  const trainMutation = useMutation({
    mutationFn: (d: any) => modelsApi.train(d),
    onSuccess: () => {
      toast.success('Training queued!')
      setShowTrain(false)
      qc.invalidateQueries({ queryKey: ['models'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Failed to start training'),
  })

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">ML Models</h1>
          <p className="text-muted text-sm mt-0.5">Train and manage your AutoML models</p>
        </div>
        {selectedConnectionId && (
          <button onClick={() => setShowTrain(!showTrain)}
            className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                       rounded-lg text-sm transition-all">
            <Plus size={14} /> Train Model
          </button>
        )}
      </div>

      {showTrain && selectedConnectionId && (
        <TrainForm
          connectionId={selectedConnectionId}
          onSubmit={trainMutation.mutate}
          loading={trainMutation.isPending}
        />
      )}

      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="animate-spin text-accent" /></div>
      ) : (
        <div className="space-y-3">
          {models.map((m: any) => <ModelCard key={m.id} model={m} />)}
          {models.length === 0 && (
            <div className="glass p-12 flex flex-col items-center gap-3 text-center">
              <BrainCircuit size={40} className="text-muted" />
              <p className="text-muted text-sm">No models yet. Train your first model.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TrainForm({ connectionId, onSubmit, loading }: any) {
  const [f, setF] = useState({
    name: '', goal: 'churn', target_column: '', source_table: '',
  })

  const { data: schema } = useQuery({
    queryKey: ['schema', connectionId],
    queryFn:  () => connectionsApi.getSchema(connectionId).then(r => r.data),
  })

  const tables = schema?.schema?.nodes?.map((n: any) => n.id) || []
  const selectedTableCols = schema?.schema?.nodes
    ?.find((n: any) => n.id === f.source_table)
    ?.columns?.map((c: any) => c.name) || []

  return (
    <div className="glass p-6 space-y-4 animate-slide-up">
      <h3 className="font-medium text-sm">New Model</h3>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Model Name" value={f.name}
               onChange={e => setF(p => ({ ...p, name: e.target.value }))} />
        <div>
          <label className="block text-xs text-muted mb-1">Goal</label>
          <select value={f.goal} onChange={e => setF(p => ({ ...p, goal: e.target.value }))}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5 text-sm
                       text-white focus:outline-none focus:border-accent">
            {GOALS.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-muted mb-1">Source Table</label>
          <select value={f.source_table}
                  onChange={e => setF(p => ({ ...p, source_table: e.target.value, target_column: '' }))}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5 text-sm
                       text-white focus:outline-none focus:border-accent">
            <option value="">Select table…</option>
            {tables.map((t: string) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-muted mb-1">Target Column</label>
          <select value={f.target_column}
                  onChange={e => setF(p => ({ ...p, target_column: e.target.value }))}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5 text-sm
                       text-white focus:outline-none focus:border-accent">
            <option value="">Select column…</option>
            {selectedTableCols.map((c: string) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>
      <button
        onClick={() => onSubmit({ ...f, connection_id: connectionId })}
        disabled={loading || !f.name || !f.source_table || !f.target_column}
        className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                   disabled:opacity-50 rounded-lg text-sm transition-all">
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
        Start Training
      </button>
    </div>
  )
}

function ModelCard({ model: m }: { model: any }) {
  const [expanded, setExpanded]    = useState(false)
  const [predInput, setPredInput]  = useState('')
  const [predResult, setPredResult]= useState<any>(null)
  const [predLoading, setPredLoading] = useState(false)

  const runPrediction = async () => {
    if (!predInput.trim()) return
    setPredLoading(true)
    try {
      let input_data: any = {}
      try { input_data = JSON.parse(predInput) } catch { input_data = {} }
      const { data } = await modelsApi.predict({ model_id: m.id, input_data })
      setPredResult(data.prediction)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Prediction failed')
    } finally {
      setPredLoading(false)
    }
  }

  const statusColors: Record<string, string> = {
    ready:    'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    training: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    failed:   'bg-red-500/20 text-red-400 border-red-500/30',
    pending:  'bg-blue-500/20 text-blue-400 border-blue-500/30',
  }

  return (
    <div className="glass">
      <div className="p-4 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-surface-3 flex items-center justify-center">
          <BrainCircuit size={16} className="text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm">{m.name}</p>
          <p className="text-xs text-muted capitalize">
            {m.goal} · {m.source_table} → {m.target_column}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded border text-xs font-medium ${statusColors[m.status] || ''}`}>
            {m.status}
          </span>
          {m.status === 'training' && <Loader2 size={12} className="animate-spin text-yellow-400" />}
          <button onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-muted hover:text-white transition-colors">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border p-4 space-y-4">
          {/* Metrics */}
          {m.metrics && Object.keys(m.metrics).length > 0 && (
            <div>
              <p className="text-xs text-muted mb-2 font-medium">METRICS</p>
              <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                {Object.entries(m.metrics).map(([k, v]: any) => (
                  typeof v === 'number' && (
                    <div key={k} className="bg-surface-3 rounded-lg px-3 py-2 text-center">
                      <p className="text-xs text-muted">{k.toUpperCase()}</p>
                      <p className="text-sm font-semibold text-accent">
                        {v < 1 ? (v * 100).toFixed(1) + (k.includes('rmse') || k.includes('mae') ? '' : '%') : v.toLocaleString()}
                      </p>
                    </div>
                  )
                ))}
              </div>
            </div>
          )}

          {/* Prediction */}
          {m.status === 'ready' && (
            <div>
              <p className="text-xs text-muted mb-2 font-medium">PREDICT</p>
              <div className="flex gap-2">
                <input
                  value={predInput}
                  onChange={e => setPredInput(e.target.value)}
                  placeholder='{"feature_1": 0.5, "feature_2": 42}'
                  className="flex-1 bg-surface-2 border border-border rounded-lg px-3 py-2
                             text-xs font-mono text-white placeholder-muted
                             focus:outline-none focus:border-accent"
                />
                <button onClick={runPrediction} disabled={predLoading}
                  className="px-3 py-2 bg-accent hover:bg-accent-hover disabled:opacity-50
                             rounded-lg text-xs transition-all flex items-center gap-1">
                  {predLoading ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                  Predict
                </button>
              </div>
              {predResult !== null && (
                <div className="mt-2 bg-accent/10 border border-accent/20 rounded-lg px-3 py-2">
                  <p className="text-xs text-muted">Result</p>
                  <p className="text-sm font-semibold text-accent">
                    {typeof predResult === 'object' ? JSON.stringify(predResult) : String(predResult)}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Field({ label, ...props }: any) {
  return (
    <div>
      <label className="block text-xs text-muted mb-1">{label}</label>
      <input {...props} className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5
                                   text-sm text-white focus:outline-none focus:border-accent transition-colors" />
    </div>
  )
}

function toast_error(msg: string) { console.error(msg) }
