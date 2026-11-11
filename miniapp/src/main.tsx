import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './app/App'
import { createQueryClient } from './app/query-client'
import { TelegramProvider } from './integrations/telegram/TelegramProvider'
import { AuthProvider } from './features/auth/AuthProvider'
import './styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('Missing application root')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <TelegramProvider>
        <AuthProvider><BrowserRouter><App /></BrowserRouter></AuthProvider>
      </TelegramProvider>
    </QueryClientProvider>
  </StrictMode>,
)
