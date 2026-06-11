'use client'
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { modelsApi, connectionsApi } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import toast from 'react-hot-toast'
import {
  BrainCircuit, Plus, Loader2, ChevronDown, ChevronUp,
  BarChart2, Zap, AlertCircle, TrendingUp, CheckCircle2
} from 'lucide-react'

const GOALS = ['churn', 'revenue_forecast', 'classification', 'regression']

// Known agents and products from the CRM data
const SALES_AGENTS = [
  'Darcel Schlecht', 'Vicki Laflamme', 'Anna Snelling', 'Kary Hendrixson',
  'Kami Bicknell', 'Versie Hillebrand', 'Zane Levy', 'Cassey Cress',
  'Jonathan Berthelot', 'Gladys Colclough', 'Lajuana Vencill', 'Corliss Cosme',
  'Markita Hansen', 'Maureen Marcano', 'Marty Freudenburg', 'Donn Cantrell',
  'James Ascencio', 'Violet Mclelland', 'Moses Frase', 'Daniell Hammack',
  'Niesha Huffines', 'Reed Clapper', 'Boris Faz', 'Cecily Lampkin',
  'Hayden Neloms', 'Elease Gluck', 'Rosie Papadopoulos', 'Rosalina Dieter',
  'Garret Kinder', 'Wilburn Farren'
]

const PRODUCTS = [
  'GTX Basic', 'MG Special', 'GTXPro', 'MG Advanced',
  'GTX Plus Basic', 'GTX Plus Pro', 'GTK 500'
]

export default function ModelsPage() {
  const { selectedConnectionId } = useConnectionStore()
  const [showTrain, setShowTrain] = useState(false)
  const qc = useQueryClient()

  const { data: models = [], isLoading } = useQuery({
    queryKey: ['models'],
    queryFn:  () => modelsApi.list().then(r => r.data),
    refetchInterval: 8_000,
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
               onChange={(e: any) => setF(p => ({ ...p, name: e.target.value }))} />
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
  const [expanded, setExpanded] = useState(false)
  const [predResult, setPredResult] = useState<any>(null)
  const [predLoading, setPredLoading] = useState(false)

  // Smart form fields
  const [salesAgent, setSalesAgent] = useState('Anna Snelling')
  const [product, setProduct] = useState('GTXPro')
  const [closeValue, setCloseValue] = useState('5000')
  const [createdDate, setCreatedDate] = useState('2017-01-01')
  const [closeDate, setCloseDate] = useState('2017-03-01')

  const dateToUnix = (d: string) => Math.floor(new Date(d).getTime() / 1000)

  const runPrediction = async () => {
    setPredLoading(true)
    try {
      const input_data: any = {
        sales_agent: salesAgent,
        product: product,
        close_value: parseFloat(closeValue) || 0,
        created_date: dateToUnix(createdDate),
        close_date: dateToUnix(closeDate),
      }
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

  const predictionColors: Record<string, string> = {
    'Won':         'text-emerald-400',
    'Lost':        'text-red-400',
    'In Progress': 'text-yellow-400',
  }

  const predictionIcons: Record<string, any> = {
    'Won':         <CheckCircle2 size={18} className="text-emerald-400" />,
    'Lost':        <AlertCircle size={18} className="text-red-400" />,
    'In Progress': <TrendingUp size={18} className="text-yellow-400" />,
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
                        {v < 1 ? (v * 100).toFixed(1) + '%' : v.toLocaleString()}
                      </p>
                    </div>
                  )
                ))}
              </div>
            </div>
          )}

          {/* Smart Prediction Form */}
          {m.status === 'ready' && (
            <div>
              <p className="text-xs text-muted mb-3 font-medium">PREDICT DEAL OUTCOME</p>
              <div className="grid grid-cols-2 gap-3">

                {/* Sales Agent dropdown */}
                <div>
                  <label className="block text-xs text-muted mb-1">Sales Agent</label>
                  <select
                    value={salesAgent}
                    onChange={e => setSalesAgent(e.target.value)}
                    className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm
                               text-white focus:outline-none focus:border-accent"
                  >
                    {SALES_AGENTS.map(a => <option key={a} value={a}>{a}</option>)}
                  </select>
                </div>

                {/* Product dropdown */}
                <div>
                  <label className="block text-xs text-muted mb-1">Product</label>
                  <select
                    value={product}
                    onChange={e => setProduct(e.target.value)}
                    className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm
                               text-white focus:outline-none focus:border-accent"
                  >
                    {PRODUCTS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>

                {/* Deal Value */}
                <div>
                  <label className="block text-xs text-muted mb-1">Deal Value ($)</label>
                  <input
                    type="number"
                    value={closeValue}
                    onChange={e => setCloseValue(e.target.value)}
                    placeholder="5000"
                    className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm
                               text-white focus:outline-none focus:border-accent"
                  />
                </div>

                {/* Created Date */}
                <div>
                  <label className="block text-xs text-muted mb-1">Deal Created</label>
                  <input
                    type="date"
                    value={createdDate}
                    onChange={e => setCreatedDate(e.target.value)}
                    className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm
                               text-white focus:outline-none focus:border-accent"
                  />
                </div>

                {/* Close Date */}
                <div>
                  <label className="block text-xs text-muted mb-1">Expected Close</label>
                  <input
                    type="date"
                    value={closeDate}
                    onChange={e => setCloseDate(e.target.value)}
                    className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm
                               text-white focus:outline-none focus:border-accent"
                  />
                </div>

                {/* Predict Button */}
                <div className="flex items-end">
                  <button
                    onClick={runPrediction}
                    disabled={predLoading}
                    className="w-full px-4 py-2 bg-accent hover:bg-accent-hover disabled:opacity-50
                               rounded-lg text-sm transition-all flex items-center justify-center gap-2"
                  >
                    {predLoading
                      ? <Loader2 size={14} className="animate-spin" />
                      : <Zap size={14} />}
                    Predict Outcome
                  </button>
                </div>
              </div>

              {/* Result */}
              {predResult !== null && (
                <div className="mt-4 bg-surface-3 border border-border rounded-xl p-4">
                  <p className="text-xs text-muted mb-2">PREDICTION RESULT</p>
                  {typeof predResult === 'object' ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        {predictionIcons[predResult.prediction] || <BarChart2 size={18} className="text-accent" />}
                        <span className={`text-2xl font-bold ${predictionColors[predResult.prediction] || 'text-accent'}`}>
                          {predResult.prediction}
                        </span>
                      </div>
                      {predResult.confidence !== undefined && (
                        <div>
                          <div className="flex justify-between text-xs text-muted mb-1">
                            <span>Confidence</span>
                            <span>{(predResult.confidence * 100).toFixed(1)}%</span>
                          </div>
                          <div className="w-full bg-surface-2 rounded-full h-2">
                            <div
                              className="bg-accent rounded-full h-2 transition-all"
                              style={{ width: `${predResult.confidence * 100}%` }}
                            />
                          </div>
                        </div>
                      )}
                      {predResult.probability && (
                        <div className="grid grid-cols-3 gap-2 mt-2">
                          {Object.entries(predResult.probability).map(([k, v]: any) => {
                            const labels: Record<string, string> = { '0': 'Lost', '1': 'In Progress', '2': 'Won' }
                            return (
                              <div key={k} className="bg-surface-2 rounded-lg p-2 text-center">
                                <p className="text-xs text-muted">{labels[k] || k}</p>
                                <p className="text-sm font-semibold text-white">{(v * 100).toFixed(1)}%</p>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-lg font-bold text-accent">{String(predResult)}</p>
                  )}
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