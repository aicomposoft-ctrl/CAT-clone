import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'

const LoginPage = lazy(() => import('./pages/Auth/LoginPage'))
const DashboardPage = lazy(() => import('./pages/Dashboard'))
const ContentPage = lazy(() => import('./pages/Content'))
const DistributionPage = lazy(() => import('./pages/Distribution'))
const AlertsPage = lazy(() => import('./pages/Alerts'))
const PricesPage = lazy(() => import('./pages/Prices'))
const ReviewsPage = lazy(() => import('./pages/Reviews'))
const SettingsPage = lazy(() => import('./pages/Settings'))

const Fallback = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
    <Spin size="large" />
  </div>
)

export default function App() {
  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected — any authenticated user */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/content" element={<ContentPage />} />
            <Route path="/stock" element={<DistributionPage />} />
            <Route path="/prices" element={<PricesPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
          </Route>
        </Route>

        {/* Protected — admin + manager only */}
        <Route element={<ProtectedRoute allowedRoles={['admin', 'manager']} />}>
          <Route element={<AppLayout />}>
            <Route path="/settings/skus" element={<SettingsPage />} />
          </Route>
        </Route>

        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  )
}
