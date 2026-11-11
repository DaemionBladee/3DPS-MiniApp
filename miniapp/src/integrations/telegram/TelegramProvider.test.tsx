import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TelegramProvider, useTelegram, useTelegramBackButton } from './TelegramProvider'
import type { TelegramEvent, TelegramWebApp } from './types'

function PresentationProbe() {
  const { source, mockRole, colorScheme, isInitializing, setMockRole, toggleMockTheme } = useTelegram()
  return <>
    <output aria-label="source">{source}</output>
    <output aria-label="role">{mockRole ?? 'none'}</output>
    <output aria-label="theme">{colorScheme}</output>
    <output aria-label="initializing">{String(isInitializing)}</output>
    <button onClick={() => setMockRole('owner')}>Select owner presentation</button>
    <button onClick={toggleMockTheme}>Toggle mock theme</button>
  </>
}

function makeApp() {
  const listeners = new Map<TelegramEvent, () => void>()
  const app: TelegramWebApp = {
    initData: 'presentation-context-only',
    colorScheme: 'light',
    themeParams: { bg_color: '#ffffff', text_color: '#112233', hint_color: 'url(https://invalid.example)' },
    safeAreaInset: { top: 24, bottom: 12 },
    contentSafeAreaInset: { top: 16, left: -20, right: Number.NaN },
    viewportStableHeight: 700,
    ready: vi.fn(),
    expand: vi.fn(),
    onEvent: vi.fn((event, listener) => { listeners.set(event, listener) }),
    offEvent: vi.fn((event) => { listeners.delete(event) }),
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
  }
  return { app, listeners }
}

beforeEach(() => {
  vi.stubEnv('VITE_TELEGRAM_MOCK', '')
  delete window.Telegram
  document.documentElement.removeAttribute('style')
  delete document.documentElement.dataset.theme
})

afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  delete window.Telegram
})

