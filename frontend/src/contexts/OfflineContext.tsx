/**
 * Offline Context for managing online/offline state and data synchronization
 * Provides: isOnline status, lastSync timestamp, forceRefresh function
 * Requirements: 3.1, 3.2, 3.3, 4.3, 8.1, 8.2, 8.3
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { loadLastSync, saveLastSync } from '../utils/indexedDB'
import type { OfflineContextValue } from '../types/serviceWorker'

export type { OfflineContextValue }

const OfflineContext = createContext<OfflineContextValue | undefined>(undefined)

interface OfflineProviderProps {
  children: ReactNode
}

export function OfflineProvider({ children }: OfflineProviderProps) {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [lastSync, setLastSync] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  
  // Listen to online/offline events
  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])
  
  // Load last sync timestamp from IndexedDB on mount
  useEffect(() => {
    loadLastSync()
      .then(setLastSync)
      .catch(error => {
        console.error('Failed to load last sync timestamp:', error)
      })
  }, [])
  
  // Force refresh function with cache bypass
  const forceRefresh = async () => {
    setIsRefreshing(true)
    try {
      // Fetch with cache: 'reload' to bypass cache
      const response = await fetch('/api/catalog/all', { cache: 'reload' })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      // Update cache through Cache API
      const cache = await caches.open('catalog-data-v1')
      await cache.put('/api/catalog/all', new Response(JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
      }))
      
      // Update timestamp
      const timestamp = Date.now()
      await saveLastSync(timestamp)
      setLastSync(timestamp)
    } catch (error) {
      console.error('Force refresh failed:', error)
      throw error
    } finally {
      setIsRefreshing(false)
    }
  }
  
  return (
    <OfflineContext.Provider value={{ isOnline, lastSync, forceRefresh, isRefreshing }}>
      {children}
    </OfflineContext.Provider>
  )
}

/**
 * Hook to access offline context
 * @throws Error if used outside OfflineProvider
 */
export function useOffline(): OfflineContextValue {
  const context = useContext(OfflineContext)
  if (context === undefined) {
    throw new Error('useOffline must be used within an OfflineProvider')
  }
  return context
}
