import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,  // Слушать на всех интерфейсах (для ktm.local)
    port: 80,    // Стандартный HTTP порт (требует запуск от администратора)
    strictPort: true,  // НЕ пытаться использовать другой порт, если 80 занят
    allowedHosts: true,  // Разрешить все хосты
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        rewriteWsOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
