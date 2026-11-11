import { spawnSync } from 'node:child_process'
import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
// Deliberately hostile configuration: production must ignore the UI mock flag.
const result = spawnSync(process.execPath, ['node_modules/vite/bin/vite.js', 'build', '--outDir', '.production-check'], {
  cwd: root,
  env: { ...process.env, NODE_ENV: 'production', VITE_TELEGRAM_MOCK: 'true' },
  stdio: 'inherit',
})
if (result.error) throw result.error
if (result.status !== 0) process.exit(result.status ?? 1)

async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name)
    if (entry.isDirectory()) await inspect(file)
    else if (entry.name.endsWith('.js')) {
      const content = await readFile(file, 'utf8')
      if (content.includes('M01_DEV_UI_MOCK_ONLY') || /^mock-/.test(entry.name)) {
        throw new Error('Development mock found in production artifact')
      }
    }
  }
}
await inspect(path.join(root, '.production-check'))
console.log('Production artifact PASS: mock flag forced true, mock module excluded by build guard and artifact inspection.')
