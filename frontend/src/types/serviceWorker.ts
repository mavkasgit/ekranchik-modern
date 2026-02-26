/**
 * TypeScript type definitions for Service Worker, Cache API, and IndexedDB operations
 * Used for catalog offline mode functionality
 * 
 * Note: These types extend the built-in Service Worker types from lib.webworker.d.ts
 * For use in Service Worker context, ensure tsconfig includes "webworker" in lib array
 */

// ============================================================================
// Service Worker Event Types
// ============================================================================

/**
 * Service Worker install event
 */
export interface ServiceWorkerInstallEvent extends Event {
  readonly type: 'install'
  waitUntil(promise: Promise<any>): void
}

/**
 * Service Worker activate event
 */
export interface ServiceWorkerActivateEvent extends Event {
  readonly type: 'activate'
  waitUntil(promise: Promise<any>): void
}

/**
 * Service Worker fetch event
 */
export interface ServiceWorkerFetchEvent extends Event {
  readonly type: 'fetch'
  readonly request: Request
  respondWith(response: Promise<Response> | Response): void
  waitUntil(promise: Promise<any>): void
}

/**
 * Service Worker message event
 */
export interface ServiceWorkerMessageEvent extends Event {
  readonly type: 'message'
  readonly data: any
  readonly source: MessageEventSource | null
  waitUntil(promise: Promise<any>): void
}

/**
 * Message event source (Client, ServiceWorker, or MessagePort)
 */
export type MessageEventSource = ServiceWorker | MessagePort | object

// ============================================================================
// Cache API Types
// ============================================================================

/**
 * Cache names configuration
 */
export interface CacheNames {
  catalog: string
  images: string
  static: string
}

/**
 * Cache limits configuration
 */
export interface CacheLimits {
  images: number
  networkTimeout: number
}

/**
 * Cache entry metadata
 */
export interface CacheEntryMetadata {
  url: string
  timestamp: number
  size?: number
}

/**
 * Cache strategy type
 */
export type CacheStrategy = 'network-first' | 'cache-first' | 'stale-while-revalidate'

/**
 * Cache operation result
 */
export interface CacheOperationResult {
  success: boolean
  error?: Error
  fromCache: boolean
}

// ============================================================================
// IndexedDB Types
// ============================================================================

/**
 * Metadata entry stored in IndexedDB
 */
export interface MetadataEntry {
  key: string
  value: any
}

/**
 * LRU (Least Recently Used) entry for cache management
 */
export interface LRUEntry {
  url: string
  lastUsed: number
}

/**
 * IndexedDB database configuration
 */
export interface IndexedDBConfig {
  name: string
  version: number
  stores: {
    metadata: string
    lru: string
  }
}

/**
 * IndexedDB transaction mode
 */
export type IDBTransactionMode = 'readonly' | 'readwrite' | 'versionchange'

// ============================================================================
// Service Worker Registration Types
// ============================================================================

/**
 * Service Worker registration configuration
 */
export interface ServiceWorkerConfig {
  onSuccess?: (registration: ServiceWorkerRegistration) => void
  onUpdate?: (registration: ServiceWorkerRegistration) => void
  onError?: (error: Error) => void
}

/**
 * Service Worker registration result
 */
export interface ServiceWorkerRegistrationResult {
  success: boolean
  registration?: ServiceWorkerRegistration
  error?: Error
}

// ============================================================================
// Offline Context Types
// ============================================================================

/**
 * Offline context value provided to React components
 */
export interface OfflineContextValue {
  isOnline: boolean
  lastSync: number | null
  forceRefresh: () => Promise<void>
  isRefreshing: boolean
}

/**
 * Sync status information
 */
export interface SyncStatus {
  isOnline: boolean
  lastSync: number | null
  source: 'network' | 'cache'
}

// ============================================================================
// Caching Strategy Function Types
// ============================================================================

/**
 * Network first strategy function signature
 */
export type NetworkFirstStrategy = (request: Request) => Promise<Response>

/**
 * Cache first strategy function signature
 */
export type CacheFirstStrategy = (request: Request) => Promise<Response>

/**
 * Fetch with timeout function signature
 */
export type FetchWithTimeout = (request: Request, timeout: number) => Promise<Response>

// ============================================================================
// Helper Function Types
// ============================================================================

/**
 * Update sync timestamp function signature
 */
export type UpdateSyncTimestamp = () => Promise<void>

/**
 * Update LRU metadata function signature
 */
export type UpdateLRUMetadata = (url: string) => Promise<void>

/**
 * Get LRU data function signature
 */
export type GetLRUData = () => Promise<LRUEntry[]>

/**
 * Enforce cache limit function signature
 */
export type EnforceCacheLimit = (cache: Cache, limit: number) => Promise<void>

/**
 * Safe cache put function signature
 */
export type SafeCachePut = (cacheName: string, request: Request, response: Response) => Promise<boolean>

/**
 * Safe cache match function signature
 */
export type SafeCacheMatch = (request: Request) => Promise<Response | undefined>

// ============================================================================
// Error Types
// ============================================================================

/**
 * Cache error types
 */
export type CacheErrorType = 
  | 'QuotaExceededError'
  | 'NetworkError'
  | 'TimeoutError'
  | 'CacheUnavailable'
  | 'IndexedDBUnavailable'

/**
 * Cache error with type information
 */
export interface CacheError extends Error {
  type: CacheErrorType
  originalError?: Error
}

// ============================================================================
// Service Worker Global Scope Types
// ============================================================================

/**
 * Service Worker clients interface
 */
export interface ServiceWorkerClients {
  claim(): Promise<void>
  get(id: string): Promise<ServiceWorkerClient | undefined>
  matchAll(options?: ClientQueryOptions): Promise<ServiceWorkerClient[]>
  openWindow(url: string): Promise<WindowClient | null>
}

/**
 * Service Worker client
 */
export interface ServiceWorkerClient {
  readonly id: string
  readonly type: ClientType
  readonly url: string
  postMessage(message: any, transfer?: Transferable[]): void
}

/**
 * Window client (extends ServiceWorkerClient)
 */
export interface WindowClient extends ServiceWorkerClient {
  readonly focused: boolean
  readonly visibilityState: DocumentVisibilityState
  focus(): Promise<WindowClient>
  navigate(url: string): Promise<WindowClient>
}

/**
 * Client query options
 */
export interface ClientQueryOptions {
  includeUncontrolled?: boolean
  type?: ClientType
}

/**
 * Client type
 */
export type ClientType = 'window' | 'worker' | 'sharedworker' | 'all'

/**
 * Document visibility state
 */
export type DocumentVisibilityState = 'hidden' | 'visible' | 'prerender'

/**
 * Service Worker global scope (for use in sw.js)
 * Note: In actual Service Worker context, use the global 'self' object
 */
export interface ServiceWorkerGlobalScope {
  readonly clients: ServiceWorkerClients
  readonly registration: ServiceWorkerRegistration
  skipWaiting(): Promise<void>
  addEventListener(type: 'install', listener: (event: ServiceWorkerInstallEvent) => void): void
  addEventListener(type: 'activate', listener: (event: ServiceWorkerActivateEvent) => void): void
  addEventListener(type: 'fetch', listener: (event: ServiceWorkerFetchEvent) => void): void
  addEventListener(type: 'message', listener: (event: ServiceWorkerMessageEvent) => void): void
}

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Timestamp in milliseconds (Unix epoch)
 */
export type Timestamp = number

/**
 * URL string
 */
export type URLString = string

/**
 * Cache version identifier
 */
export type CacheVersion = string
