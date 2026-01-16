/**
 * Интервалы обновления данных (в миллисекундах).
 * 
 * Основное обновление идёт через WebSocket.
 * Эти интервалы используются только как fallback если WebSocket не работает.
 */

// Быстрые проверки (критичные для UX)
export const FILE_STATUS_INTERVAL = 5000      // 5 сек - проверка изменений Excel
export const WS_RECONNECT_INTERVAL = 3000     // 3 сек - переподключение WebSocket

// Основные данные (fallback когда WS не работает)
export const DATA_REFRESH_INTERVAL = 10000    // 10 сек - fallback для данных

// WebSocket обновления (реальные интервалы на бэкенде)
export const WS_LINE_UPDATE_INTERVAL = 2000   // 2 сек - heartbeat с бэкенда (line_monitor._heartbeat_interval)

// Для отображения в UI
export const WS_UPDATE_INTERVAL_SEC = WS_LINE_UPDATE_INTERVAL / 1000
