import { useEffect, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { WebSocketMessage } from '@/types/dashboard'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseRealtimeDataOptions {
  onMessage?: (message: WebSocketMessage) => void
  autoReconnect?: boolean
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
  const connectionTimeoutRef = useRef<number | null>(null)
  const onMessageRef = useRef(onMessage)
  const queryClient = useQueryClient()
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttemptsRef = useRef(10)
  const isUnmountingRef = useRef(false)
  const isConnectingRef = useRef(false)
  
  // Keep onMessage ref updated without triggering reconnects
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current) {
      console.log('[WS] Already attempting to connect, skipping')
      return
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WS] Already connected, skipping')
      return
    }

    // Prevent reconnection attempts if unmounting
    if (isUnmountingRef.current) {
      console.log('[WS] Component unmounting, skipping connection')
      return
    }

    isConnectingRef.current = true

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s max
    const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 60000)
    
    if (reconnectAttemptsRef.current > 0) {
      console.log(`[WS] Reconnect attempt ${reconnectAttemptsRef.current}, waiting ${delay}ms`)
      
      // Schedule connection after delay
      reconnectTimeoutRef.current = window.setTimeout(() => {
        if (!isUnmountingRef.current) {
          connect()
        }
        isConnectingRef.current = false
      }, delay)
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    
    console.log('[WS] Connecting to:', wsUrl)
    setStatus('connecting')
    
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      // Set connection timeout - close if not connected within 10 seconds
      connectionTimeoutRef.current = window.setTimeout(() => {
        if (ws.readyState === WebSocket.CONNECTING) {
          console.warn('[WS] Connection timeout, closing')
          ws.close(1000, 'Connection timeout')
        }
      }, 10000)

      ws.onopen = () => {
        if (connectionTimeoutRef.current) {
          clearTimeout(connectionTimeoutRef.current)
          connectionTimeoutRef.current = null
        }
        
        if (isUnmountingRef.current) {
          console.log('[WS] Connected but component unmounting, closing')
          ws.close()
          return
        }
        
        reconnectAttemptsRef.current = 0 // Reset on successful connection
        setStatus('connected')
        isConnectingRef.current = false
        console.log('[WS] Connected successfully')
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          
          // Don't log heartbeat messages to reduce console spam
          if (message.type !== 'heartbeat') {
            console.log('[WS] Received:', message.type)
          }
          
          setLastMessage(message)
          onMessageRef.current?.(message)

          // Invalidate and refetch queries based on message type
          if (message.type === 'data_update') {
            queryClient.invalidateQueries({ queryKey: ['dashboard'] })
          } else if (message.type === 'unload_event') {
            console.log('[WS] Refetching unload-matched data...')
            queryClient.invalidateQueries({ queryKey: ['dashboard', 'unload-matched'] })
            queryClient.refetchQueries({ queryKey: ['dashboard', 'unload-matched'] })
          } else if (message.type === 'opcua_status') {
            queryClient.invalidateQueries({ queryKey: ['opcua'] })
          }
        } catch (e) {
          console.error('[WS] Failed to parse message:', e)
        }
      }

      ws.onclose = () => {
        if (connectionTimeoutRef.current) {
          clearTimeout(connectionTimeoutRef.current)
          connectionTimeoutRef.current = null
        }
        
        console.log('[WS] Disconnected')
        setStatus('disconnected')
        wsRef.current = null
        isConnectingRef.current = false
        
        if (autoReconnect && !isUnmountingRef.current) {
          reconnectAttemptsRef.current++
          
          if (reconnectAttemptsRef.current <= maxReconnectAttemptsRef.current) {
            const nextDelay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 60000)
            console.log(`[WS] Scheduling reconnect in ${nextDelay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttemptsRef.current})`)
            reconnectTimeoutRef.current = window.setTimeout(connect, nextDelay)
          } else {
            console.error('[WS] Max reconnection attempts reached')
            setStatus('error')
          }
        }
      }

      ws.onerror = (event) => {
        console.error('[WS] WebSocket error:', event)
        setStatus('error')
        isConnectingRef.current = false
      }
    } catch (e) {
      setStatus('error')
      console.error('[WS] Connection error:', e)
      isConnectingRef.current = false
      
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
    console.log('[WS] Disconnecting...')
    isUnmountingRef.current = true
    isConnectingRef.current = false
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    
    if (connectionTimeoutRef.current) {
      clearTimeout(connectionTimeoutRef.current)
      connectionTimeoutRef.current = null
    }
    
    if (wsRef.current) {
      try {
        if (wsRef.current.readyState === WebSocket.OPEN || 
            wsRef.current.readyState === WebSocket.CONNECTING) {
          wsRef.current.close(1000, 'Component unmounting')
        }
      } catch (e) {
        console.warn('[WS] Error closing WebSocket:', e)
      }
      wsRef.current = null
    }
    
    setStatus('disconnected')
  }, [])

  useEffect(() => {
    // Reset state on mount
    isUnmountingRef.current = false
    isConnectingRef.current = false
    reconnectAttemptsRef.current = 0
    
    // Connect on mount
    connect()
    
    // Cleanup on unmount
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
