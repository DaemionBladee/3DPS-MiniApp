/* global document */
import assert from 'node:assert/strict'
import { expect } from '@playwright/test'

/** Real opaque-origin HTTP requests plus production React cookie restoration.
 * Browser-controlled Origin cannot reliably be overridden by Chromium routing;
 * use the context's real HTTP client, never fake API responses or proxy bypasses.
 */
export async function runOpaqueOriginIntegration({ browser, origin, installTelegramPresentation, signedLaunch, observed }) {
  const before = { ...observed }
  const opaque = { Origin: 'null' }
  const customer = await browser.newContext({ ignoreHTTPSErrors: true })
  const proof = signedLaunch(225)
  await installTelegramPresentation(customer, proof)
  try {
    const login = await customer.request.post(`${origin}/api/v1/auth/telegram`, { headers: opaque, data: { init_data: proof } })
    assert.equal(login.status(), 200)
    assert.equal(login.headers()['access-control-allow-origin'], undefined)
    const session = await login.json()
    const page = await customer.newPage()
    page.setDefaultTimeout(10_000)
    let browserLogins = 0
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/auth/telegram')) browserLogins += 1 })
    await page.goto(`${origin}/app`)
    await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
    const cookie = (await customer.cookies()).find(c => c.name === '__Host-3dps_session')
    assert(cookie?.secure && cookie.httpOnly && cookie.sameSite === 'Lax' && cookie.path === '/')
    assert.equal(await page.evaluate(() => document.cookie.includes('__Host-3dps_session')), false)
    await page.reload()
    await page.getByRole('heading', { name: 'Your next idea, made real.' }).waitFor()
    assert.equal(browserLogins, 0, 'React must restore the opaque-login cookie without replaying the consumed launch.')
    assert.equal((await customer.request.get(`${origin}/api/v1/owner/auth-check`, { headers: opaque })).status(), 403)
    const missing = await customer.request.post(`${origin}/api/v1/requests`, { headers: { ...opaque, 'Idempotency-Key': 'opaque-no-csrf' }, data: { service_type: 'printing' } })
    assert.equal(missing.status(), 403)
    const creation = await customer.request.post(`${origin}/api/v1/requests`, { headers: { ...opaque, 'Idempotency-Key': 'opaque-valid-csrf', 'X-CSRF-Token': session.csrf_token }, data: { service_type: 'printing', customer_notes: 'Opaque-origin private simulation fixture' } })
    assert.equal(creation.status(), 201)
    await page.getByRole('button', { name: 'Open project drafts', exact: true }).click()
    await expect(page.getByLabel('Draft notes', { exact: true })).toHaveValue('Opaque-origin private simulation fixture')
    const crossSite = await customer.request.post(`${origin}/api/v1/auth/logout`, { headers: { ...opaque, 'Sec-Fetch-Site': 'cross-site', 'X-CSRF-Token': session.csrf_token } })
    assert.equal(crossSite.status(), 403)
    const replay = await customer.request.post(`${origin}/api/v1/auth/telegram`, { headers: opaque, data: { init_data: proof } })
    assert.equal(replay.status(), 409)
    assert.equal((await customer.request.get(`${origin}/api/v1/auth/me`, { headers: opaque })).status(), 200)
    const logout = await customer.request.post(`${origin}/api/v1/auth/logout`, { headers: { ...opaque, 'X-CSRF-Token': session.csrf_token } })
    assert.equal(logout.status(), 204)
    // Simulate WebView resume so the mounted provider rechecks the revoked
    // cookie and retires its launch, rather than remounting with a spent proof.
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    await page.getByRole('heading', { name: 'Sign-in required', exact: true }).waitFor()
    assert.equal((await customer.request.get(`${origin}/api/v1/auth/me`, { headers: opaque })).status(), 401)
    assert.equal(await page.evaluate(() => Object.keys(localStorage).length), 0)
    assert(observed.login > before.login && observed.csrfMutations >= before.csrfMutations + 3, 'TLS gateway must observe real null-origin login, draft creation and logout.')
    console.log('PASS opaque Origin 1/2: real null-origin HTTPS proof/CSRF/replay/logout checks and production React secure-cookie restoration without proof resubmission.')
  } finally { await customer.close() }
  const owner = await browser.newContext({ ignoreHTTPSErrors: true })
  const ownerProof = signedLaunch(111)
  await installTelegramPresentation(owner, ownerProof)
  try {
    const login = await owner.request.post(`${origin}/api/v1/auth/telegram`, { headers: { ...opaque, Referer: `${origin}/app`, 'Sec-Fetch-Site': 'same-origin' }, data: { init_data: ownerProof } })
    assert.equal(login.status(), 200)
    assert.equal((await login.json()).user.role, 'owner')
    const page = await owner.newPage()
    page.setDefaultTimeout(10_000)
    await page.goto(`${origin}/owner`)
    await expect(page.getByRole('heading', { name: 'Your workshop, at a glance.' })).toBeVisible()
    assert.equal((await owner.request.get(`${origin}/api/v1/owner/auth-check`, { headers: { ...opaque, 'Sec-Fetch-Site': 'same-origin' } })).status(), 200)
    console.log('PASS opaque Origin 2/2: server-provisioned Owner opaque-origin login with same-origin evidence and production Owner workspace.')
  } finally { await owner.close() }
}
