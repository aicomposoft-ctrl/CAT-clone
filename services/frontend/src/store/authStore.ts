import { create } from 'zustand'
import { QueryClient } from '@tanstack/react-query'

// Module-level queryClient reference — set once on app init via setQueryClient()
let _queryClient: QueryClient | null = null
export function setQueryClient(qc: QueryClient) { _queryClient = qc }

export type Role = 'admin' | 'manager' | 'viewer'

export interface AuthUser {
  id: string
  email: string
  role: Role
  org_id: string
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
  setAuth: (user: AuthUser, token: string) => void
  setAccessToken: (token: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,

  setAuth: (user, token) => set({ user, accessToken: token }),
  setAccessToken: (token) => set({ accessToken: token }),
  clearAuth: () => {
    sessionStorage.removeItem('refresh_token')
    set({ user: null, accessToken: null })
    // Clear React Query cache so stale org data is not shown to next user
    _queryClient?.clear()
  },
}))
