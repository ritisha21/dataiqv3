'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, Database, MessageSquare,
  BrainCircuit, LogOut, Zap, ScanLine, Download
} from 'lucide-react'
import { useAuthStore } from '@/lib/store'
import { useRouter } from 'next/navigation'
import clsx from 'clsx'

const NAV = [
  { href: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard'   },
  { href: '/connections', icon: Database,         label: 'Connections' },
  { href: '/chat',        icon: MessageSquare,    label: 'Chat'        },
  { href: '/models',      icon: BrainCircuit,     label: 'Models'      },
  { href: '/etl',         icon: ScanLine,         label: 'ETL'         },
  { href: '/export',      icon: Download,         label: 'Export CSV'  },
]

export function Sidebar() {
  const pathname = usePathname()
  const { logout } = useAuthStore()
  const router     = useRouter()

  const handleLogout = () => { logout(); router.push('/auth') }

  return (
    <aside className="w-56 min-h-screen flex flex-col bg-surface-1 border-r border-border">
      {/* Logo */}
      <div className="p-5 flex items-center gap-2 border-b border-border">
        <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
          <Zap size={14} className="text-white" />
        </div>
        <span className="font-semibold text-sm tracking-wide">DataIQ</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, icon: Icon, label }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all',
              pathname.startsWith(href)
                ? 'bg-accent/15 text-accent font-medium'
                : 'text-muted hover:text-white hover:bg-surface-3'
            )}
          >
            <Icon size={16} />
            {label}
          </Link>
        ))}
      </nav>

      {/* Logout */}
      <div className="p-3 border-t border-border">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg
                     text-sm text-muted hover:text-white hover:bg-surface-3 transition-all"
        >
          <LogOut size={16} />
          Sign out
        </button>
      </div>
    </aside>
  )
}
