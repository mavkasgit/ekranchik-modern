import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { applyRealtimeMessage } from './applyMessage'
import type { WebSocketMessage } from '@/types/dashboard'
import type { LineStatus } from '@/types/line'

const DASHBOARD_KEY = ['dashboard', 7, 100, true] as const
const MATCHED_KEY = ['dashboard', 'opcuaMatchedUnloadEvents', 100] as const
const OPCUA_STATUS_KEY = ['dashboard', 'opcuaStatus'] as const
const LINE_KEY = ['line', 'status'] as const

function message(
  type: WebSocketMessage['type'],
  payload: Record<string, unknown> = {},
): WebSocketMessage {
  return { type, payload, timestamp: '2026-09-12T10:00:00Z' }
}

function seededClient(): QueryClient {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(DASHBOARD_KEY, { success: true })
  client.setQueryData(MATCHED_KEY, [{ hanger: 777 }])
  client.setQueryData(OPCUA_STATUS_KEY, { is_open: true })
  client.setQueryData<LineStatus>(LINE_KEY, {
    baths: [
      {
        bath_number: 30,
        in_use: true,
        pallete: 777,
        in_time: 10,
        out_time: 310,
        free: false,
        article: 'П-1',
        color: 'серебро',
      },
    ],
    timestamp: '2026-09-12T09:59:00Z',
    opcua_connected: true,
    power_supply: { current: 1, voltage: 2 },
  })
  return client
}

function isInvalidated(client: QueryClient, key: readonly unknown[]): boolean {
  return client.getQueryState(key)?.isInvalidated === true
}

describe('applyRealtimeMessage', () => {
  it('обновление Excel помечает данные дашборда устаревшими', () => {
    const client = seededClient()

    applyRealtimeMessage(client, message('data_update', { source: 'excel' }))

    expect(isInvalidated(client, DASHBOARD_KEY)).toBe(true)
    expect(isInvalidated(client, MATCHED_KEY)).toBe(true)
  })

  it('статус OPC UA обновляет только свой запрос', () => {
    const client = seededClient()

    applyRealtimeMessage(client, message('opcua_status', { connected: false }))

    expect(isInvalidated(client, OPCUA_STATUS_KEY)).toBe(true)
    expect(isInvalidated(client, DASHBOARD_KEY)).toBe(false)
  })

  it('событие выгрузки обновляет данные дашборда и сопоставленные события', () => {
    const client = seededClient()

    applyRealtimeMessage(client, message('unload_event', { hanger: 777 }))

    expect(isInvalidated(client, DASHBOARD_KEY)).toBe(true)
    expect(isInvalidated(client, MATCHED_KEY)).toBe(true)
  })

  it('обновление линии кладёт счётчики ванн в кэш, сохраняя данные из HTTP', () => {
    const client = seededClient()

    applyRealtimeMessage(
      client,
      message('line_update', {
        baths: [{ bath_number: 30, in_use: true, pallete: 777, in_time: 42, out_time: 300 }],
        opcua_connected: true,
        active_hangers: 1,
      }),
    )

    const line = client.getQueryData<LineStatus>(LINE_KEY)
    expect(line?.baths[0]).toMatchObject({ in_time: 42, out_time: 300, article: 'П-1', color: 'серебро' })
    expect(line?.active_hangers).toBe(1)
    expect(isInvalidated(client, LINE_KEY)).toBe(false)
  })

  it('служебные сообщения не трогают кэш', () => {
    const client = seededClient()

    applyRealtimeMessage(client, message('heartbeat'))
    applyRealtimeMessage(client, message('ping'))

    expect(isInvalidated(client, DASHBOARD_KEY)).toBe(false)
    expect(isInvalidated(client, OPCUA_STATUS_KEY)).toBe(false)
    expect(client.getQueryData<LineStatus>(LINE_KEY)?.timestamp).toBe('2026-09-12T09:59:00Z')
  })
})
