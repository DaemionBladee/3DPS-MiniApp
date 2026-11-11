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
  const initialRequest = useRef<{ key: string; promise: Promise<AuthResponse | null> } | null>(null)
  const refreshRequest = useRef<{ key: string; promise: Promise<AuthResponse | null> } | null>(null)
  const pendingLogins = useRef(new Map<string, Promise<AuthResponse>>())
  const retiredProofs = useRef(new Set<string>())
  const generation = useRef(0)
  const authEpoch = useRef(0)

  const clearPrivateState = useCallback(() => {
    generation.current += 1
    authEpoch.current += 1
    initialRequest.current = null
    refreshRequest.current = null
    void queryClient.cancelQueries()
    queryClient.clear()
    setState(sessionEnded)
  }, [queryClient])

  const restoreSession = useCallback(async (): Promise<AuthResponse | null> => {
    const launchAtStart = getRawTelegramInitData()
    try {
      const session = await apiRequest<AuthResponse>('/auth/me')
      // A successful cookie restoration must not later turn the same launch
      // into a new login after this session is expired or explicitly ended.
      if (launchAtStart) retiredProofs.current.add(launchAtStart)
      return session
    } catch (error) {
      if (!isUnauthorized(error)) throw error
    }
    if (telegram.source !== 'telegram') return null
    // Read the current SDK proof after the cookie check, not a captured initial
    // launch. A reused WebView may receive a genuinely fresh Telegram launch.
    const raw = getRawTelegramInitData()
    if (!raw) return null
    const key = `${authEpoch.current}:${raw}`
    const pending = pendingLogins.current.get(key)
    if (pending) return pending
    if (retiredProofs.current.has(raw)) return null
    retiredProofs.current.add(raw)
    // Exact raw bytes go to FastAPI once. Failed/ambiguous submissions remain
    // retired too: retry cookies or a fresh launch, never replay the credential.
    const login = apiRequest<AuthResponse>('/auth/telegram', { method: 'POST', body: JSON.stringify({ init_data: raw }) })
    pendingLogins.current.set(key, login)
    const forgetPending = () => { if (pendingLogins.current.get(key) === login) pendingLogins.current.delete(key) }
    void login.then(forgetPending, forgetPending)
    return login
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
    const key = `${telegram.source}:${getRawTelegramInitData() ?? ''}:${currentGeneration}`
    if (initialRequest.current?.key !== key) initialRequest.current = { key, promise: restoreSession() }
    void initialRequest.current.promise.then(session => {
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
    // Cookie restoration is always first. Only an unseen current launch may
    // then authenticate; attempted or explicitly logged-out proofs stay retired.
    const key = `${telegram.source}:${getRawTelegramInitData() ?? ''}:${authEpoch.current}`
    if (refreshRequest.current?.key !== key) {
      const request = { key, promise: restoreSession() }
      refreshRequest.current = request
      const forgetPending = () => { if (refreshRequest.current === request) refreshRequest.current = null }
      void request.promise.then(forgetPending, forgetPending)
    }
    void refreshRequest.current.promise.then(session => {
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
    authEpoch.current += 1
    initialRequest.current = null
    refreshRequest.current = null
    const currentProof = getRawTelegramInitData()
    if (currentProof) retiredProofs.current.add(currentProof)
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
