'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { authApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'
import toast from 'react-hot-toast'
import { Zap, Loader2 } from 'lucide-react'

export default function LoginPage() {
  const router  = useRouter()
  const setAuth = useAuthStore(s => s.setAuth)

  const [tab, setTab]     = useState<'login' | 'register'>('login')
  const [loading, setLoading] = useState(false)
  const [form, setForm]   = useState({
    email: '', password: '', full_name: '',
    tenant_slug: '', tenant_name: '',
  })

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async () => {
    if (!form.email || !form.password || !form.tenant_slug) {
      toast.error('Fill all required fields'); return
    }
    setLoading(true)
    try {
      const fn   = tab === 'login' ? authApi.login : authApi.register
      const body = tab === 'login'
        ? { email: form.email, password: form.password, tenant_slug: form.tenant_slug }
        : { ...form }
      const { data } = await fn(body)
      setAuth(data)
      toast.success('Welcome!')
      router.push('/dashboard')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface p-4">
      <div className="w-full max-w-md glass p-8 space-y-6 animate-slide-up">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-accent rounded-xl flex items-center justify-center glow-accent">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <h1 className="font-semibold text-lg">DataIQ</h1>
            <p className="text-xs text-muted">Business Intelligence Platform</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex bg-surface-2 rounded-lg p-1">
          {(['login', 'register'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition-all capitalize
                ${tab === t ? 'bg-accent text-white' : 'text-muted hover:text-white'}`}>
              {t}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          {tab === 'register' && (
            <>
              <Input label="Full Name" value={form.full_name} onChange={set('full_name')} />
              <Input label="Company Name" value={form.tenant_name} onChange={set('tenant_name')} />
            </>
          )}
          <Input label="Workspace Slug" placeholder="acme-corp" value={form.tenant_slug} onChange={set('tenant_slug')} />
          <Input label="Email" type="email" value={form.email} onChange={set('email')} />
          <Input label="Password" type="password" value={form.password} onChange={set('password')} />
        </div>

        <button
          onClick={handleSubmit} disabled={loading}
          className="w-full py-3 bg-accent hover:bg-accent-hover disabled:opacity-50
                     rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          {tab === 'login' ? 'Sign in' : 'Create account'}
        </button>
      </div>
    </div>
  )
}

function Input({ label, ...props }: any) {
  return (
    <div>
      <label className="block text-xs text-muted mb-1">{label}</label>
      <input
        {...props}
        className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2.5
                   text-sm text-white placeholder-muted focus:outline-none focus:border-accent
                   transition-colors"
      />
    </div>
  )
}
