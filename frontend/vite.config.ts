import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Note: Files in public/ directory (including sw.js) are automatically
// copied to dist/ root during build. No special configuration needed.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    host: true,  // Слушать на всех интерфейсах
    port: 5173,    // Стандартный Vite порт
    strictPort: true,  // НЕ пытаться использовать другой порт, если 5173 занят
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
  preview: {
    host: true,
    port: 4173,
    strictPort: true,
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
