import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// Единый источник версии — корневой VERSION (фолбэк 'dev').
// В Docker-сборке VERSION лежит вне контекста (frontend/), поэтому значение
// приходит аргументом сборки APP_VERSION; локально файл читается сам.
function readAppVersion(): string {
  const fromBuild = (process.env.APP_VERSION ?? '').trim()
  if (fromBuild) return fromBuild
  try {
    const text = fs.readFileSync(path.resolve(__dirname, '../VERSION'), 'utf-8').trim().split(/\s+/)[0]
    if (text) return text
  } catch {
    // фолбэк ниже
  }
  return 'dev'
}
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(readAppVersion()),
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,  // Слушать на всех интерфейсах
    port: 5173,    // Стандартный Vite порт
    strictPort: true,  // НЕ пытаться использовать другой порт, если 5173 занят
    allowedHosts: true,  // Разрешить все хосты
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8013',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8013',
        ws: true,
        rewriteWsOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8013',
        changeOrigin: true,
      },
    },
  },
})
