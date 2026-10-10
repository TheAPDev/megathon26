import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ApiError } from './api/client'
import { useConfig } from './api/hooks'
import { initAuth } from './auth/auth'
import { Layout } from './components/Layout'
import { ErrorState, Loading } from './components/ui'
import { Dashboard } from './screens/Dashboard'
import { useSession } from './state/session'

// Screens other than the dashboard load on demand.
const Studio = lazy(() => import('./screens/Studio'))
const Paisa = lazy(() => import('./screens/Paisa'))
const Saathi = lazy(() => import('./screens/Saathi'))
const Portfolio = lazy(() => import('./screens/Portfolio'))
const BillToScore = lazy(() => import('./screens/BillToScore'))
const Garmi = lazy(() => import('./screens/Garmi'))
const Login = lazy(() => import('./screens/Login'))

export function App() {
  const cfg = useConfig()
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (cfg.data) initAuth(cfg.data).finally(() => setReady(true))
  }, [cfg.data])
  if (cfg.error) return <div className="page"><ErrorState error={cfg.error} onRetry={() => cfg.refetch()} /></div>
  if (!ready) return <div className="page" style={{ paddingTop: 48 }}><Loading lines={4} label="Starting Green Ghar" /></div>
  return (
    <BrowserRouter basename="/app">
      <Suspense fallback={<div className="page"><Loading lines={4} /></div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route index element={<RequireHome><Dashboard /></RequireHome>} />
            <Route path="bill" element={<BillToScore />} />
            <Route path="studio" element={<RequireHome><Studio /></RequireHome>} />
            <Route path="paisa" element={<RequireHome><Paisa /></RequireHome>} />
            <Route path="saathi" element={<RequireHome><Saathi /></RequireHome>} />
            <Route path="garmi" element={<RequireHome><Garmi /></RequireHome>} />
            <Route path="portfolio" element={<RequireAnalyst><Portfolio /></RequireAnalyst>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const mode = useSession((s) => s.authMode)
  const user = useSession((s) => s.user)
  if (mode === 'supabase' && !user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname.replace(/^\/app/, '') || '/')}`} replace />
  return <>{children}</>
}

function RequireHome({ children }: { children: ReactNode }) {
  const id = useSession((s) => s.activeHomeId)
  if (!id) return <Navigate to="/bill?first=1" replace />
  return <>{children}</>
}

function RequireAnalyst({ children }: { children: ReactNode }) {
  const mode = useSession((s) => s.authMode)
  const role = useSession((s) => s.user?.role)
  if (mode !== 'demo' && role !== 'analyst')
    return <ErrorState error={new ApiError(403, 'forbidden', 'The lender portfolio needs an analyst account. Sign in with your bank login.')} />
  return <>{children}</>
}
