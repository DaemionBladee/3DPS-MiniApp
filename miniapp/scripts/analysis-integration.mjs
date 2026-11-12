import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { expect } from '@playwright/test'

export async function runAnalysisIntegration({ page, ownerPage, customer, owner, origin, printingId, backendDirectory, directory, databaseUrl, image }) {
  assert(/^sha256:[0-9a-f]{64}$/.test(image), 'M06 browser checks require a real immutable worker image.')
  async function worker(args) {
    const child = spawn(path.join(backendDirectory, '.venv/bin/python'), ['scripts/process_tasks.py', ...args], {
      cwd: backendDirectory,
      env: { ...process.env, PYTHONPATH: `${backendDirectory}:${path.dirname(backendDirectory)}`,
        APP_ENV: 'test', DATABASE_URL: databaseUrl, BOT_TOKEN: 'm06-browser-synthetic-bot-token',
        SESSION_SECRET: 'm06-browser-synthetic-orchestrator-only-secret', OWNER_TELEGRAM_IDS: '111',
        STORAGE_ROOT: path.join(directory, 'private-models'), PUBLIC_BASE_URL: origin },
      stdio: ['ignore', 'ignore', 'ignore'],
    })
    const timer = setTimeout(() => child.kill('SIGTERM'), 120_000)
    try {
      const code = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', resolve) })
      assert.equal(code, 0, 'Trusted worker CLI must succeed against the real sandbox and PostgreSQL.')
    } finally { clearTimeout(timer) }
  }
  await worker(['--seed-image', image, '--profile-revision', '1'])
  for (let index = 0; index < 2; index++) await worker(['--once', '--staging-root', path.join(directory, 'analysis-jobs')])
  const response = await customer.request.get(`${origin}/api/v1/requests/${printingId}/analysis/results`)
  assert.equal(response.status(), 200)
  const results = await response.json()
  assert.equal(results.items.length, 2)
  assert(results.items.some(item => item.outcome === 'estimated' && item.estimate.filament_g > 0))
  assert(results.items.some(item => item.outcome === 'manual_review' && item.estimate === null))
  await page.reload()
  await page.getByRole('heading', { name: 'Manual review required', exact: true }).waitFor()
  await expect(page.getByText('Simulation estimate — not a final quotation.', { exact: true })).toBeVisible()
  await expect(page.getByText(/Per model:/)).toBeVisible()
  assert(await page.getByRole('button', { name: /pay|accept quote/i }).count() === 0)
  await ownerPage.reload()
  await expect(ownerPage.getByRole('heading', { name: 'Manual review required', exact: true })).toBeVisible()
  await expect(ownerPage.getByRole('button', { name: 'Review simulation retry' })).toHaveCount(2)
  assert((await owner.request.get(`${origin}/api/v1/owner/processing-tasks`)).status() === 200)
  assert((await customer.request.get(`${origin}/api/v1/owner/processing-tasks`)).status() === 403)
  console.log('PASS M06: real isolated cube slicing + open-mesh review, SQL provenance, customer/Owner views, no commercial actions.')
}
