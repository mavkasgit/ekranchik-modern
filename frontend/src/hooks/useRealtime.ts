import { useEffect, useRef, useSyncExternalStore } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { realtime, type RealtimeState } from '@/realtime/connection'
import { applyRealtimeMessage } from '@/realtime/applyMessage'
import type { WebSocketMessage } from '@/types/dashboard'

export interface RealtimeConnectionState extends RealtimeState {
  isConnected: boolean
}

/** Состояние канала: статус, последнее сообщение и признак живого соединения. */
export function useRealtimeConnection(): RealtimeConnectionState {
  const state = useSyncExternalStore(realtime.subscribe, realtime.getState)

  useEffect(() => realtime.acquire(), [])

  return { ...state, isConnected: state.status === 'connected' }
}

/** Типизированная подписка на один вид сообщения сервера. */
export function useRealtimeEvent(
  type: WebSocketMessage['type'],
  handler: (message: WebSocketMessage) => void,
): void {
  const { lastMessage } = useRealtimeConnection()
  const handlerRef = useRef(handler)
  useEffect(() => {
    handlerRef.current = handler
  }, [handler])

  useEffect(() => {
    if (lastMessage?.type === type) handlerRef.current(lastMessage)
  }, [lastMessage, type])
}

/** Связывает канал с кэшем запросов: приложение владеет каналом целиком. */
export function useRealtimeBridge(): void {
  const client = useQueryClient()

  useEffect(() => {
    const release = realtime.acquire()
    realtime.setMessageHandler((message) => applyRealtimeMessage(client, message))

    return () => {
      realtime.setMessageHandler(null)
      release()
    }
  }, [client])
}
