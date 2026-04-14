/**
 * Auth hook — reads current user and role from Zustand authStore.
 */
import { useAuthStore } from '../store/authStore'

interface AuthState {
  userId: string
  orgId: string
  role: 'admin' | 'manager' | 'viewer'
}

export function useAuth(): AuthState {
  const user = useAuthStore((s) => s.user)
  if (!user) {
    return { userId: '', orgId: '', role: 'viewer' }
  }
  return {
    userId: user.id,
    orgId: user.org_id,
    role: user.role,
  }
}
