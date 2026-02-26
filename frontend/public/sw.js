// Service Worker for Catalog Offline Mode
// Version: v1

// Constants
const VERSION = 'v1';
const CACHE_NAMES = {
  catalog: `catalog-data-${VERSION}`,
  images: `catalog-images-${VERSION}`,
  static: `static-assets-${VERSION}`
};

const CACHE_LIMITS = {
  images: 500,
  networkTimeout: 5000
};

// Install event - no precaching (Vite generates dynamic filenames)
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing version:', VERSION);
  
  // Force the waiting service worker to become the active service worker
  self.skipWaiting();
});

// Activate event - cleanup old caches
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating version:', VERSION);
  
  event.waitUntil(
    (async () => {
      if (!isCacheAvailable()) {
        console.warn('[Service Worker] Cache API unavailable during activation');
        return self.clients.claim();
      }
      
      try {
        const cacheNames = await caches.keys();
        
        await Promise.all(
          cacheNames
            .filter(cacheName => {
              // Delete caches that don't match current version
              return !Object.values(CACHE_NAMES).includes(cacheName);
            })
            .map(async cacheName => {
              try {
                console.log('[Service Worker] Deleting old cache:', cacheName);
                await caches.delete(cacheName);
              } catch (error) {
                console.error('[Service Worker] Failed to delete cache:', cacheName, error);
              }
            })
        );
        
        console.log('[Service Worker] Cleanup complete');
      } catch (error) {
        console.error('[Service Worker] Activation cleanup failed:', error);
      }
      
      // Take control of all clients immediately
      return self.clients.claim();
    })()
  );
});

// Helper: Fetch with timeout
function fetchWithTimeout(request, timeout) {
  return Promise.race([
    fetch(request),
    new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Network timeout')), timeout)
    )
  ]);
}

// Helper: Update sync timestamp in IndexedDB
async function updateSyncTimestamp() {
  try {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('catalog-offline', 1);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains('metadata')) {
          db.createObjectStore('metadata', { keyPath: 'key' });
        }
      };
    });
    
    await new Promise((resolve, reject) => {
      const tx = db.transaction('metadata', 'readwrite');
      const store = tx.objectStore('metadata');
      const request = store.put({ key: 'lastSync', value: Date.now() });
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
    
    console.log('[Service Worker] Sync timestamp updated');
  } catch (error) {
    console.error('[Service Worker] Failed to update sync timestamp:', error);
  }
}

// Helper: Update LRU metadata in IndexedDB
async function updateLRUMetadata(url) {
  try {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('catalog-offline', 1);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains('lru')) {
          const lruStore = db.createObjectStore('lru', { keyPath: 'url' });
          lruStore.createIndex('lastUsed', 'lastUsed', { unique: false });
        }
      };
    });
    
    await new Promise((resolve, reject) => {
      const tx = db.transaction('lru', 'readwrite');
      const store = tx.objectStore('lru');
      const request = store.put({ url, lastUsed: Date.now() });
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.error('[Service Worker] Failed to update LRU metadata:', error);
  }
}

// Helper: Get LRU data from IndexedDB
async function getLRUData() {
  try {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('catalog-offline', 1);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
    
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('lru', 'readonly');
      const store = tx.objectStore('lru');
      const index = store.index('lastUsed');
      const request = index.getAll();
      
      request.onsuccess = () => {
        const entries = request.result;
        // Sort by lastUsed ascending (oldest first)
        entries.sort((a, b) => a.lastUsed - b.lastUsed);
        resolve(entries);
      };
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.error('[Service Worker] Failed to get LRU data:', error);
    return [];
  }
}

// Helper: Find oldest entry from LRU data
function findOldestEntry(lruData, cacheKeys) {
  // Create a map of URLs from cache keys
  const cacheUrls = cacheKeys.map(req => req.url);
  
  // Find the oldest entry that exists in cache
  for (const entry of lruData) {
    if (cacheUrls.includes(entry.url)) {
      return entry.url;
    }
  }
  
  // If no LRU data matches, return first cache key
  return cacheKeys[0]?.url;
}

