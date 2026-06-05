'use client'
import { useState } from 'react'
import { api } from '@/lib/api'
import { useConnectionStore } from '@/lib/store'
import toast from 'react-hot-toast'
import { Download, Send, Loader2, Database, FileSpreadsheet, Eye, EyeOff } from 'lucide-react'
import Link from 'next/link'

export default function ExportPage() {
  const { selectedConnectionId } = useConnectionStore()
  const [question, setQuestion]     = useState('')
  const [rawSql, setRawSql]         = useState('')
  const [mode, setMode]             = useState<'nl' | 'sql'>('nl')
  const [preview, setPreview]       = useState<{ columns: string[]; rows: any[] } | null>(null)
  const [loading, setLoading]       = useState(false)
  const [showPreview, setShowPreview] = useState(true)
  const [filename, setFilename]     = useState('')

  const runAndPreview = async () => {
    if (!selectedConnectionId) { toast.error('Select a connection first'); return }
    const text = mode === 'nl' ? question : rawSql
    if (!text.trim()) { toast.error('Enter a question or SQL query'); return }

    setLoading(true)
    try {
      // Use the query endpoint to get a preview first
      const res = await api.post('/query', {
        connection_id:    selectedConnectionId,
        natural_language: mode === 'nl' ? text : `Execute this SQL: ${text}`,
      })
      const results = res.data?.results
      if (results?.rows?.length) {
        setPreview({ columns: results.columns, rows: results.rows.slice(0, 20) })
        toast.success(`${results.row_count} rows ready to export`)
      } else {
        toast.error('No data returned')
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Query failed')
    } finally {
      setLoading(false)
    }
  }

  const downloadCSV = async () => {
    if (!selectedConnectionId) return
    const text = mode === 'nl' ? question : rawSql
    if (!text.trim()) { toast.error('Run a query first'); return }

    setLoading(true)
    try {
      const endpoint = mode === 'nl' ? '/export/csv' : '/export/query-csv'
      const body = mode === 'nl'
        ? { connection_id: selectedConnectionId, natural_language: text, filename: filename || undefined }
        : { connection_id: selectedConnectionId, sql: text, filename: filename || undefined }

      const res = await api.post(endpoint, body, { responseType: 'blob' })

      // Get filename from header or use default
      const disposition = res.headers['content-disposition'] || ''
      const match       = disposition.match(/filename="(.+)"/)
      const fname       = match?.[1] || filename || 'export.csv'

      // Trigger browser download
      const url  = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href  = url
      link.setAttribute('download', fname)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      toast.success(`Downloaded ${fname}`)
    } catch (e: any) {
      toast.error('Export failed')
    } finally {
      setLoading(false)
    }
  }

  if (!selectedConnectionId) return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8 text-center">
      <Database size={40} className="text-muted" />
      <p className="text-muted text-sm">Select a database connection first</p>
      <Link href="/connections" className="px-4 py-2 bg-accent hover:bg-accent-hover rounded-lg text-sm">Go to Connections</Link>
    </div>
  )

  return (
    <div className="p-6 space-y-5 animate-fade-in max-w-4xl">
      <div>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <FileSpreadsheet size={20} className="text-accent" />
          Export to CSV
        </h1>
        <p className="text-muted text-sm mt-1">Ask a question or write SQL — preview and download as CSV</p>
      </div>

      {/* Mode toggle */}
      <div className="flex bg-surface-2 border border-border rounded-lg p-1 w-fit">
        {(['nl', 'sql'] as const).map(m => (
          <button key={m} onClick={() => { setMode(m); setPreview(null) }}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all
              ${mode === m ? 'bg-accent text-white' : 'text-muted hover:text-white'}`}>
            {m === 'nl' ? 'Natural language' : 'Raw SQL'}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="glass p-4 space-y-3">
        {mode === 'nl' ? (
          <div>
            <label className="block text-xs text-muted mb-2">Question</label>
            <textarea
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) runAndPreview() }}
              placeholder='e.g. "Show all customers who churned in the last 3 months"'
              rows={2}
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5
                         text-sm text-white placeholder-muted focus:outline-none
                         focus:border-accent resize-none transition-colors"
            />
          </div>
        ) : (
          <div>
            <label className="block text-xs text-muted mb-2">SQL Query</label>
            <textarea
              value={rawSql}
              onChange={e => setRawSql(e.target.value)}
              placeholder='SELECT * FROM customers WHERE churned = true LIMIT 1000'
              rows={4}
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5
                         text-sm text-white placeholder-muted focus:outline-none
                         focus:border-accent resize-none font-mono transition-colors"
            />
          </div>
        )}

        <div className="flex items-center gap-2">
          <div className="flex-1">
            <input
              value={filename}
              onChange={e => setFilename(e.target.value)}
              placeholder="Filename (optional) — defaults to query name"
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2
                         text-sm text-white placeholder-muted focus:outline-none
                         focus:border-accent transition-colors"
            />
          </div>
          <button onClick={runAndPreview} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-surface-3 hover:bg-surface-2
                       border border-border rounded-lg text-sm transition-all disabled:opacity-50">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
            Preview
          </button>
          <button onClick={downloadCSV} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                       rounded-lg text-sm transition-all disabled:opacity-50">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            Download CSV
          </button>
        </div>
      </div>

      {/* Preview */}
      {preview && (
        <div className="glass overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <span className="text-xs text-muted font-medium">
              Preview — first 20 rows · {preview.columns.length} columns
            </span>
            <button onClick={() => setShowPreview(!showPreview)}
              className="text-muted hover:text-white transition-colors">
              {showPreview ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>

          {showPreview && (
            <div className="overflow-x-auto max-h-80">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-surface-3">
                  <tr>
                    {preview.columns.map(c => (
                      <th key={c} className="px-3 py-2 text-left text-muted font-medium whitespace-nowrap border-b border-border">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i} className="border-b border-border hover:bg-surface-3 transition-colors">
                      {preview.columns.map(c => (
                        <td key={c} className="px-3 py-2 text-muted whitespace-nowrap max-w-xs truncate">
                          {String(row[c] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="px-4 py-2 border-t border-border flex justify-end">
            <button onClick={downloadCSV} disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover
                         rounded-lg text-xs transition-all disabled:opacity-50">
              <Download size={12} />
              Download full CSV
            </button>
          </div>
        </div>
      )}

      {/* Quick suggestions */}
      {!preview && (
        <div className="space-y-2">
          <p className="text-xs text-muted">Quick exports</p>
          <div className="grid grid-cols-2 gap-2">
            {QUICK_EXPORTS.map(q => (
              <button key={q} onClick={() => { setMode('nl'); setQuestion(q) }}
                className="glass text-left px-3 py-2.5 text-xs text-muted
                           hover:text-white hover:border-accent/40 transition-all rounded-lg">
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const QUICK_EXPORTS = [
  'All customers with their total revenue',
  'Customers who churned in the last 30 days',
  'Top 100 customers by order value',
  'Monthly revenue summary for this year',
  'All open support tickets with status',
  'Products with inventory below 10 units',
]
