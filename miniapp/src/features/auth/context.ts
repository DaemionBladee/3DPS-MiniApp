import { createContext, useContext } from 'react'
import type { components } from '../../lib/api/schema'

export type AuthResponse = components['schemas']['AuthResponse']
export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error'

export interface AuthContextValue {
  status: AuthStatus
  session: AuthResponse | null
  error: string | null
  isLoggingOut: boolean
  refreshSession: () => void
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth requires AuthProvider')
  return auth
}
