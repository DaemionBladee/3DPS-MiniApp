/* global window, document */
import assert from 'node:assert/strict'
import { runOpaqueOriginIntegration } from './ios-auth-integration.mjs'
import { runPricingIntegration } from './pricing-integration.mjs'
import { runAnalysisIntegration } from './analysis-integration.mjs'
import { runDesignIntegration } from './design-integration.mjs'
import { spawn, spawnSync } from 'node:child_process'
import { createHmac, randomBytes, randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import http from 'node:http'
import https from 'node:https'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, expect } from '@playwright/test'

const frontend = fileURLToPath(new URL('..', import.meta.url))
const backendDirectory = path.resolve(frontend, '../backend')
const dist = path.join(frontend, 'dist')
const apiPort = 18002
const gatewayPort = 18443
const origin = `https://127.0.0.1:${gatewayPort}`
const syntheticBotToken = 'm02-integration-synthetic-bot-token'
const cookieName = '__Host-3dps_session'
// Test harness only: a caller-owned image may replace the local Python child.
// The API address remains fixed to loopback; never select a remote/live API.
const useContainerApi = process.env.TEST_CONTAINER_API === 'true'
// Only boolean/count evidence is retained; never record header values or bodies.
const opaqueRequests = { login: 0, csrfMutations: 0 }

function safeDatabaseUrl() {
  const value = process.env.TEST_BROWSER_DATABASE_URL
  assert(value, 'Set TEST_BROWSER_DATABASE_URL to an already-migrated disposable browser-test database.')
  let url
  try { url = new URL(value) } catch { throw new Error('The browser-test database URL is malformed.') }
  assert(url.protocol === 'postgresql+asyncpg:', 'Browser integration requires PostgreSQL asyncpg.')
  assert(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname), 'Browser-test database must use a loopback host.')
  assert(/^\/3dps_test_browser(?:_[a-z0-9]+)?$/.test(url.pathname), 'Refusing a database outside the dedicated 3dps_test_browser namespace.')
  assert(!url.search && !url.hash, 'Browser-test database URL must not contain routing overrides.')
  return value
}

async function assertPortFree(port) {
  const probe = net.createServer()
  await new Promise((resolve, reject) => {
    probe.once('error', () => reject(new Error(`Required local test port ${port} is already in use.`)))
    probe.listen(port, '127.0.0.1', resolve)
  })
  await new Promise(resolve => probe.close(resolve))
}

function signedLaunch(telegramId, forged = false) {
  // Sign in Node, outside the browser. Only raw signed initData reaches React.
  const fields = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: randomUUID(),
    user: JSON.stringify({ id: telegramId, first_name: telegramId === 111 ? 'Owner Fixture' : 'Customer Fixture' }),
  }
  const dataCheckString = Object.keys(fields).sort().map(key => `${key}=${fields[key]}`).join('\n')
  const secret = createHmac('sha256', 'WebAppData').update(syntheticBotToken).digest()
  let hash = createHmac('sha256', secret).update(dataCheckString).digest('hex')
  if (forged) hash = `${hash.slice(0, -1)}${hash.endsWith('0') ? '1' : '0'}`
  return new URLSearchParams({ ...fields, hash }).toString()
}

async function installTelegramPresentation(context, initData) {
  // The only intercepted network destination is the external presentation SDK.
  // Every /api request uses the actual FastAPI server and PostgreSQL database.
  await context.route('https://telegram.org/**', route => route.fulfill({ contentType: 'application/javascript', body: '' }))
  await context.addInitScript(raw => {
    window.Telegram = { WebApp: {
      initData: raw,
      colorScheme: 'light',
      themeParams: {},
      ready() {},
      expand() {},
      onEvent() {},
      offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    } }
  }, initData)
}

