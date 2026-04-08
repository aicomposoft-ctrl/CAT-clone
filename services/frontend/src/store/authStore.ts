import { create } from 'zustand'
import { persist } from 'zustand/middleware'
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

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
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
    }),
    {
      name: 'cat-auth',
      // Persist only user info — access token stays in-memory for security.
      // On reload: user is restored → ProtectedRoute passes → first API call
      // gets 401 (no token) → interceptor uses sessionStorage refresh_token → new token set.
      partialize: (state) => ({ user: state.user }),
    }
  )
)
