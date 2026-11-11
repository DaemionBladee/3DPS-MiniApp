import type { MockRole } from './types'

/** Loaded only by a Vite development build with the explicit UI mock flag. */
export function createMockAdapter(): { role: MockRole; marker: string } {
  return { role: 'customer', marker: 'M01_DEV_UI_MOCK_ONLY' }
}
