/**
 * Auth hook — reads JWT claims from localStorage.
 * Returns role, userId, orgId. Redirects to /login if token is absent.
 */

interface AuthState {
  userId: string
  orgId: string
  role: 'admin' | 'manager' | 'viewer'
}

function parseJwt(token: string): Record<string, unknown> {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return {}
  }
}

export function useAuth(): AuthState {
  const token = localStorage.getItem('access_token')
  if (!token) {
    window.location.href = '/login'
    return { userId: '', orgId: '', role: 'viewer' }
  }
  const claims = parseJwt(token)
  // Redirect on expiry so the UI never shows restricted controls for expired sessions.
  const exp = claims.exp as number | undefined
  if (exp && Date.now() / 1000 > exp) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    return { userId: '', orgId: '', role: 'viewer' }
  }
  return {
    userId: (claims.sub as string) ?? '',
    orgId: (claims.org_id as string) ?? '',
    role: (claims.role as AuthState['role']) ?? 'viewer',
  }
}
