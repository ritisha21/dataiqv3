import { create } from 'zustand'
import Cookies from 'js-cookie'

const DEV_MODE   = true
const DEV_TOKEN  = 'dev-bypass-token'
const DEV_USER   = {
  id:       '00000000-0000-0000-0000-000000000002',
  tenantId: '00000000-0000-0000-0000-000000000001',
  role:     'admin',
}

interface AuthState {
  user: { id: string; tenantId: string; role: string } | null
  isAuthenticated: boolean
  setAuth: (data: {
    access_token: string; refresh_token: string
    user_id: string; tenant_id: string; role: string
  }) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user:            DEV_MODE ? DEV_USER : null,
  isAuthenticated: DEV_MODE ? true : !!Cookies.get('access_token'),
  setAuth: (data) => {
    Cookies.set('access_token',  data.access_token,  { expires: 1 / 48 })
    Cookies.set('refresh_token', data.refresh_token, { expires: 7 })
    set({
      user: { id: data.user_id, tenantId: data.tenant_id, role: data.role },
      isAuthenticated: true,
    })
  },
  logout: () => {
    if (DEV_MODE) return
    Cookies.remove('access_token')
    Cookies.remove('refresh_token')
    set({ user: null, isAuthenticated: false })
  },
}))

interface ConnectionStore {
  selectedConnectionId: string | null
  setConnection: (id: string) => void
}

export const useConnectionStore = create<ConnectionStore>((set) => ({
  selectedConnectionId: null,
  setConnection: (id) => set({ selectedConnectionId: id }),
}))

// ETL state persisted across navigation
interface ETLStore {
  scanResult: { tables: any[]; suggestions: any[] } | null
  selected: Set<string>
  trainResults: any[]
  taskId: string | null
  expandedTable: string | null
  setScanResult: (r: { tables: any[]; suggestions: any[] } | null) => void
  setSelected: (s: Set<string>) => void
  setTrainResults: (r: any[]) => void
  setTaskId: (id: string | null) => void
  setExpandedTable: (t: string | null) => void
  resetETL: () => void
}

export const useETLStore = create<ETLStore>((set) => ({
  scanResult:    null,
  selected:      new Set(),
  trainResults:  [],
  taskId:        null,
  expandedTable: null,
  setScanResult:    (r) => set({ scanResult: r }),
  setSelected:      (s) => set({ selected: s }),
  setTrainResults:  (r) => set({ trainResults: r }),
  setTaskId:        (id) => set({ taskId: id }),
  setExpandedTable: (t) => set({ expandedTable: t }),
  resetETL: () => set({ scanResult: null, selected: new Set(), trainResults: [], taskId: null, expandedTable: null }),
}))