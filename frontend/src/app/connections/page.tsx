'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { connectionsApi } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import toast from 'react-hot-toast'
import { Database, Plus, Check, Loader2, ChevronDown, ChevronRight, Table } from 'lucide-react'

export default function ConnectionsPage() {
  const [showForm, setShowForm] = useState(false)
  const { selectedConnectionId, setConnection } = useConnectionStore()
  const qc = useQueryClient()

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['connections'],
    queryFn:  () => connectionsApi.list().then(r => r.data),
  })

  const connectMutation = useMutation({
    mutationFn: (data: any) => connectionsApi.connect(data),
    onSuccess: () => {
      toast.success('Database connected! Introspection started.')
      setShowForm(false)
      qc.invalidateQueries({ queryKey: ['connections'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Connection failed'),
  })

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Database Connections</h1>
          <p className="text-muted text-sm mt-0.5">Connect your Postgres or MySQL databases</p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                     rounded-lg text-sm transition-all">
          <Plus size={14} /> Connect DB
        </button>
      </div>

      {showForm && (
        <ConnectForm onSubmit={connectMutation.mutate} loading={connectMutation.isPending} />
      )}

      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="animate-spin text-accent" /></div>
      ) : (
        <div className="space-y-3">
          {connections.map((c: any) => (
            <ConnectionCard
              key={c.id}
              connection={c}
              selected={selectedConnectionId === c.id}
              onSelect={() => setConnection(c.id)}
            />
          ))}
          {connections.length === 0 && (
            <div className="glass p-12 flex flex-col items-center gap-3 text-center">
              <Database size={40} className="text-muted" />
              <p className="text-muted text-sm">No connections yet. Connect your first database.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ConnectForm({ onSubmit, loading }: any) {
  const [f, setF] = useState({
    name: '', db_type: 'postgres', host: 'localhost',
    port: '5432', database: '', username: 'postgres', password: '',
  })
  const set = (k: string) => (e: any) => setF(p => ({ ...p, [k]: e.target.value }))

  const handleDbTypeChange = (t: string) =>
    setF(p => ({ ...p, db_type: t, port: t === 'mysql' ? '3306' : '5432' }))

  return (
    <div className="glass p-6 space-y-4 animate-slide-up">
      <h3 className="font-medium text-sm">New Connection</h3>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"     value={f.name}     onChange={set('name')} />
        <div>
          <label className="block text-xs text-muted mb-1">Type</label>
          <select value={f.db_type} onChange={e => handleDbTypeChange(e.target.value)}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-accent">
            <option value="postgres">PostgreSQL</option>
            <option value="mysql">MySQL</option>
          </select>
        </div>
        <Field label="Host"     value={f.host}     onChange={set('host')} />
        <Field label="Port"     value={f.port}     onChange={set('port')} />
        <Field label="Database" value={f.database} onChange={set('database')} />
        <Field label="Username" value={f.username} onChange={set('username')} />
        <div className="col-span-2">
          <Field label="Password" type="password" value={f.password} onChange={set('password')} />
        </div>
      </div>
      <button onClick={() => onSubmit({ ...f, port: Number(f.port) })} disabled={loading}
        className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                   disabled:opacity-50 rounded-lg text-sm transition-all">
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
        Connect
      </button>
    </div>
  )
}

function ConnectionCard({ connection: c, selected, onSelect }: any) {
  const [expanded, setExpanded] = useState(false)
  const { data: schema } = useQuery({
    queryKey: ['schema', c.id],
    queryFn:  () => connectionsApi.getSchema(c.id).then(r => r.data),
    enabled:  expanded,
  })

  return (
    <div className={`glass transition-all ${selected ? 'border-accent/50' : ''}`}>
      <div className="p-4 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-surface-3 flex items-center justify-center">
          <Database size={16} className="text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm">{c.name}</p>
          <p className="text-xs text-muted truncate">{c.db_type} · {c.host}:{c.port}/{c.database}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onSelect}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all
              ${selected
                ? 'bg-accent/20 text-accent'
                : 'bg-surface-3 text-muted hover:text-white'}`}>
            {selected ? <><Check size={12} className="inline mr-1"/>Active</> : 'Select'}
          </button>
          <button onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-muted hover:text-white transition-colors">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border p-4">
          {!schema
            ? <p className="text-xs text-muted">Loading schema…</p>
            : (
              <div className="space-y-2">
                <p className="text-xs text-muted">{schema.table_count} tables · v{schema.version}</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {schema.schema?.nodes?.slice(0, 12).map((t: any) => (
                    <div key={t.id} className="flex items-center gap-1.5 text-xs text-muted
                                                bg-surface-3 rounded px-2 py-1">
                      <Table size={10} />
                      <span className="truncate">{t.id}</span>
                      <span className="ml-auto text-xs opacity-50">{t.columns?.length}</span>
                    </div>
                  ))}
                </div>
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
                                   text-sm text-white placeholder-muted focus:outline-none
                                   focus:border-accent transition-colors" />
    </div>
  )
}
