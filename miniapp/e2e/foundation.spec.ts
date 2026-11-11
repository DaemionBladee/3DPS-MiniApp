import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  // Presentation tests need no external Telegram network or bot credentials.
  await page.route('https://telegram.org/**', route => route.fulfill({ contentType: 'application/javascript', body: '' }))
  // Browser auth gates use explicit denial fixtures. Backend proof validation has
  // separate PostgreSQL integration tests; these fixtures grant no real session.
  await page.route('**/api/v1/auth/**', route => route.fulfill({ status: 401, json: { code: 'unauthenticated' } }))
})

for (const viewport of [
  { width: 320, height: 780 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 1000 },
]) {
  test(`customer/owner navigation and themes at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto('http://127.0.0.1:5173/app')
    await expect(page.getByRole('heading', { name: 'Your next idea, made real.' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start a project' })).toBeDisabled()
    await expect(page.getByRole('heading', { name: 'Custom design' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Owner', exact: true }).click()
    await expect(page).toHaveURL(/\/owner$/)
    await expect(page.getByRole('heading', { name: 'Your workshop, at a glance.' })).toBeVisible()
    for (const name of ['Reviews', 'Payments', 'Production', 'Inventory']) {
      await expect(page.getByRole('heading', { name })).toBeVisible()
    }
    expect(await page.locator('.owner-intro > div').evaluate(element => element.getBoundingClientRect().width)).toBeGreaterThan(140)
    await page.getByRole('button', { name: 'Switch to dark theme' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Switch to light theme' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
    await page.getByRole('button', { name: 'Customer', exact: true }).click()
    await expect(page).toHaveURL(/\/app$/)
    expect(errors).toEqual([])
  })
}

test('connection loading, error and retry states are real transport states', async ({ page }) => {
  let requests = 0
  await page.route('**/api/v1/health', async route => {
    requests += 1
    if (requests === 1) {
      await route.fulfill({ status: 503, contentType: 'text/html', body: '<h1>Unavailable</h1>' })
    } else await route.fulfill({ json: { status: 'ok' } })
  })
  await page.goto('http://127.0.0.1:5173/app')
  await page.getByRole('button', { name: 'Check connection' }).click()
  await expect(page.getByRole('alert')).toContainText('Service not connected')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('status')).toContainText('Service reachable')
  expect(requests).toBe(2)
})

test('production rejects URL/storage role hints despite mock-enabled build environment', async ({ page }) => {
  const requests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/')) requests.push(request.url()) })
  await page.addInitScript(() => {
    localStorage.setItem('role', 'owner')
    localStorage.setItem('VITE_TELEGRAM_MOCK', 'true')
  })
  await page.goto('http://127.0.0.1:4173/owner?role=owner&mock=true')
  await expect(page.getByRole('heading', { name: 'Open in Telegram' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Preview workspace' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Your workshop, at a glance.' })).toHaveCount(0)
  expect(requests).toEqual(['http://127.0.0.1:4173/api/v1/auth/me'])
})

test('production Telegram appearance never grants a verified owner role', async ({ page }) => {
  await page.addInitScript(() => {
    // Synthetic SDK for presentation testing, not a signed/verified Telegram identity.
    Object.assign(window, { Telegram: { WebApp: {
      initData: 'unsigned-test-data', colorScheme: 'dark',
      themeParams: { bg_color: '#112233', text_color: '#ffffff' },
      safeAreaInset: { top: 20, bottom: 10 }, contentSafeAreaInset: { top: 12 },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
    } } })
  })
  await page.goto('http://127.0.0.1:4173/owner')
  await expect(page.getByRole('heading', { name: 'Sign-in required' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--tg-safe-area-inset-top'))).toBe('20px')
  await expect(page.getByRole('group', { name: 'Preview workspace' })).toHaveCount(0)
})

test('local preview supports keyboard navigation and does not silently add future screens', async ({ page }) => {
  await page.goto('http://127.0.0.1:5173/app')
  await page.getByRole('button', { name: 'Owner', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Your workshop, at a glance.' })).toBeVisible()
  await page.goto('http://127.0.0.1:5173/app/requests/new')
  await expect(page.getByRole('heading', { name: 'This idea hasn’t taken shape.' })).toBeVisible()
  await page.getByRole('link', { name: /overview|workspace|home/i }).first().click()
  await expect(page.getByRole('heading', { name: 'Your next idea, made real.' })).toBeVisible()
})


const serverSession = (role: 'customer' | 'owner') => ({
  user: { id: '00000000-0000-4000-8000-000000000001', telegram_id: '12345', display_name: 'Server account', role },
  capabilities: role === 'owner' ? ['auth.read_self', 'auth.logout', 'owner.auth_check'] : ['auth.read_self', 'auth.logout'],
  csrf_token: 'fixture-csrf-token', environment: 'simulation',
})

test('production customer cookie response cannot open the Owner workspace', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: serverSession('customer') }))
  await page.goto('http://127.0.0.1:4173/owner?role=owner')
  await expect(page.getByRole('heading', { name: 'Owner access required' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your workshop, at a glance.' })).toHaveCount(0)
  await page.getByRole('link', { name: 'Back to your workspace' }).click()
  await expect(page.getByRole('heading', { name: 'Your next idea, made real.' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Owner workspace' })).toHaveCount(0)
})

test('production server-provisioned Owner can navigate and sign out with CSRF', async ({ page }) => {
  let logoutRequests = 0
  let sessionChecks = 0
  await page.route('**/api/v1/auth/me', route => {
    sessionChecks += 1
    return route.fulfill({ json: serverSession('owner') })
  })
  await page.route('**/api/v1/auth/logout', async route => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().headers()['x-csrf-token']).toBe('fixture-csrf-token')
    logoutRequests += 1
    await route.fulfill({ status: 204 })
  })
  await page.goto('http://127.0.0.1:4173/app')
  await expect(page.getByText('Server account')).toBeVisible()
  await page.getByRole('link', { name: 'Owner workspace' }).click()
  await expect(page.getByRole('heading', { name: 'Your workshop, at a glance.' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Preview workspace' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Open in Telegram' })).toBeVisible()
  expect(logoutRequests).toBe(1)
  expect(sessionChecks).toBe(1)
})