async function waitForBackend(child) {
  // Leave room for the final bounded probe inside the 15-second startup budget.
  const deadline = Date.now() + 14_000
  while (Date.now() < deadline) {
    if (child && (child.exitCode !== null || child.signalCode !== null)) throw new Error('The disposable backend exited before readiness.')
    try {
      const response = await fetch(`http://127.0.0.1:${apiPort}/api/v1/health`, { signal: AbortSignal.timeout(750) })
      if (response.ok && (await response.json()).status === 'ok') return
    } catch { /* The process may still be starting. */ }
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw new Error('The disposable FastAPI server did not become ready within 15 seconds.')
}

async function createGateway(directory) {
  const keyFile = path.join(directory, 'loopback-test-key.pem')
  const certificateFile = path.join(directory, 'loopback-test-certificate.pem')
  const generated = spawnSync('openssl', [
    'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', keyFile,
    '-out', certificateFile, '-days', '1', '-subj', '/CN=127.0.0.1',
    '-addext', 'subjectAltName=IP:127.0.0.1',
  ], { stdio: 'ignore', timeout: 10_000 })
  assert(!generated.error && generated.status === 0, 'OpenSSL must generate the ephemeral loopback TLS certificate.')
  const server = https.createServer({ key: await readFile(keyFile), cert: await readFile(certificateFile) }, (request, response) => {
    if (request.url?.startsWith('/api/')) {
      if (request.headers.origin === 'null') {
        if (request.method === 'POST' && request.url === '/api/v1/auth/telegram') opaqueRequests.login += 1
        else if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method) && request.headers['x-csrf-token']) opaqueRequests.csrfMutations += 1
      }
      const upstream = http.request({
        hostname: '127.0.0.1', port: apiPort, method: request.method,
        path: request.url, headers: { ...request.headers, host: `127.0.0.1:${gatewayPort}` },
      }, upstreamResponse => {
        response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers)
        upstreamResponse.pipe(response)
      })
      upstream.on('error', () => {
        if (!response.headersSent) response.writeHead(502)
        response.end()
      })
      request.pipe(upstream)
      return
    }
    void (async () => {
      let pathname
      try { pathname = decodeURIComponent(new URL(request.url ?? '/', origin).pathname) } catch {
        response.writeHead(400).end()
        return
      }
      let file = path.resolve(dist, `.${pathname}`)
      if (file !== dist && !file.startsWith(`${dist}${path.sep}`)) {
        response.writeHead(404).end()
        return
      }
      try {
        if (!(await stat(file)).isFile()) file = path.join(dist, 'index.html')
      } catch {
        if (path.extname(pathname)) { response.writeHead(404).end(); return }
        file = path.join(dist, 'index.html')
      }
      const contentType = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }[path.extname(file)] ?? 'application/octet-stream'
      response.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' })
      response.end(request.method === 'HEAD' ? undefined : await readFile(file))
    })().catch(() => { if (!response.headersSent) response.writeHead(500); response.end() })
  })
  await new Promise((resolve, reject) => {
    server.once('error', () => reject(new Error('Could not start the ephemeral HTTPS loopback gateway.')))
    server.listen(gatewayPort, '127.0.0.1', resolve)
  })
  return server
}

async function stopBackend(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return
  child.kill('SIGTERM')
  await Promise.race([
    new Promise(resolve => child.once('exit', resolve)),
    new Promise(resolve => setTimeout(resolve, 3000)),
  ])
  if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL')
}

