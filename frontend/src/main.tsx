import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import { register } from './serviceWorkerRegistration'

// Force light mode - remove dark class if present
if (typeof document !== 'undefined') {
  document.documentElement.classList.remove('dark')
  localStorage.setItem('theme', 'light')
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)

// Register Service Worker after rendering
register({
  onSuccess: (registration) => {
    console.log('Service Worker успешно зарегистрирован:', registration.scope)
  },
  onUpdate: () => {
    console.log('Доступно обновление Service Worker')
  },
  onError: (error) => {
    console.error('Ошибка регистрации Service Worker:', error)
  }
})
