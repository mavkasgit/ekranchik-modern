import { useEffect, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { WebSocketMessage } from '@/types/dashboard'
import { WS_RECONNECT_INTERVAL } from '@/config/intervals'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseRealtimeDataOptions {
  onMessage?: (message: WebSocketMessage) => void
  autoReconnect?: boolean
  reconnectInterval?: number
}

export function useRealtimeData(options: UseRealtimeDataOptions = {}) {
  const { 
    onMessage, 
    autoReconnect = true, 
    reconnectInterval = WS_RECONNECT_INTERVAL 
  } = options
  
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const queryClient = useQueryClient()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    
    console.log('[WS] Connecting to:', wsUrl)
    setStatus('connecting')
    
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        console.log('[WS] Connected')
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          console.log('[WS] Received:', message.type, message.payload)
          setLastMessage(message)
          onMessage?.(message)

          // Invalidate and refetch queries based on message type
          if (message.type === 'data_update') {
            queryClient.invalidateQueries({ queryKey: ['dashboard'] })
          } else if (message.type === 'unload_event') {
            // Force immediate refetch for unload events
            console.log('[WS] Refetching unload-matched data...')
            queryClient.invalidateQueries({ queryKey: ['dashboard', 'unload-matched'] })
            queryClient.refetchQueries({ queryKey: ['dashboard', 'unload-matched'] })
          }
        } catch (e) {
          console.error('[WS] Failed to parse message:', e)
        }
      }

      ws.onclose = () => {
        console.log('[WS] Disconnected')
        setStatus('disconnected')
        wsRef.current = null
        
        if (autoReconnect) {
          reconnectTimeoutRef.current = window.setTimeout(connect, reconnectInterval)
        }
      }

      ws.onerror = (e) => {
        console.error('[WS] Error:', e)
        setStatus('error')
      }
    } catch (e) {
      setStatus('error')
      console.error('[WS] Connection error:', e)
    }
  }, [onMessage, autoReconnect, reconnectInterval, queryClient])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    
    setStatus('disconnected')
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return {
    status,
    lastMessage,
    connect,
    disconnect,
    isConnected: status === 'connected',
  }
}
