/* global window, document */
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import { createHmac, randomBytes, randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import http from 'node:http'
import https from 'node:https'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const frontend = fileURLToPath(new URL('..', import.meta.url))
const backendDirectory = path.resolve(frontend, '../backend')
const dist = path.join(frontend, 'dist')
const apiPort = 18002
const gatewayPort = 18443
const origin = `https://127.0.0.1:${gatewayPort}`
const syntheticBotToken = 'm02-integration-synthetic-bot-token'
const cookieName = '__Host-3dps_session'

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
    if (child.exitCode !== null || child.signalCode !== null) throw new Error('The disposable backend exited before readiness.')
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
  assert(existsSync(path.join(backendDirectory, '.venv/bin/python')), 'Install the backend test environment first.')
  await assertPortFree(apiPort)
  await assertPortFree(gatewayPort)
  directory = await mkdtemp(path.join(os.tmpdir(), '3dps-m02-browser-'))
  backend = spawn(path.join(backendDirectory, '.venv/bin/python'), [
    '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1',
    '--port', String(apiPort), '--no-proxy-headers', '--no-access-log',
  ], {
    cwd: backendDirectory,
    env: {
      ...process.env,
      APP_ENV: 'test', DATABASE_URL: databaseUrl, BOT_TOKEN: syntheticBotToken,
      SESSION_SECRET: randomBytes(32).toString('base64url'), OWNER_TELEGRAM_IDS: '111',
      PUBLIC_BASE_URL: origin, SIMULATION_MODE: 'true', DEVELOPMENT_AUTH_ENABLED: 'false',
      BINDING_QUOTES_ENABLED: 'false', AUTO_QUOTE_ENABLED: 'false', PAYMENT_POLICY_APPROVED: 'false',
      LIVE_PAYMENTS_ENABLED: 'false', REAL_PRINTING_ENABLED: 'false', AUTH_RATE_LIMIT: '100',
    },
    stdio: ['ignore', 'ignore', 'pipe'],
  })
  // Never echo child logs, signed launch data, cookies or configured secrets.
  backend.stderr.resume()
  backend.on('error', () => { /* Readiness produces a safe diagnostic. */ })
  await waitForBackend(backend)
  gateway = await createGateway(directory)
  browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
  })

  // The single self-signed test certificate is accepted only by these ephemeral
  // browser contexts. Package installation and other TLS verification stay on.
  const customer = await browser.newContext({ ignoreHTTPSErrors: true })
  await installTelegramPresentation(customer, signedLaunch(222))
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
  console.log('PASS 1/5: production React signs in a Customer through real FastAPI/PostgreSQL; secure cookie restores on reload.')

  await page.goto(`${origin}/owner`)
  await page.getByRole('heading', { name: 'Owner access required' }).waitFor()
  const denied = await page.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)
  assert(denied === 403, 'Authenticated Customer must be denied by the actual Owner API.')
  assert((await page.getByRole('group', { name: 'Preview workspace' }).count()) === 0, 'Production must not expose development role overrides.')
  console.log('PASS 2/5: Customer is denied by both the production Owner route and the actual backend authorization check.')

  await page.goto(`${origin}/app`)
  await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  const missingCsrf = await page.evaluate(async () => (await fetch('/api/v1/auth/logout', { method: 'POST' })).status)
  assert(missingCsrf === 403, 'A cookie-authenticated logout without CSRF must fail.')
  assert((await page.evaluate(async () => (await fetch('/api/v1/auth/me')).status)) === 200, 'Failed CSRF must leave the session active.')
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.getByRole('heading', { name: 'Sign-in required' }).waitFor()
  assert((await page.evaluate(async () => (await fetch('/api/v1/auth/me')).status)) === 401, 'Logged-out session must be unauthorized.')
  const replay = await customer.request.get(`${origin}/api/v1/auth/me`, { headers: { Cookie: `${cookieName}=${sessionCookie.value}` } })
  assert(replay.status() === 401, 'Server-side revocation must reject the old cookie even when replayed.')
  assert(customerLogins === 1, 'Logout must not silently reuse the old Telegram launch proof.')
  console.log('PASS 3/5: real CSRF enforcement, React logout, PostgreSQL session revocation and no automatic proof replay.')
  await customer.close()

  const owner = await browser.newContext({ ignoreHTTPSErrors: true })
  await installTelegramPresentation(owner, signedLaunch(111))
  const ownerPage = await owner.newPage()
  ownerPage.setDefaultTimeout(10_000)
  await ownerPage.goto(`${origin}/owner`)
  await ownerPage.getByRole('heading', { name: 'Your workshop, at a glance.' }).waitFor()
  assert((await ownerPage.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)) === 200, 'Only the configured Owner must reach the actual Owner API.')
  await ownerPage.getByRole('link', { name: 'Customer workspace', exact: true }).click()
  await ownerPage.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
  await ownerPage.getByRole('link', { name: 'Owner workspace', exact: true }).click()
  await ownerPage.getByRole('heading', { name: 'Your workshop, at a glance.' }).waitFor()
  console.log('PASS 4/5: trusted server-provisioned Owner signs in and navigates both production workspaces.')
  await owner.close()

  const forged = await browser.newContext({ ignoreHTTPSErrors: true })
  await installTelegramPresentation(forged, signedLaunch(111, true))
  const forgedPage = await forged.newPage()
  forgedPage.setDefaultTimeout(10_000)
  await forgedPage.goto(`${origin}/owner`)
  await forgedPage.getByRole('heading', { name: 'Sign-in required' }).waitFor()
  assert((await forged.cookies()).every(cookie => cookie.name !== cookieName), 'Forged proof must never create a session cookie.')
  assert((await forgedPage.evaluate(async () => (await fetch('/api/v1/owner/auth-check')).status)) === 401, 'Forged proof must not authenticate against the actual backend.')
  console.log('PASS 5/5: forged signed launch data cannot authenticate or open the production Owner workspace.')
  await forged.close()
  console.log('M02 real-stack integration: 5 flows PASS; no API mocks, production frontend + HTTPS + FastAPI + PostgreSQL.')
} catch (error) {
  // Assertion/selector diagnostics contain no signed proofs or credential values.
  console.error(`M02 real-stack integration FAILED: ${error instanceof Error ? error.message : 'unknown test failure'}`)
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