// Helper: Enforce cache limit with LRU eviction
async function enforceCacheLimit(cache, limit) {
  try {
    const keys = await cache.keys();
    
    if (keys.length >= limit) {
      console.log(`[Service Worker] Cache limit reached (${keys.length}/${limit}), evicting oldest entry`);
      
      // Get LRU metadata
      const lruData = await getLRUData();
      
      // Find oldest entry
      const oldestUrl = findOldestEntry(lruData, keys);
      
      if (oldestUrl) {
        await cache.delete(oldestUrl);
        console.log('[Service Worker] Evicted oldest entry:', oldestUrl);
      }
    }
  } catch (error) {
    console.error('[Service Worker] Failed to enforce cache limit:', error);
  }
}

// Helper: Clear 20% of oldest cache entries
async function clearOldestCacheEntries(cache) {
  try {
    const keys = await cache.keys();
    const entriesToDelete = Math.ceil(keys.length * 0.2);
    
    console.log(`[Service Worker] Clearing ${entriesToDelete} oldest entries from cache`);
    
    // Get LRU metadata
    const lruData = await getLRUData();
    
    // Delete oldest entries
    let deleted = 0;
    for (let i = 0; i < lruData.length && deleted < entriesToDelete; i++) {
      const entry = lruData[i];
      const cacheUrls = keys.map(req => req.url);
      
      if (cacheUrls.includes(entry.url)) {
        await cache.delete(entry.url);
        deleted++;
      }
    }
    
    console.log(`[Service Worker] Cleared ${deleted} cache entries`);
  } catch (error) {
    console.error('[Service Worker] Failed to clear oldest cache entries:', error);
    throw error;
  }
}

// Helper: Safe cache put with QuotaExceededError handling
async function safeCachePut(cacheName, request, response) {
  try {
    const cache = await caches.open(cacheName);
    await cache.put(request, response);
    return true;
  } catch (error) {
    if (error.name === 'QuotaExceededError') {
      console.warn('[Service Worker] QuotaExceededError: clearing cache and retrying');
      
      try {
        // Clear 20% of oldest entries
        const cache = await caches.open(cacheName);
        await clearOldestCacheEntries(cache);
        
        // Retry the operation
        await cache.put(request, response);
        console.log('[Service Worker] Cache put succeeded after cleanup');
        return true;
      } catch (retryError) {
        console.error('[Service Worker] Cache put failed after retry:', retryError);
        return false;
      }
    } else {
      console.error('[Service Worker] Cache put failed:', error);
      return false;
    }
  }
}

// Helper: Safe cache match with fallback
async function safeCacheMatch(request) {
  try {
    return await caches.match(request);
  } catch (error) {
    console.error('[Service Worker] Cache read failed:', error);
    return null;
  }
}

// Helper: Check if Cache API is available
function isCacheAvailable() {
  return typeof caches !== 'undefined';
}

// Network First strategy for catalog data
async function networkFirstStrategy(request) {
  try {
    // Try network with timeout
    const networkResponse = await fetchWithTimeout(request, CACHE_LIMITS.networkTimeout);
    
    // Update cache in background if Cache API is available
    if (isCacheAvailable()) {
      safeCachePut(CACHE_NAMES.catalog, request, networkResponse.clone())
        .catch(error => console.error('[Service Worker] Background cache update failed:', error));
      
      // Update sync timestamp in background
      updateSyncTimestamp();
    } else {
      console.warn('[Service Worker] Cache API unavailable, operating in network-only mode');
    }
    
    console.log('[Service Worker] Network First: served from network');
    return networkResponse;
  } catch (error) {
    console.log('[Service Worker] Network First: network failed, trying cache');
    
    // Fallback to cache if available
    if (isCacheAvailable()) {
      const cachedResponse = await safeCacheMatch(request);
      
      if (cachedResponse) {
        console.log('[Service Worker] Network First: served from cache');
        return cachedResponse;
      }
      
      console.error('[Service Worker] Network First: no cache available');
    } else {
      console.error('[Service Worker] Network First: Cache API unavailable');
    }
    
    // No cache available or Cache API unavailable, throw error
    throw error;
  }
}

