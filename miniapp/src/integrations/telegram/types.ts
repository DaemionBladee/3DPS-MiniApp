export type ColorScheme = 'light' | 'dark'
export type MockRole = 'customer' | 'owner'

export interface SafeAreaInset {
  top?: number
  bottom?: number
  left?: number
  right?: number
}

export type TelegramEvent =
  | 'themeChanged'
  | 'viewportChanged'
  | 'safeAreaChanged'
  | 'contentSafeAreaChanged'

/** Only the presentation API used by M01; this is not a verified identity. */
export interface TelegramWebApp {
  initData: string
  colorScheme: ColorScheme
  themeParams: Record<string, string | undefined>
  safeAreaInset?: SafeAreaInset
  contentSafeAreaInset?: SafeAreaInset
  viewportStableHeight?: number
  ready(): void
  expand(): void
  onEvent(event: TelegramEvent, listener: () => void): void
  offEvent(event: TelegramEvent, listener: () => void): void
  BackButton?: {
    show(): void
    hide(): void
    onClick(listener: () => void): void
    offClick(listener: () => void): void
  }
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}
