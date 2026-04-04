import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore, Role } from '../store/authStore'

interface Props {
  allowedRoles?: Role[]
}

/**
 * Route guard:
 * - Unauthenticated → redirect to /login
 * - Authenticated but wrong role → redirect to /dashboard
 * - Authenticated + allowed role → render children
 */
export const ProtectedRoute: React.FC<Props> = ({ allowedRoles }) => {
  const user = useAuthStore((s) => s.user)

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
