import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

const DistributionPage = lazy(() => import('./pages/Distribution'))

export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/distribution" element={<DistributionPage />} />
        <Route path="/" element={<Navigate to="/distribution" replace />} />
      </Routes>
    </Suspense>
  )
}
