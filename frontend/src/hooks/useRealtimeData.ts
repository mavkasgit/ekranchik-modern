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
    autoReconnect = true
  } = options
  
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const onMessageRef = useRef(onMessage)
  const queryClient = useQueryClient()
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttemptsRef = useRef(10)
  const isUnmountingRef = useRef(false)
  
  // Keep onMessage ref updated without triggering reconnects
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  const connect = useCallback(() => {
    // Prevent multiple connections
    if (wsRef.current?.readyState === WebSocket.OPEN || 
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[WS] Already connecting or connected, skipping')
      return
    }

    // Prevent reconnection attempts if unmounting
    if (isUnmountingRef.current) {
      return
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s max
    const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 60000)
    
    if (reconnectAttemptsRef.current > 0) {
      console.log(`[WS] Reconnect attempt ${reconnectAttemptsRef.current}, waiting ${delay}ms`)
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    
    console.log('[WS] Connecting to:', wsUrl)
    setStatus('connecting')
    
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      // Set connection timeout
      const connectionTimeout = setTimeout(() => {
        if (ws.readyState === WebSocket.CONNECTING) {
          console.warn('[WS] Connection timeout, closing')
          ws.close()
        }
      }, 10000) // 10 second timeout

      ws.onopen = () => {
        clearTimeout(connectionTimeout)
        reconnectAttemptsRef.current = 0 // Reset on successful connection
        setStatus('connected')
        console.log('[WS] Connected successfully')
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          console.log('[WS] Received:', message.type)
          setLastMessage(message)
          onMessageRef.current?.(message)

          // Invalidate and refetch queries based on message type
          if (message.type === 'data_update') {
            queryClient.invalidateQueries({ queryKey: ['dashboard'] })
          } else if (message.type === 'unload_event') {
            console.log('[WS] Refetching unload-matched data...')
            queryClient.invalidateQueries({ queryKey: ['dashboard', 'unload-matched'] })
            queryClient.refetchQueries({ queryKey: ['dashboard', 'unload-matched'] })
          } else if (message.type === 'opcua_status' || message.type === 'heartbeat') {
            queryClient.invalidateQueries({ queryKey: ['opcua'] })
          }
        } catch (e) {
          console.error('[WS] Failed to parse message:', e)
        }
      }

      ws.onclose = () => {
        clearTimeout(connectionTimeout)
        console.log('[WS] Disconnected')
        setStatus('disconnected')
        wsRef.current = null
        
        if (autoReconnect && !isUnmountingRef.current) {
          reconnectAttemptsRef.current++
          
          if (reconnectAttemptsRef.current <= maxReconnectAttemptsRef.current) {
            const nextDelay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 60000)
            console.log(`[WS] Scheduling reconnect in ${nextDelay}ms (attempt ${reconnectAttemptsRef.current})`)
            reconnectTimeoutRef.current = window.setTimeout(connect, nextDelay)
          } else {
            console.error('[WS] Max reconnection attempts reached')
            setStatus('error')
          }
        }
      }

      ws.onerror = (e) => {
        console.error('[WS] WebSocket error:', e)
        setStatus('error')
      }
    } catch (e) {
      setStatus('error')
      console.error('[WS] Connection error:', e)
      
      if (autoReconnect && !isUnmountingRef.current) {
        reconnectAttemptsRef.current++
        if (reconnectAttemptsRef.current <= maxReconnectAttemptsRef.current) {
          const nextDelay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 60000)
          reconnectTimeoutRef.current = window.setTimeout(connect, nextDelay)
        }
      }
    }
  }, [autoReconnect, queryClient])

  const disconnect = useCallback(() => {
    isUnmountingRef.current = true
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    
    if (wsRef.current) {
      try {
        wsRef.current.close()
      } catch (e) {
        console.warn('[WS] Error closing WebSocket:', e)
      }
      wsRef.current = null
    }
    
    setStatus('disconnected')
  }, [])

  useEffect(() => {
    isUnmountingRef.current = false
    reconnectAttemptsRef.current = 0
    connect()
    
    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  return {
    status,
    lastMessage,
    connect,
    disconnect,
    isConnected: status === 'connected',
  }
}
