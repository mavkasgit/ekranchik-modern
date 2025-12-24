/**
 * Интервалы обновления данных (в миллисекундах).
 * 
 * Это fallback интервалы - основное обновление идёт через WebSocket мгновенно.
 * Эти интервалы используются только если WebSocket не работает.
 */

// Быстрые проверки (критичные для UX)
export const FILE_STATUS_INTERVAL = 5000      // 5 сек - проверка изменений Excel
export const WS_RECONNECT_INTERVAL = 5000     // 5 сек - переподключение WebSocket

// Основные данные (fallback)
export const DATA_REFRESH_INTERVAL = 30000    // 30 сек - все остальные данные
