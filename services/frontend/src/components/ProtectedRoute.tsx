import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore, Role } from '../store/authStore'

interface Props {
  allowedRoles?: Role[]
}

/**
 * Route guard:
 * - Waiting for persist hydration → spinner (avoids false redirect to /login)
 * - Unauthenticated → redirect to /login
 * - Authenticated but wrong role → redirect to /dashboard
 * - Authenticated + allowed role → render children
 */
export const ProtectedRoute: React.FC<Props> = ({ allowedRoles }) => {
  const user = useAuthStore((s) => s.user)
  const [hydrated, setHydrated] = useState(
    () => useAuthStore.persist.hasHydrated()
  )

  useEffect(() => {
    if (!hydrated) {
      const unsub = useAuthStore.persist.onFinishHydration(() => setHydrated(true))
      // In case hydration finished before we subscribed
      if (useAuthStore.persist.hasHydrated()) setHydrated(true)
      return unsub
    }
  }, [hydrated])

  if (!hydrated) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
