import { useCallback, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest } from '../../lib/api/client'
import { useTelegram } from '../../integrations/telegram/TelegramProvider'
import { getRawTelegramInitData } from '../../integrations/telegram/init-data'
import { AuthContext, type AuthContextValue, type AuthResponse, type AuthStatus } from './context'

type AuthState = { status: AuthStatus; session: AuthResponse | null; error: string | null }
const initialState: AuthState = { status: 'loading', session: null, error: null }
const sessionEnded: AuthState = { status: 'unauthenticated', session: null, error: 'Your session ended. Close and reopen the Mini App in Telegram to sign in again.' }
const isUnauthorized = (error: unknown) => error instanceof ApiError && error.status === 401

/** A secure cookie is authoritative; CSRF and user data stay in memory only. */
export function AuthProvider({ children }: PropsWithChildren) {
  const telegram = useTelegram()
  const queryClient = useQueryClient()
  const [state, setState] = useState<AuthState>(initialState)
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const initialRequest = useRef<Promise<AuthResponse | null> | null>(null)
  const generation = useRef(0)
  const loginAttempted = useRef(false)
  const preventRelogin = useRef(false)

  const clearPrivateState = useCallback(() => {
    generation.current += 1
    preventRelogin.current = true
    void queryClient.cancelQueries()
    queryClient.clear()
    setState(sessionEnded)
  }, [queryClient])

  const restoreSession = useCallback(async (allowTelegramLogin: boolean): Promise<AuthResponse | null> => {
    try {
      return await apiRequest<AuthResponse>('/auth/me')
    } catch (error) {
      if (!isUnauthorized(error)) throw error
    }
    if (!allowTelegramLogin || preventRelogin.current || loginAttempted.current || telegram.source !== 'telegram') return null
    const raw = getRawTelegramInitData()
    if (!raw) return null
    loginAttempted.current = true
    // Exact raw bytes go to FastAPI. Only the backend validates proof/role.
    return apiRequest<AuthResponse>('/auth/telegram', { method: 'POST', body: JSON.stringify({ init_data: raw }) })
  }, [telegram.source])

  useEffect(() => {
    if (telegram.isInitializing) return
    if (import.meta.env.DEV && !import.meta.env.PROD && telegram.source === 'mock') {
      // An isolated UI preview has no authenticated server identity or session.
      setState({ status: 'unauthenticated', session: null, error: null })
      return
    }
    let active = true
    const currentGeneration = generation.current
    // Reuse one promise across React StrictMode's effect replay, so a single-use
    // Telegram proof is never submitted twice during one mounted provider.
    initialRequest.current ??= restoreSession(true)
    void initialRequest.current.then(session => {
      if (!active || currentGeneration !== generation.current) return
      setState(session ? { status: 'authenticated', session, error: null } : { status: 'unauthenticated', session: null, error: null })
    }).catch((error: unknown) => {
      if (!active || currentGeneration !== generation.current) return
      setState({ status: isUnauthorized(error) ? 'unauthenticated' : 'error', session: null,
        error: error instanceof ApiError ? error.message : 'Sign-in is unavailable. Please try again.' })
    })
    return () => { active = false }
  }, [telegram.isInitializing, telegram.source, restoreSession])

  useEffect(() => {
    const invalidate = () => clearPrivateState()
    window.addEventListener('3dps:session-expired', invalidate)
    return () => window.removeEventListener('3dps:session-expired', invalidate)
  }, [clearPrivateState])

  const refreshSession = useCallback(() => {
    if (import.meta.env.DEV && !import.meta.env.PROD && telegram.source === 'mock') return
    const currentGeneration = ++generation.current
    void queryClient.cancelQueries()
    queryClient.clear()
    setState(initialState)
    // Retry only a cookie session; a used/rejected launch proof requires a fresh
    // Telegram launch, not an automatic loop that re-submits signed credentials.
    void restoreSession(false).then(session => {
      if (currentGeneration !== generation.current) return
      if (!session) clearPrivateState()
      else setState({ status: 'authenticated', session, error: null })
    }).catch((error: unknown) => {
      if (currentGeneration !== generation.current) return
      setState({ status: 'error', session: null, error: error instanceof ApiError ? error.message : 'The service is unavailable. Please try again.' })
    })
  }, [telegram.source, restoreSession, clearPrivateState, queryClient])

  useEffect(() => {
    if (state.status !== 'authenticated') return
    const verifyCurrentSession = () => { if (document.visibilityState === 'visible') refreshSession() }
    document.addEventListener('visibilitychange', verifyCurrentSession)
    return () => document.removeEventListener('visibilitychange', verifyCurrentSession)
  }, [state.status, refreshSession])

  const logout = useCallback(async () => {
    if (!state.session || isLoggingOut) return
    generation.current += 1
    preventRelogin.current = true
    setIsLoggingOut(true)
    try {
      await apiRequest('/auth/logout', { method: 'POST', csrfToken: state.session.csrf_token })
      clearPrivateState()
    } catch (error) {
      if (isUnauthorized(error)) clearPrivateState()
      else setState(previous => ({ ...previous, error: error instanceof ApiError ? error.message : 'Sign-out failed. Please try again.' }))
    } finally { setIsLoggingOut(false) }
  }, [state.session, isLoggingOut, clearPrivateState])

  const value = useMemo<AuthContextValue>(() => ({ ...state, isLoggingOut, refreshSession, logout }), [state, isLoggingOut, refreshSession, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
