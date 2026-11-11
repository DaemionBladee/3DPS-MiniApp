import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env['CI'],
  retries: 0,
  workers: 2,
  reporter: 'list',
  use: {
    browserName: 'chromium',
    headless: true,
    trace: 'retain-on-failure',
    // Use Playwright's versioned browser by default; existing system Chromium
    // is an explicit supported fallback for restricted cloud workspaces.
    launchOptions: process.env['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']
      ? { executablePath: process.env['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] }
      : {},
  },
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      env: { VITE_TELEGRAM_MOCK: 'true' },
    },
    {
      command: 'npm run preview -- --outDir .production-check',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
    },
  ],
})
