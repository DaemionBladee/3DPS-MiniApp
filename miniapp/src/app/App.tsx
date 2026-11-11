import { DesignPage } from '../features/design/DesignPage'
import { NewDesignRequest } from '../features/design/NewDesignRequest'
import { NewPrintRequest } from '../features/printing/NewPrintRequest'
import { PrintRequestPage } from '../features/printing/PrintRequestPage'
import { Component, useCallback, useEffect, type PropsWithChildren } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import CustomerDashboard from '../pages/CustomerDashboard'
import OwnerDashboard from '../pages/OwnerDashboard'
import NotFound from '../pages/NotFound'
import { useTelegramBackButton } from '../integrations/telegram/TelegramProvider'
import { PresentationGate } from './PresentationGate'
import { ServiceConnection } from './ServiceConnection'

class AppErrorBoundary extends Component<PropsWithChildren, { failed: boolean }> {
  override state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  // Do not log Telegram context, customer content or arbitrary error details.
  override componentDidCatch() { /* M01 has no telemetry sink. */ }
  override render() {
    if (this.state.failed) return <main className="entry-gate"><div className="entry-card" role="alert">
      <h1>Something went wrong.</h1><p>Reload the app to try again.</p>
      <button className="button button--primary" onClick={() => window.location.reload()}>Reload app</button>
    </div></main>
    return this.props.children
  }
}

function RoutePresentation() {
  const location = useLocation()
  const navigate = useNavigate()
  const goBack = useCallback(() => { void navigate(location.pathname.startsWith('/owner/') ? '/owner' : '/app') }, [navigate, location.pathname])
  useTelegramBackButton(location.pathname !== '/' && location.pathname !== '/app', goBack)
  useEffect(() => {
    document.title = location.pathname === '/owner' ? 'Owner workspace · 3DPS' : 'Your making space · 3DPS'
    document.getElementById('main-content')?.focus()
  }, [location.pathname])

  return <PresentationGate><Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate to="/app" replace />} />
      <Route path="app" element={<><CustomerDashboard /><ServiceConnection /></>} />
      <Route path="app/requests/new" element={<NewPrintRequest />} />
      <Route path="app/requests/design" element={<NewDesignRequest />} />
      <Route path="app/design-projects/:designId" element={<DesignPage />} />
      <Route path="app/design-requests/:requestId" element={<DesignPage />} />
      <Route path="owner/designs/:designId" element={<DesignPage owner />} />
      <Route path="owner/design-requests/:requestId" element={<DesignPage owner />} />
      <Route path="app/requests/print" element={<NewPrintRequest />} />
      <Route path="app/requests/:requestId" element={<PrintRequestPage />} />
      <Route path="owner/requests/:requestId" element={<PrintRequestPage owner />} />
      <Route path="owner" element={<><OwnerDashboard /><ServiceConnection /></>} />
      <Route path="*" element={<NotFound />} />
    </Route>
  </Routes></PresentationGate>
}

export function App() {
  return <AppErrorBoundary><RoutePresentation /></AppErrorBoundary>
}
