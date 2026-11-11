import { ArrowUpRight, Box, CircleHelp, LayoutDashboard, Moon, ShieldCheck, Sun } from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useTelegram } from '../../integrations/telegram/TelegramProvider'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { useAuth } from '../../features/auth/context'

export function AppShell() {
  const telegram = useTelegram()
  const auth = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const ownerView = location.pathname === '/owner' || location.pathname.startsWith('/owner/')

  function switchWorkspace(role: 'customer' | 'owner') {
    telegram.setMockRole(role)
    void navigate(role === 'owner' ? '/owner' : '/app')
  }

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to content</a>
      {telegram.source === 'mock' && (
        <div className="preview-bar">
          <span><span className="preview-dot" />Development preview <span className="preview-detail">· no real orders or payments</span></span>
          <div className="preview-controls">
            <div className="role-switch" role="group" aria-label="Preview workspace">
              <button type="button" aria-pressed={!ownerView} onClick={() => switchWorkspace('customer')}>Customer</button>
              <button type="button" aria-pressed={ownerView} onClick={() => switchWorkspace('owner')}>Owner</button>
            </div>
            <Button variant="ghost" className="theme-button" onClick={telegram.toggleMockTheme} aria-label={`Switch to ${telegram.colorScheme === 'light' ? 'dark' : 'light'} theme`}>
              {telegram.colorScheme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
            </Button>
          </div>
        </div>
      )}
      <div className="workspace-layout">
        <aside className="sidebar" aria-label="Workspace navigation">
          <NavLink className="brand" to={ownerView ? '/owner' : '/app'} aria-label="3DPS home">
            <span className="brand-mark"><Box size={26} strokeWidth={1.6} aria-hidden="true" /></span>
            <span>3DPS<span className="brand-subtitle">PRINT & DESIGN STUDIO</span></span>
          </NavLink>
          <p className="sidebar-label">{ownerView ? 'YOUR WORKSHOP' : 'YOUR WORKSPACE'}</p>
          <nav className="primary-nav" aria-label="Main navigation">
            {auth.status === 'authenticated' && auth.session?.user.role === 'owner' && (
              <NavLink to={ownerView ? '/app' : '/owner'} className="nav-item">{ownerView ? 'Customer workspace' : 'Owner workspace'}</NavLink>
            )}
            <NavLink end to={ownerView ? '/owner' : '/app'} className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}>
              <LayoutDashboard size={19} aria-hidden="true" />Overview<span className="nav-active-dot" />
            </NavLink>
          </nav>
          <div className="sidebar-note">
            <span className="sidebar-note__icon"><ShieldCheck size={20} aria-hidden="true" /></span>
            <strong>A thoughtful start.</strong>
            <p>We’re building a better way to bring your ideas into the real world.</p>
            <Badge>Prelaunch</Badge>
          </div>
          <div className="sidebar-footer"><Box size={15} aria-hidden="true" /><span>Ideas, made tangible.</span></div>
        </aside>
        <div className="workspace-body">
          <header className="workspace-header">
            <span className="workspace-crumb"><span className="desktop-label">Workspace<span className="crumb-slash">/</span></span>{ownerView ? 'Owner overview' : 'Customer overview'}</span>
            <div className="workspace-identity"><span className="avatar" aria-hidden="true">{auth.session?.user.display_name.slice(0, 1) || (ownerView ? 'O' : 'C')}</span><span>{auth.session?.user.display_name ?? (ownerView ? 'Owner' : 'Customer')}</span>
              {auth.status === 'authenticated' && <Button variant="secondary" disabled={auth.isLoggingOut} onClick={() => { void auth.logout() }}>{auth.isLoggingOut ? 'Signing out…' : 'Sign out'}</Button>}
            </div>
          </header>
          {auth.status === 'authenticated' && auth.error && <p className="session-error" role="alert">{auth.error}</p>}
          <main id="main-content" className="main-content" tabIndex={-1}>
            <Outlet />
          </main>
          <footer className="workspace-footer">
            <span>3DPS · Print & design, thoughtfully.</span>
            <span><CircleHelp size={14} aria-hidden="true" />Ordering opens in a later release.<ArrowUpRight size={13} aria-hidden="true" /></span>
          </footer>
        </div>
      </div>
    </div>
  )
}