// Network First strategy for app shell (HTML, JS, CSS)
async function networkFirstForAppShell(request) {
  const url = new URL(request.url);
  
  try {
    const networkResponse = await fetch(request);
    
    // Cache successful responses
    if (isCacheAvailable() && networkResponse.ok) {
      safeCachePut(CACHE_NAMES.static, request, networkResponse.clone())
        .catch(error => console.error('[Service Worker] App shell cache failed:', error));
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[Service Worker] App shell: network failed, trying cache');
    
    if (isCacheAvailable()) {
      // Try to get from cache
      let cachedResponse = await safeCacheMatch(request);
      
      if (cachedResponse) {
        console.log('[Service Worker] App shell: served from cache');
        return cachedResponse;
      }
      
      // For navigation requests (HTML pages), fallback to index.html
      // This is needed for SPA routing to work offline
      if (request.mode === 'navigate' || request.destination === 'document' || 
          (!url.pathname.includes('.') && request.method === 'GET')) {
        console.log('[Service Worker] App shell: navigation request, trying index');
        cachedResponse = await safeCacheMatch('/');
        
        if (cachedResponse) {
          console.log('[Service Worker] App shell: served index.html from cache');
          return cachedResponse;
        }
      }
    }
    
    throw error;
  }
}

// Cache First strategy for images
async function cacheFirstStrategy(request) {
  // Check if Cache API is available
  if (!isCacheAvailable()) {
    console.warn('[Service Worker] Cache API unavailable, fetching from network');
    try {
      return await fetch(request);
    } catch (error) {
      console.error('[Service Worker] Network fetch failed and Cache API unavailable:', error);
      throw error;
    }
  }
  
  try {
    // Check cache first
    const cachedResponse = await safeCacheMatch(request);
    
    if (cachedResponse) {
      console.log('[Service Worker] Cache First: served from cache');
      
      // Update LRU metadata in background (don't await)
      updateLRUMetadata(request.url);
      
      return cachedResponse;
    }
    
    console.log('[Service Worker] Cache First: cache miss, fetching from network');
    
    // Fetch from network
    let networkResponse;
    try {
      networkResponse = await fetch(request);
    } catch (networkError) {
      console.error('[Service Worker] Cache First: network fetch failed:', networkError);
      
      // Try to return placeholder
      const placeholderResponse = await safeCacheMatch('/placeholder-image.svg');
      if (placeholderResponse) {
        console.log('[Service Worker] Cache First: returning placeholder');
        return placeholderResponse;
      }
      
      throw networkError;
    }
    
    // Store in cache with LRU management
    try {
      const cache = await caches.open(CACHE_NAMES.images);
      
      // Enforce cache limit before adding new entry
      await enforceCacheLimit(cache, CACHE_LIMITS.images);
      
      // Add to cache with QuotaExceededError handling
      await safeCachePut(CACHE_NAMES.images, request, networkResponse.clone());
      
      // Update LRU metadata
      await updateLRUMetadata(request.url);
      
      console.log('[Service Worker] Cache First: cached and served from network');
    } catch (cacheError) {
      console.error('[Service Worker] Cache First: caching failed, serving from network anyway:', cacheError);
      // Continue and return network response even if caching failed
    }
    
    return networkResponse;
  } catch (error) {
    console.error('[Service Worker] Cache First: error occurred:', error);
    
    // Final fallback: try to return placeholder
    const placeholderResponse = await safeCacheMatch('/placeholder-image.svg');
    if (placeholderResponse) {
      console.log('[Service Worker] Cache First: returning placeholder after error');
      return placeholderResponse;
    }
    
    // If placeholder not available, throw error
    throw error;
  }
}

// Fetch event - route requests to appropriate strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Only handle same-origin requests
  if (url.origin !== self.location.origin) {
    return;
  }
  
  // Route to appropriate caching strategy
  if (url.pathname.startsWith('/api/catalog')) {
    // Network First strategy for catalog data
    event.respondWith(networkFirstStrategy(request));
  } else if (url.pathname.startsWith('/static/photos') || 
             url.pathname.startsWith('/static/thumbnails')) {
    // Cache First strategy for images
    event.respondWith(cacheFirstStrategy(request));
  } else if (
    request.method === 'GET' && 
    (url.pathname.endsWith('.js') || 
     url.pathname.endsWith('.css') || 
     url.pathname === '/' ||
     url.pathname.startsWith('/@') || // Vite HMR
     !url.pathname.includes('.'))  // HTML pages
  ) {
    // Network First for app shell (HTML, JS, CSS)
    event.respondWith(networkFirstForAppShell(request));
  }
  // Other requests pass through without caching
});

// Error handling
self.addEventListener('error', (event) => {
  console.error('[Service Worker] Error:', event.error);
});

// Unhandled promise rejections
self.addEventListener('unhandledrejection', (event) => {
  console.error('[Service Worker] Unhandled rejection:', event.reason);
});
