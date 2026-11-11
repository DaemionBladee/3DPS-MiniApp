import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  // The proxy target is server configuration, never a browser-facing API URL.
  const env = loadEnv(mode, process.cwd(), '')
  const target = env['API_PROXY_TARGET'] || 'http://127.0.0.1:8000'
  const url = new URL(target)
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('API_PROXY_TARGET must be an HTTP(S) origin without credentials')
  }

  return {
    plugins: [
      react(),
      tailwindcss(),
      {
        name: 'exclude-development-telegram-mock',
        generateBundle(_options, bundle) {
          for (const output of Object.values(bundle)) {
            if (output.type === 'chunk' && Object.keys(output.modules).some(id => /integrations\/telegram\/mock\.[tj]s$/.test(id))) {
              this.error('Development Telegram mock must never be included in a build')
            }
          }
        },
      },
    ],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: { '/api': { target: url.origin, changeOrigin: false } },
    },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true },
    build: { sourcemap: false },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      clearMocks: true,
    },
  }
})
