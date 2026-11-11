import type { PropsWithChildren } from 'react'
import { Box, LockKeyhole } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useTelegram } from '../integrations/telegram/TelegramProvider'
import { useAuth } from '../features/auth/context'
import { ErrorState, LoadingState } from '../components/ui/States'
import { Button } from '../components/ui/Button'

/** UI navigation guard; every backend resource independently authorizes access. */
export function PresentationGate({ children }: PropsWithChildren) {
  const { source, isInitializing } = useTelegram()
  const auth = useAuth()
  const location = useLocation()
  if (isInitializing || (auth.status === 'loading' && source !== 'mock')) {
    return <main className="entry-gate"><LoadingState label="Checking your session…" /></main>
  }
  if (import.meta.env.DEV && !import.meta.env.PROD && source === 'mock') return children
  if (auth.status === 'authenticated' && auth.session) {
    if (location.pathname.startsWith('/owner') && auth.session.user.role !== 'owner') {
      return <main className="entry-gate"><ErrorState title="Owner access required" description="Your account can access its customer workspace. Owner actions require a provisioned Owner account." />
        <Link className="button button--primary" to="/app">Back to your workspace</Link>
      </main>
    }
    return children
  }

  return (
    <main className="entry-gate">
      <div className="entry-card">
        <div className="entry-brand"><Box aria-hidden="true" size={32} /><span>3DPS</span></div>
        <span className="entry-label">YOUR MAKING SPACE</span>
        <h1>{auth.status === 'error' ? 'Unable to sign in' : source === 'telegram' ? 'Sign-in required' : 'Open in Telegram'}</h1>
        <p>{auth.error ?? (source === 'telegram'
          ? 'Close and reopen the Mini App in Telegram to start a fresh, secure sign-in.'
          : '3DPS brings your printing and design projects together inside Telegram. Open this Mini App from the official bot to sign in securely.')}</p>
        {auth.status === 'error' && <Button variant="secondary" onClick={auth.refreshSession}>Check connection again</Button>}
        {auth.status === 'unauthenticated' && source === 'telegram' && <Button variant="secondary" onClick={auth.refreshSession}>Check sign-in again</Button>}
        <div className="entry-note"><LockKeyhole aria-hidden="true" size={18} /><span>No orders or payments are available in this preview.</span></div>
        {import.meta.env.DEV && !import.meta.env.PROD && (
          <p className="entry-dev-hint">Developing locally? Explicitly set VITE_TELEGRAM_MOCK=true and restart Vite to preview the two workspaces.</p>
        )}
      </div>
    </main>
  )
}