describe('Telegram presentation context', () => {
  it('does not enable a browser role implicitly or accept a browser role hint', () => {
    window.history.replaceState(null, '', '/owner?role=owner&mock=true')
    render(<TelegramProvider><PresentationProbe /></TelegramProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Select owner presentation' }))
    expect(screen.getByLabelText('source')).toHaveTextContent('browser')
    expect(screen.getByLabelText('role')).toHaveTextContent('none')
    expect(screen.getByLabelText('initializing')).toHaveTextContent('false')
    window.history.replaceState(null, '', '/')
  })

  it('loads an explicit development UI mock and can change its presentation only', async () => {
    vi.stubEnv('VITE_TELEGRAM_MOCK', 'true')
    render(<TelegramProvider><PresentationProbe /></TelegramProvider>)
    expect(await screen.findByText('mock', { selector: 'output' })).toBeInTheDocument()
    expect(screen.getByLabelText('role')).toHaveTextContent('customer')
    const initialTheme = screen.getByLabelText('theme').textContent
    fireEvent.click(screen.getByRole('button', { name: 'Select owner presentation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Toggle mock theme' }))
    expect(screen.getByLabelText('role')).toHaveTextContent('owner')
    expect(screen.getByLabelText('theme').textContent).not.toBe(initialTheme)
    expect(screen.getByLabelText('initializing')).toHaveTextContent('false')
  })

  it('rejects mock configuration in production even if the mock flag is true', () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('PROD', true)
    vi.stubEnv('VITE_TELEGRAM_MOCK', 'true')
    render(<TelegramProvider><PresentationProbe /></TelegramProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Select owner presentation' }))
    expect(screen.getByLabelText('source')).toHaveTextContent('browser')
    expect(screen.getByLabelText('role')).toHaveTextContent('none')
    expect(screen.getByLabelText('initializing')).toHaveTextContent('false')
  })

  it('uses Telegram appearance without interpreting it as a verified role', () => {
    const { app, listeners } = makeApp()
    window.Telegram = { WebApp: app }
    vi.stubEnv('VITE_TELEGRAM_MOCK', 'true')
    const { unmount } = render(<TelegramProvider><PresentationProbe /></TelegramProvider>)
    expect(screen.getByLabelText('source')).toHaveTextContent('telegram')
    fireEvent.click(screen.getByRole('button', { name: 'Select owner presentation' }))
    expect(screen.getByLabelText('role')).toHaveTextContent('none')
    expect(app.ready).toHaveBeenCalledOnce()
    expect(app.expand).toHaveBeenCalledOnce()
    const root = document.documentElement
    expect(root.style.getPropertyValue('--tg-theme-bg-color')).toBe('#ffffff')
    expect(root.style.getPropertyValue('--tg-theme-hint-color')).toBe('')
    expect(root.style.getPropertyValue('--tg-safe-area-inset-top')).toBe('24px')
    expect(root.style.getPropertyValue('--tg-content-safe-area-inset-top')).toBe('16px')
    expect(root.style.getPropertyValue('--tg-content-safe-area-inset-left')).toBe('0px')
    expect(root.style.getPropertyValue('--tg-content-safe-area-inset-right')).toBe('0px')
    expect(root.style.getPropertyValue('--tg-viewport-stable-height')).toBe('700px')
    act(() => {
      app.colorScheme = 'dark'
      app.themeParams.bg_color = '#112233'
      listeners.get('themeChanged')?.()
    })
    expect(screen.getByLabelText('theme')).toHaveTextContent('dark')
    expect(root.dataset.theme).toBe('dark')
    expect(root.style.getPropertyValue('--tg-theme-bg-color')).toBe('#112233')
    act(() => {
      app.safeAreaInset = { top: 44 }
      listeners.get('safeAreaChanged')?.()
    })
    expect(root.style.getPropertyValue('--tg-safe-area-inset-top')).toBe('44px')
    expect(listeners.size).toBe(4)
    unmount()
    expect(app.offEvent).toHaveBeenCalledTimes(4)
    expect(listeners.size).toBe(0)
    expect(root.dataset.theme).toBeUndefined()
    expect(root.style.getPropertyValue('--tg-safe-area-inset-top')).toBe('')
  })

  it('does not treat merely loading the SDK in a browser as a Telegram launch', () => {
    const { app } = makeApp()
    app.initData = ''
    window.Telegram = { WebApp: app }
    render(<TelegramProvider><PresentationProbe /></TelegramProvider>)
    expect(screen.getByLabelText('source')).toHaveTextContent('browser')
    expect(app.ready).not.toHaveBeenCalled()
  })

  it('follows browser appearance changes and removes the media listener', () => {
    let listener: (() => void) | undefined
    const mediaQuery = {
      matches: false,
      addEventListener: vi.fn((_event: string, callback: () => void) => { listener = callback }),
      removeEventListener: vi.fn(),
    }
    vi.spyOn(window, 'matchMedia').mockReturnValue(mediaQuery as unknown as MediaQueryList)
    const { unmount } = render(<TelegramProvider><PresentationProbe /></TelegramProvider>)
    expect(screen.getByLabelText('theme')).toHaveTextContent('light')
    act(() => {
      mediaQuery.matches = true
      listener?.()
    })
    expect(screen.getByLabelText('theme')).toHaveTextContent('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    unmount()
    expect(mediaQuery.removeEventListener).toHaveBeenCalledWith('change', listener)
  })
})

describe('Telegram native back button', () => {
  it('subscribes only while navigation can go back and cleans up', () => {
    const { app } = makeApp()
    const onBack = vi.fn()
    window.Telegram = { WebApp: app }
    function NavigationProbe({ canGoBack }: { canGoBack: boolean }) {
      useTelegramBackButton(canGoBack, onBack)
      return null
    }
    const { rerender, unmount } = render(<TelegramProvider><NavigationProbe canGoBack /></TelegramProvider>)
    expect(app.BackButton?.show).toHaveBeenCalledOnce()
    expect(app.BackButton?.onClick).toHaveBeenCalledWith(onBack)
    rerender(<TelegramProvider><NavigationProbe canGoBack={false} /></TelegramProvider>)
    expect(app.BackButton?.offClick).toHaveBeenCalledWith(onBack)
    expect(app.BackButton?.hide).toHaveBeenCalled()
    unmount()
  })
})