let directory
let backend
let gateway
let browser
try {
  const databaseUrl = safeDatabaseUrl()
  assert(existsSync(path.join(dist, 'index.html')), 'Build the actual production frontend before this integration test.')
  if (!useContainerApi) {
    assert(existsSync(path.join(backendDirectory, '.venv/bin/python')), 'Install the backend test environment first.')
    await assertPortFree(apiPort)
  }
  await assertPortFree(gatewayPort)
  directory = await mkdtemp(path.join(os.tmpdir(), '3dps-m04-browser-'))
  if (!useContainerApi) {
    backend = spawn(path.join(backendDirectory, '.venv/bin/python'), [
      '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1',
      '--port', String(apiPort), '--no-proxy-headers', '--no-access-log',
    ], {
      cwd: backendDirectory,
      env: {
        ...process.env,
        PYTHONPATH: `${backendDirectory}:${path.dirname(backendDirectory)}`,
        APP_ENV: 'test', DATABASE_URL: databaseUrl, BOT_TOKEN: syntheticBotToken,
        SESSION_SECRET: randomBytes(32).toString('base64url'), OWNER_TELEGRAM_IDS: '111',
        STORAGE_ROOT: path.join(directory, 'private-models'),
        PUBLIC_BASE_URL: origin, SIMULATION_MODE: 'true', DEVELOPMENT_AUTH_ENABLED: 'false',
        BINDING_QUOTES_ENABLED: 'false', AUTO_QUOTE_ENABLED: 'false', PAYMENT_POLICY_APPROVED: 'false',
        LIVE_PAYMENTS_ENABLED: 'false', REAL_PRINTING_ENABLED: 'false', AUTH_RATE_LIMIT: '100',
      },
      stdio: ['ignore', 'ignore', 'pipe'],
    })
    // Never echo child logs, signed launch data, cookies or configured secrets.
    backend.stderr.resume()
    backend.on('error', () => { /* Readiness produces a safe diagnostic. */ })
  }
  await waitForBackend(backend)
  gateway = await createGateway(directory)
  browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
  })

  // The single self-signed test certificate is accepted only by these ephemeral
  // browser contexts. Package installation and other TLS verification stay on.
  const customer = await browser.newContext({ ignoreHTTPSErrors: true })
  const customerProof = signedLaunch(222)
  await installTelegramPresentation(customer, customerProof)
  // The HTTPS gateway must preserve Origin enforcement, including for an
  // otherwise valid unused proof. A rejected browser origin consumes no proof.
  for (const invalidOrigin of ['https://untrusted.example']) {
    const rejected = await customer.request.post(`${origin}/api/v1/auth/telegram`, {
      headers: { Origin: invalidOrigin }, data: { init_data: customerProof },
    })
    assert(rejected.status() === 403, 'HTTPS proxy must not permit login from an untrusted Origin.')
  }
  const crossSiteOpaque = await customer.request.post(`${origin}/api/v1/auth/telegram`, {
    headers: { Origin: 'null', 'Sec-Fetch-Site': 'cross-site' }, data: { init_data: customerProof },
  })
  assert(crossSiteOpaque.status() === 403, 'Opaque Origin must never override hostile Fetch Metadata.')
  const missingOrigin = await customer.request.post(`${origin}/api/v1/auth/telegram`, { data: { init_data: customerProof } })
  assert(missingOrigin.status() === 403, 'HTTPS proxy must not permit login with missing Origin.')
  const page = await customer.newPage()
  page.setDefaultTimeout(10_000)
  let customerLogins = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/v1/auth/telegram')) customerLogins += 1 })
  await page.goto(`${origin}/app`)
  await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  const sessionCookie = (await customer.cookies()).find(cookie => cookie.name === cookieName)
  assert(sessionCookie?.httpOnly && sessionCookie.secure && sessionCookie.sameSite === 'Lax' && sessionCookie.path === '/', 'Real session cookie must be Secure/HttpOnly/Lax with root path.')
  assert(!(await page.evaluate(name => document.cookie.includes(name), cookieName)), 'Session cookie must be inaccessible to JavaScript.')
  assert(customerLogins === 1, 'Initial Telegram launch must create exactly one actual session.')
  await page.reload()
  await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  assert(customerLogins === 1, 'Page reload must restore the real cookie without replaying signed proof.')
  console.log('PASS 1/10: production React signs in a Customer through real FastAPI/PostgreSQL; secure cookie restores on reload.')

  // M03: a production React mutation crosses the same HTTPS gateway and
  // commits actual projects/requests; no API interception or business mocks.
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Open project drafts' }).click()
  await page.getByLabel('Service', { exact: true }).selectOption('design_and_print')
  const businessNotes = `M03 browser draft ${randomUUID()}`
  await page.getByLabel('Project notes (optional)').fill(businessNotes)
  const creation = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/v1/requests'))
  await page.getByRole('button', { name: 'Save simulation draft' }).click()
  const createdResponse = await creation
  assert(createdResponse.status() === 201, 'React must create a real simulation project and draft.')
  const businessDraft = await createdResponse.json()
  assert(businessDraft.request.stage_kind === 'design' && businessDraft.project.mode === 'simulation', 'Combined projects must begin with a simulation design stage.')
  const draftEditor = page.locator(`#notes-${businessDraft.request.id}`)
  await draftEditor.fill(`${businessNotes} revised`)
  const update = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith(`/requests/${businessDraft.request.id}`))
  await page.locator('form').filter({ has: draftEditor }).getByRole('button', { name: 'Save changes', exact: true }).click()
  const updatedResponse = await update
  assert(updatedResponse.status() === 200 && (await updatedResponse.json()).version === 2, 'React must update the actual versioned draft.')
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Mobile draft workspace must not overflow horizontally.')
  await mkdir(path.join(frontend, 'test-results'), { recursive: true })
  await page.screenshot({ path: path.join(frontend, 'test-results/m03-customer-mobile.png'), fullPage: true })
  const noBusinessCsrf = await page.evaluate(async () => (await fetch('/api/v1/requests', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'missing-csrf-browser' }, body: JSON.stringify({ service_type: 'printing' }) })).status)
  assert(noBusinessCsrf === 403, 'Business writes must enforce session CSRF through the HTTPS gateway.')
  const stranger = await browser.newContext({ ignoreHTTPSErrors: true })
  const strangerLogin = await stranger.request.post(`${origin}/api/v1/auth/telegram`, { headers: { Origin: origin }, data: { init_data: signedLaunch(223) } })
  assert(strangerLogin.status() === 200)
  assert((await stranger.request.get(`${origin}/api/v1/requests/${businessDraft.request.id}`)).status() === 404, 'Another Customer must not read the draft.')
  assert((await stranger.request.get(`${origin}/api/v1/projects/${businessDraft.project.id}`)).status() === 404, 'Another Customer must not read its parent project.')
  assert((await stranger.request.get(`${origin}/api/v1/owner/requests`)).status() === 403, 'Customer must not list Owner resources.')
  await stranger.close()
  console.log('PASS 2/10: production React creates and edits real simulation drafts; gateway CSRF and cross-customer isolation hold.')

  await page.goto(`${origin}/owner`)
  await page.getByRole('heading', { name: 'Owner access required' }).waitFor()
  const denied = await page.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)
  assert(denied === 403, 'Authenticated Customer must be denied by the actual Owner API.')
  assert((await page.evaluate(async () => (await fetch('/api/v1/ready')).status)) === 403, 'Customer must not reach internal Owner readiness.')
  assert((await page.getByRole('group', { name: 'Preview workspace' }).count()) === 0, 'Production must not expose development role overrides.')
  console.log('PASS 3/10: Customer is denied by both the production Owner route and the actual backend authorization check.')

  await page.goto(`${origin}/app`)
  await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  const missingCsrf = await page.evaluate(async () => (await fetch('/api/v1/auth/logout', { method: 'POST' })).status)
  assert(missingCsrf === 403, 'A cookie-authenticated logout without CSRF must fail.')
  const csrfResponse = await customer.request.get(`${origin}/api/v1/auth/csrf`)
  const { csrf_token: currentCsrf } = await csrfResponse.json()
  const wrongOrigin = await customer.request.post(`${origin}/api/v1/auth/logout`, {
    headers: { Origin: 'https://untrusted.example', 'X-CSRF-Token': currentCsrf },
  })
  assert(wrongOrigin.status() === 403, 'Correct CSRF must not bypass Origin validation through HTTPS proxy.')
  const wrongCsrf = await customer.request.post(`${origin}/api/v1/auth/logout`, {
    headers: { Origin: origin, 'X-CSRF-Token': 'invalid-session-token' },
  })
  assert(wrongCsrf.status() === 403, 'Correct Origin must not bypass session CSRF validation through HTTPS proxy.')
  assert((await page.evaluate(async () => (await fetch('/api/v1/auth/me')).status)) === 200, 'Failed CSRF must leave the session active.')
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.getByRole('heading', { name: 'Sign-in required' }).waitFor()
  assert((await page.evaluate(async () => (await fetch('/api/v1/auth/me')).status)) === 401, 'Logged-out session must be unauthorized.')
  const replay = await customer.request.get(`${origin}/api/v1/auth/me`, { headers: { Cookie: `${cookieName}=${sessionCookie.value}` } })
  assert(replay.status() === 401, 'Server-side revocation must reject the old cookie even when replayed.')
  assert(customerLogins === 1, 'Logout must not silently reuse the old Telegram launch proof.')
  await page.evaluate(raw => { window.Telegram.WebApp.initData = raw }, signedLaunch(222))
  await page.getByRole('button', { name: 'Check sign-in again' }).click()
  await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  assert(customerLogins === 2, 'A fresh Telegram launch must recover after logout, using exactly one new login.')
  console.log('PASS 4/10: HTTPS proxy Origin/CSRF enforcement, logout/revocation, no proof replay and fresh-launch recovery.')

  const owner = await browser.newContext({ ignoreHTTPSErrors: true })
  await installTelegramPresentation(owner, signedLaunch(111))
  const ownerPage = await owner.newPage()
  ownerPage.setDefaultTimeout(10_000)
  await ownerPage.goto(`${origin}/owner`)
  await ownerPage.getByRole('heading', { name: 'Your workshop, at a glance.' }).waitFor()
  assert((await ownerPage.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)) === 200, 'Only the configured Owner must reach the actual Owner API.')
  assert((await ownerPage.evaluate(async () => (await fetch('/api/v1/ready')).status)) === 200, 'Packaged schema must match the application readiness head.')
  // /docs on the HTTPS gateway is a SPA fallback, so probe the private API
  // directly; only /api/* is forwarded by the public test gateway.
  if (useContainerApi) assert((await fetch(`http://127.0.0.1:${apiPort}/docs`)).status === 404, 'Production container must not expose interactive API docs.')
  await ownerPage.getByRole('link', { name: 'Customer workspace', exact: true }).click()
  await ownerPage.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  await ownerPage.getByRole('link', { name: 'Owner workspace', exact: true }).click()
  await ownerPage.getByRole('heading', { name: 'Your workshop, at a glance.' }).waitFor()
  console.log('PASS 5/10: trusted server-provisioned Owner signs in and navigates both production workspaces.')
  await ownerPage.getByRole('button', { name: 'Load customer drafts' }).click()
  const ownerRow = ownerPage.locator('.request-row').filter({ has: ownerPage.getByText(`${businessNotes} revised`, { exact: true }) })
  await ownerRow.getByLabel('Cancellation reason').fill('M03 browser review complete')
  const cancellation = ownerPage.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/requests/${businessDraft.request.id}/transitions`))
  await ownerRow.getByRole('button', { name: 'Cancel draft', exact: true }).click()
  const cancelledResponse = await cancellation
  assert(cancelledResponse.status() === 200 && (await cancelledResponse.json()).status === 'cancelled', 'Owner must cancel through the real authorized transition service.')
  await ownerRow.getByText('Cancelled', { exact: true }).waitFor()
  await ownerPage.screenshot({ path: path.join(frontend, 'test-results/m03-owner-desktop.png'), fullPage: true })
  const customerView = await customer.request.get(`${origin}/api/v1/requests/${businessDraft.request.id}`)
  assert(customerView.status() === 200 && (await customerView.json()).status === 'cancelled', 'Customer must see the committed Owner transition.')
  console.log('PASS 6/10: provisioned Owner reviews and cancels the customer draft; Customer reads the committed state.')
  // M04: full printing intake; all API requests use the actual backend.
  await page.goto(`${origin}/app/requests/new`)
  const printNotes = `M04 private print ${randomUUID()}`
  await page.getByLabel('Project notes (optional)').fill(printNotes)
  await page.getByRole('button', { name: 'Create printing draft', exact: true }).click()
  await page.getByRole('heading', { name: 'Your printing draft' }).waitFor()
  const printingId = new URL(page.url()).pathname.split('/').at(-1)
  assert(printingId, 'Printing draft must have a durable identifier.')
  const points = [[0,0,0],[20,0,0],[20,20,0],[0,20,0],[0,0,20],[20,0,20],[20,20,20],[0,20,20]]
  const faces = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
  const stl = Buffer.from('solid cube\n' + faces.map(face => 'facet normal 0 0 0\nouter loop\n' + face.map(i => 'vertex ' + points[i].join(' ') + '\n').join('') + 'endloop\nendfacet\n').join('') + 'endsolid cube\n')
  const obj = Buffer.from('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
  await page.getByLabel('Choose model files', { exact: true }).setInputFiles([
    { name: 'triangle.stl', mimeType: 'application/octet-stream', buffer: stl },
    { name: 'triangle.obj', mimeType: 'application/octet-stream', buffer: obj },
  ])
  await expect(page.getByText('Format checked', { exact: true })).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  for (let index = 1; index <= 2; index++) {
    const item = page.getByRole('region', { name: `Print item ${index}`, exact: true })
    const update = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().includes(`/requests/${printingId}/items/`))
    await item.getByLabel('Material', { exact: true }).selectOption('dev-pla')
    await item.getByLabel('Color', { exact: true }).selectOption('dev-white')
    await item.getByLabel('Quality', { exact: true }).selectOption('dev-standard')
    await item.getByLabel('I confirm these are the model’s intended units').check()
    if (index === 1) await item.getByLabel('Special requirements', { exact: true }).fill('Owner review: keep the visible face clean.')
    assert((await update).status() === 200, 'Item settings must autosave through the real versioned API.')
    await expect(item.getByText('Settings saved', { exact: true })).toBeVisible()
  }
  await page.reload()
  await page.getByRole('heading', { name: 'Your printing draft' }).waitFor()
  await expect(page.getByText('Format checked', { exact: true })).toHaveCount(2)
  const recovered = await (await customer.request.get(`${origin}/api/v1/requests/${printingId}/intake`)).json()
  assert(recovered.items.length === 2 && recovered.items.every(item => item.specification.unit_confirmed && item.specification.material_key === 'dev-pla'), 'Draft models and autosaved settings must survive WebView reload.')
  await page.getByRole('button', { name: '3. Fulfillment', exact: true }).click()
  const preferences = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith(`/requests/${printingId}/intake`))
  await page.getByLabel('Preferred handoff', { exact: true }).selectOption('delivery')
  await page.getByLabel('Fulfillment notes (optional)').fill('Contact me before arranging delivery.')
  assert((await preferences).status() === 200, 'Fulfillment preferences must autosave to PostgreSQL.')
  await expect(page.getByText('Preferences saved', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '4. Review', exact: true }).click()
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Mobile printing wizard must not overflow horizontally.')
  await page.screenshot({ path: path.join(frontend, 'test-results/m04-customer-mobile.png'), fullPage: true })
  const submission = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/requests/${printingId}/submit`))
  await page.getByRole('button', { name: 'Submit printing request', exact: true }).click()
  const submittedResponse = await submission
  assert(submittedResponse.status() === 200, 'Completed printing draft must submit successfully.')
  const submitted = await submittedResponse.json()
  await page.getByRole('heading', { name: 'Printing request submitted', exact: true }).waitFor()
  await page.getByRole('heading', { name: 'Pending analysis', exact: true }).waitFor()
  assert(submitted.tasks.length === 2 && submitted.tasks.every(task => task.state === 'pending'), 'Submission creates one pending task per model; no fake analysis.')
  assert((await page.evaluate(() => Object.keys(localStorage))).length === 0, 'Printing intake must not persist private data in localStorage.')
  console.log('PASS 8/10: mobile multi-model upload, autosave, reload recovery, preferences and validated submission persist through real APIs.')

  const outsider = await browser.newContext({ ignoreHTTPSErrors: true })
  assert((await outsider.request.post(`${origin}/api/v1/auth/telegram`, { headers: { Origin: origin }, data: { init_data: signedLaunch(224) } })).status() === 200)
  const fileId = submitted.items[0].model_file.id
  for (const resource of [`requests/${printingId}/intake`, `requests/${printingId}/analysis`, `files/${fileId}`, `files/${fileId}/download`]) {
    assert((await outsider.request.get(`${origin}/api/v1/${resource}`)).status() === 404, 'Another customer must not read private printing data or models.')
  }
  const download = await customer.request.get(`${origin}/api/v1/files/${fileId}/download`)
  assert(download.status() === 200 && (await download.body()).equals(stl), 'Authorized download must return exact private model bytes.')
  assert(download.headers()['cache-control'] === 'no-store' && download.headers()['x-content-type-options'] === 'nosniff', 'Downloads must prevent caching and sniffing.')
  await outsider.close()
  console.log('PASS 9/10: cross-customer file/intake/task denial and authenticated private download through HTTPS.')

  await ownerPage.goto(`${origin}/owner`)
  await ownerPage.getByRole('button', { name: 'Load submitted printing requests', exact: true }).click()
  await ownerPage.getByRole('link', { name: `Inspect printing request ${printingId.slice(0, 8)}`, exact: true }).click()
  await ownerPage.getByRole('heading', { name: 'Printing request submitted', exact: true }).waitFor()
  await expect(ownerPage.getByText('Owner review: keep the visible face clean.', { exact: true })).toBeVisible()
  assert((await ownerPage.getByRole('button', { name: 'Submit printing request', exact: true }).count()) === 0, 'Owner inspection cannot impersonate customer editing.')
  const ownerDownload = ownerPage.waitForEvent('download')
  await ownerPage.getByRole('button', { name: 'Download private model', exact: true }).first().click()
  assert((await ownerDownload).suggestedFilename() === 'triangle.stl', 'Owner must download the authorized private file.')
  await ownerPage.screenshot({ path: path.join(frontend, 'test-results/m04-owner-desktop.png'), fullPage: true })
  const analysis = await (await owner.request.get(`${origin}/api/v1/requests/${printingId}/analysis`)).json()
  assert(analysis.state === 'pending' && analysis.processing_available === false, 'Pending analysis must never claim a running or completed worker.')
  console.log('PASS 10/10: Owner queue, special requirements, private download and pending-analysis inspection.')
  if (process.env.M06_TEST_WORKER_IMAGE && !useContainerApi) {
    await runAnalysisIntegration({ page, ownerPage, customer, owner, origin, printingId, backendDirectory, directory, databaseUrl, image: process.env.M06_TEST_WORKER_IMAGE })
  } else console.log('M06 real worker browser flow not requested; baseline intake remains pending.')
  await runDesignIntegration({ page, ownerPage, customer, owner, origin, frontend })
  await runPricingIntegration({ page, ownerPage, customer, owner, origin, printingId })
  await customer.close()
  await owner.close()

  const forged = await browser.newContext({ ignoreHTTPSErrors: true })
  await installTelegramPresentation(forged, signedLaunch(111, true))
  const forgedPage = await forged.newPage()
  forgedPage.setDefaultTimeout(10_000)
  await forgedPage.goto(`${origin}/owner`)
  await forgedPage.getByRole('heading', { name: 'Sign-in required' }).waitFor()
  assert((await forged.cookies()).every(cookie => cookie.name !== cookieName), 'Forged proof must never create a session cookie.')
  assert((await forgedPage.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)) === 401, 'Forged proof must not authenticate against the actual backend.')
  await forgedPage.evaluate(raw => { window.Telegram.WebApp.initData = raw }, signedLaunch(111))
  await forgedPage.getByRole('button', { name: 'Check sign-in again' }).click()
  await forgedPage.getByRole('heading', { name: 'Your workshop, at a glance.' }).waitFor()
  assert((await forgedPage.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)) === 200, 'A fresh valid proof must recover from an earlier rejected login.')
  console.log('PASS 7/10: forged launch rejected; fresh valid launch recovers through the real backend.')
  await forged.close()
  await runOpaqueOriginIntegration({ browser, origin, installTelegramPresentation, signedLaunch, observed: opaqueRequests })
  console.log(`M02–M07 real-stack integration: ${process.env.M06_TEST_WORKER_IMAGE && !useContainerApi ? 19 : 18} flows PASS; no API mocks, production frontend + HTTPS + FastAPI + PostgreSQL.`)
  if (useContainerApi) console.log('Container API mode PASS: packaged application used; caller owns container cleanup.')
} catch (error) {
  // Assertion/selector diagnostics contain no signed proofs or credential values.
  console.error(`M02–M05 real-stack integration FAILED: ${error instanceof Error ? error.message : 'unknown test failure'}`)
  process.exitCode = 1
} finally {
  if (browser) await browser.close().catch(() => {})
  if (gateway) {
    gateway.closeAllConnections()
    await new Promise(resolve => gateway.close(resolve))
  }
  await stopBackend(backend)
  if (directory) await rm(directory, { recursive: true, force: true })
}
