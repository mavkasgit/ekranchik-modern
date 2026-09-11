import type { QueryClient } from '@tanstack/react-query'
import type { WebSocketMessage } from '@/types/dashboard'
import type { BathStatus, LineStatus, LineUpdatePayload } from '@/types/line'
import { DASHBOARD_KEY, LINE_STATUS_KEY, OPCUA_STATUS_KEY } from '@/lib/queryKeys'

/**
 * Единственная таблица «сообщение сервера → что делать с кэшем».
 * Инвалидация по фактическим ключам, а не по строкам, которых в кэше нет.
 */
export function applyRealtimeMessage(client: QueryClient, message: WebSocketMessage): void {
  switch (message.type) {
    case 'data_update':
    case 'unload_event':
      void client.invalidateQueries({ queryKey: DASHBOARD_KEY })
      return
    case 'opcua_status':
      void client.invalidateQueries({ queryKey: OPCUA_STATUS_KEY })
      return
    case 'line_update':
      client.setQueryData<LineStatus>(LINE_STATUS_KEY, (previous) =>
        mergeLineUpdate(previous, message.payload as LineUpdatePayload),
      )
      return
    default:
      return
  }
}

/**
 * Сообщение линии несёт только счётчики ванн; данные из HTTP (`article`, `color`,
 * `power_supply`, `free`, `d_time`) сохраняем, иначе они пропадут из таблицы прогноза.
 */
function mergeLineUpdate(previous: LineStatus | undefined, payload: LineUpdatePayload): LineStatus {
  const live = new Map((payload.baths ?? []).map((bath) => [bath.bath_number, bath]))
  const baths: BathStatus[] = (previous?.baths ?? []).map((bath) => {
    const update = live.get(bath.bath_number)
    return update ? { ...bath, ...update } : bath
  })

  return {
    baths: baths.length > 0 ? baths : ((payload.baths ?? []) as BathStatus[]),
    timestamp: payload.timestamp ?? previous?.timestamp ?? new Date().toISOString(),
    opcua_connected: payload.opcua_connected ?? previous?.opcua_connected ?? false,
    active_baths: baths.length > 0 ? baths.filter((bath) => bath.in_use).length : previous?.active_baths,
    total_baths: previous?.total_baths ?? (baths.length || undefined),
    active_hangers: payload.active_hangers ?? previous?.active_hangers,
    power_supply: previous?.power_supply,
  }
}
