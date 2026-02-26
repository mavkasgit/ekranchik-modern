/**
 * IndexedDB utilities for catalog offline mode
 * Manages metadata storage (sync timestamps) and LRU cache tracking
 */

import type { MetadataEntry, LRUEntry } from '../types/serviceWorker'

const DB_NAME = 'catalog-offline'
const DB_VERSION = 1

export type { MetadataEntry, LRUEntry }

/**
 * Opens the IndexedDB database and creates object stores if needed
 * @returns Promise resolving to the database instance
 */
export async function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    
    request.onerror = () => reject(request.error)
    request.onsuccess = () => resolve(request.result)
    
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result
      
      // Metadata store for sync timestamps and other metadata
      if (!db.objectStoreNames.contains('metadata')) {
        db.createObjectStore('metadata', { keyPath: 'key' })
      }
      
      // LRU store for tracking image cache usage
      if (!db.objectStoreNames.contains('lru')) {
        const lruStore = db.createObjectStore('lru', { keyPath: 'url' })
        lruStore.createIndex('lastUsed', 'lastUsed', { unique: false })
      }
    }
  })
}

/**
 * Saves the last sync timestamp to IndexedDB
 * @param timestamp Unix timestamp in milliseconds
 */
export async function saveLastSync(timestamp: number): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('metadata', 'readwrite')
    const store = tx.objectStore('metadata')
    const request = store.put({ key: 'lastSync', value: timestamp })
    
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
}

/**
 * Loads the last sync timestamp from IndexedDB
 * @returns Promise resolving to timestamp or null if not found
 */
export async function loadLastSync(): Promise<number | null> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('metadata', 'readonly')
    const store = tx.objectStore('metadata')
    const request = store.get('lastSync')
    
    request.onsuccess = () => {
      const result = request.result as MetadataEntry | undefined
      resolve(result?.value ?? null)
    }
    request.onerror = () => reject(request.error)
  })
}

/**
 * Updates LRU metadata for a cached resource
 * @param url URL of the cached resource
 */
export async function updateLRUMetadata(url: string): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('lru', 'readwrite')
    const store = tx.objectStore('lru')
    const request = store.put({ url, lastUsed: Date.now() })
    
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
}

/**
 * Gets all LRU data sorted by last used time (oldest first)
 * @returns Promise resolving to array of LRU entries
 */
export async function getLRUData(): Promise<LRUEntry[]> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('lru', 'readonly')
    const store = tx.objectStore('lru')
    const index = store.index('lastUsed')
    const request = index.getAll()
    
    request.onsuccess = () => {
      const entries = request.result as LRUEntry[]
      // Sort by lastUsed ascending (oldest first)
      entries.sort((a, b) => a.lastUsed - b.lastUsed)
      resolve(entries)
    }
    request.onerror = () => reject(request.error)
  })
}

/**
 * Clears all caches and IndexedDB data
 * Used for complete cache reset
 */
export async function clearCache(): Promise<void> {
  // Clear Cache API
  const cacheNames = await caches.keys()
  await Promise.all(cacheNames.map(name => caches.delete(name)))
  
  // Clear IndexedDB
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['metadata', 'lru'], 'readwrite')
    const metadataStore = tx.objectStore('metadata')
    const lruStore = tx.objectStore('lru')
    
    metadataStore.clear()
    lruStore.clear()
    
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
