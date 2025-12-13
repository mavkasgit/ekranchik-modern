import { useEffect, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { WebSocketMessage } from '@/types/dashboard'

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
    reconnectInterval = 5000 
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
    
    setStatus('connecting')
    
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        console.log('WebSocket connected')
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          setLastMessage(message)
          onMessage?.(message)

          // Invalidate queries based on message type
          if (message.type === 'data_update') {
            queryClient.invalidateQueries({ queryKey: ['dashboard'] })
          } else if (message.type === 'unload_event') {
            queryClient.invalidateQueries({ queryKey: ['dashboard', 'events'] })
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onclose = () => {
        setStatus('disconnected')
        wsRef.current = null
        
        if (autoReconnect) {
          reconnectTimeoutRef.current = window.setTimeout(connect, reconnectInterval)
        }
      }

      ws.onerror = () => {
        setStatus('error')
      }
    } catch (e) {
      setStatus('error')
      console.error('WebSocket connection error:', e)
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
