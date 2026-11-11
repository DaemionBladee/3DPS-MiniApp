/** Raw launch proof only. This function never parses a user or grants a role. */
export function getRawTelegramInitData(): string | null {
  const raw = window.Telegram?.WebApp?.initData
  return typeof raw === 'string' && raw.length > 0 ? raw : null
}
