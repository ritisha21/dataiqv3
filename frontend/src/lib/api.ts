import axios from 'axios'
import Cookies from 'js-cookie'

const API_URL  = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const DEV_MODE = true

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  if (DEV_MODE) {
    // Send a dummy token — backend bypass ignores it entirely
    config.headers.Authorization = 'Bearer dev-bypass-token'
    return config
  }
  const token = Cookies.get('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (DEV_MODE) return Promise.reject(err)   // no refresh in dev mode
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = Cookies.get('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
            refresh_token: refresh,
          })
          Cookies.set('access_token',  data.access_token,  { expires: 1 / 48 })
          Cookies.set('refresh_token', data.refresh_token, { expires: 7 })
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          Cookies.remove('access_token')
          Cookies.remove('refresh_token')
          window.location.href = '/auth'
        }
      }
    }
    return Promise.reject(err)
  }
)

export const authApi = {
  register: (data: any) => api.post('/auth/register', data),
  login:    (data: any) => api.post('/auth/login',    data),
  refresh:  (token: string) => api.post('/auth/refresh', { refresh_token: token }),
}

export const connectionsApi = {
  connect:      (data: any)  => api.post('/connections/connect-db', data),
  list:         ()           => api.get('/connections/'),
  getSchema:    (id: string) => api.get(`/connections/${id}/schema`),
  getSemantic:  (id: string) => api.get(`/connections/${id}/semantic`),
  reIntrospect: (id: string) => api.post(`/connections/${id}/re-introspect`),
}

export const queryApi = {
  query: (data: { connection_id: string; natural_language: string }) =>
    api.post('/query', data),
  chat:  (data: { connection_id: string; message: string; stream?: boolean }) =>
    api.post('/chat', data),
}

export const modelsApi = {
  train:   (data: any)    => api.post('/models/train-model', data),
  list:    ()             => api.get('/models/'),
  get:     (id: string)   => api.get(`/models/${id}`),
  predict: (data: { model_id: string; input_data: Record<string, any> }) =>
    api.post('/models/predict', data),
}

export const dashboardApi = {
  getWidgets: (connectionId: string) =>
    api.get(`/dashboard/widgets?connection_id=${connectionId}`),
}
