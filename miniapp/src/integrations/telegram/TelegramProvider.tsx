import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react'
import type { ColorScheme, MockRole, TelegramEvent, TelegramWebApp } from './types'

interface TelegramContextValue {
  source: 'browser' | 'telegram' | 'mock'
  mockRole: MockRole | null
  colorScheme: ColorScheme
  isInitializing: boolean
  setMockRole: (role: MockRole) => void
  toggleMockTheme: () => void
}

const TelegramContext = createContext<TelegramContextValue | null>(null)
const colorKeys = ['bg_color', 'text_color', 'hint_color', 'button_color', 'button_text_color', 'secondary_bg_color'] as const
const edges = ['top', 'right', 'bottom', 'left'] as const
const appearanceEvents: TelegramEvent[] = ['themeChanged', 'viewportChanged', 'safeAreaChanged', 'contentSafeAreaChanged']

function getTelegramApp(): TelegramWebApp | undefined {
  const app = window.Telegram?.WebApp
  // Presence is presentation context only. M02 must verify raw initData server-side.
  return app && typeof app.initData === 'string' && app.initData.length > 0 ? app : undefined
}

function systemColorScheme(): ColorScheme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function safePixels(value: number | undefined): string {
  return `${typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(value, 4096)) : 0}px`
}

function applyAppearance(app: TelegramWebApp | undefined, scheme: ColorScheme): void {
  const root = document.documentElement
  root.dataset.theme = scheme
  root.style.colorScheme = scheme
  for (const key of colorKeys) {
    const name = `--tg-theme-${key.replaceAll('_', '-')}`
    const value = app?.themeParams[key]
    // Telegram theme colors are hex values. Never interpolate arbitrary CSS.
    if (typeof value === 'string' && /^#[\da-f]{6}$/i.test(value)) root.style.setProperty(name, value)
    else root.style.removeProperty(name)
  }
  for (const edge of edges) {
    root.style.setProperty(`--tg-safe-area-inset-${edge}`, safePixels(app?.safeAreaInset?.[edge]))
    root.style.setProperty(`--tg-content-safe-area-inset-${edge}`, safePixels(app?.contentSafeAreaInset?.[edge]))
  }
  const height = app?.viewportStableHeight
  if (typeof height === 'number' && Number.isFinite(height) && height > 0) {
    root.style.setProperty('--tg-viewport-stable-height', safePixels(height))
  } else root.style.removeProperty('--tg-viewport-stable-height')
}

export function TelegramProvider({ children }: PropsWithChildren) {
  const [app] = useState(getTelegramApp)
  const [mockRole, updateMockRole] = useState<MockRole | null>(null)
  const [colorScheme, setColorScheme] = useState<ColorScheme>(() => app?.colorScheme === 'dark' ? 'dark' : app ? 'light' : systemColorScheme())
  const [isInitializing, setIsInitializing] = useState(
    () => import.meta.env.DEV && !import.meta.env.PROD && import.meta.env.VITE_TELEGRAM_MOCK === 'true' && !app,
  )
  const source: TelegramContextValue['source'] = app ? 'telegram' : mockRole ? 'mock' : 'browser'

  useEffect(() => {
    // The compile-time guard removes this import from every production bundle,
    // including a production build mistakenly given VITE_TELEGRAM_MOCK=true.
    if (import.meta.env.DEV && !import.meta.env.PROD && import.meta.env.VITE_TELEGRAM_MOCK === 'true' && !app) {
      let mounted = true
      void import('./mock').then(({ createMockAdapter }) => {
        if (!mounted) return
        updateMockRole(createMockAdapter().role)
        setIsInitializing(false)
      }).catch(() => {
        // A missing development chunk fails closed to the ordinary browser gate.
        if (mounted) setIsInitializing(false)
      })
      return () => { mounted = false }
    }
  }, [app])

  useEffect(() => {
    const root = document.documentElement
    const previousTheme = root.dataset.theme
    const previousColorScheme = root.style.colorScheme
    const properties = [
      ...colorKeys.map(key => `--tg-theme-${key.replaceAll('_', '-')}`),
      ...edges.flatMap(edge => [`--tg-safe-area-inset-${edge}`, `--tg-content-safe-area-inset-${edge}`]),
      '--tg-viewport-stable-height',
    ]
    const previousValues = properties.map(name => [name, root.style.getPropertyValue(name)] as const)
    applyAppearance(app, colorScheme)

    return () => {
      if (previousTheme === undefined) delete root.dataset.theme
      else root.dataset.theme = previousTheme
      root.style.colorScheme = previousColorScheme
      for (const [name, value] of previousValues) {
        if (value) root.style.setProperty(name, value)
        else root.style.removeProperty(name)
      }
    }
  }, [app, colorScheme])

  useEffect(() => {
    if (!app) return
    app.ready()
    app.expand()
    const update = () => {
      const nextScheme = app.colorScheme === 'dark' ? 'dark' : 'light'
      applyAppearance(app, nextScheme)
      setColorScheme(nextScheme)
    }
    for (const event of appearanceEvents) app.onEvent(event, update)
    return () => {
      for (const event of appearanceEvents) app.offEvent(event, update)
    }
  }, [app])

  useEffect(() => {
    if (app || mockRole) return
    const query = window.matchMedia?.('(prefers-color-scheme: dark)')
    const update = () => setColorScheme(query?.matches ? 'dark' : 'light')
    query?.addEventListener('change', update)
    return () => query?.removeEventListener('change', update)
  }, [app, mockRole])

  const setMockRole = useCallback((role: MockRole) => {
    if (import.meta.env.DEV && !import.meta.env.PROD && source === 'mock') updateMockRole(role)
  }, [source])
  const toggleMockTheme = useCallback(() => {
    if (import.meta.env.DEV && !import.meta.env.PROD && source === 'mock') {
      setColorScheme(previous => previous === 'dark' ? 'light' : 'dark')
    }
  }, [source])

  const value = useMemo<TelegramContextValue>(() => ({ source, mockRole, colorScheme, isInitializing, setMockRole, toggleMockTheme }), [source, mockRole, colorScheme, isInitializing, setMockRole, toggleMockTheme])
  return <TelegramContext.Provider value={value}>{children}</TelegramContext.Provider>
}

export function useTelegram(): TelegramContextValue {
  const value = useContext(TelegramContext)
  if (!value) throw new Error('useTelegram requires TelegramProvider')
  return value
}

export function useTelegramBackButton(canGoBack: boolean, onBack: () => void): void {
  const { source } = useTelegram()
  useEffect(() => {
    const button = source === 'telegram' ? getTelegramApp()?.BackButton : undefined
    if (!button) return
    if (canGoBack) {
      button.show()
      button.onClick(onBack)
    } else button.hide()
    return () => {
      if (canGoBack) button.offClick(onBack)
      button.hide()
    }
  }, [source, canGoBack, onBack])
}
