/**
 * Axios instance with JWT Bearer token injection and transparent refresh.
 *
 * Token storage:
 *   access_token  — Zustand in-memory only (cleared on page refresh)
 *   refresh_token — sessionStorage (per-tab, cleared on tab close)
 *
 * Race condition handled: concurrent 401s share a single refreshPromise so
 * only one POST /auth/refresh is made regardless of how many requests fail.
 */
import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

// Inject Bearer token on every request
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Singleton refresh promise — prevents duplicate refresh calls on concurrent 401s
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = sessionStorage.getItem('refresh_token')
  if (!refreshToken) {
    throw new Error('No refresh token')
  }

  const response = await axios.post<{ access_token: string }>(
    '/api/v1/auth/refresh',
    { refresh_token: refreshToken },
    { headers: { 'Content-Type': 'application/json' } },
  )
  const newToken = response.data.access_token
  useAuthStore.getState().setAccessToken(newToken)
  return newToken
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalConfig = error.config

    if (error.response?.status === 401 && !originalConfig._retry) {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null
        })
      }

      try {
        const newToken = await refreshPromise
        originalConfig._retry = true
        originalConfig.headers.Authorization = `Bearer ${newToken}`
        return apiClient(originalConfig)
      } catch {
        // Refresh failed — clear auth and redirect to login
        useAuthStore.getState().clearAuth()
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  },
)

export default apiClient
