/**
 * Service Worker Registration Module
 * 
 * Handles registration and lifecycle management of the Service Worker.
 * Registers automatically if the browser supports Service Workers.
 */

import type { ServiceWorkerConfig } from './types/serviceWorker'

export type { ServiceWorkerConfig }

/**
 * Register the Service Worker
 * 
 * Requirements: 5.1, 5.2, 5.3, 5.4
 * - Registers SW automatically if browser supports it
 * - Provides callbacks for success, update, and error events
 * - Handles updatefound event for SW updates
 * - Logs registration success/failure to console
 */
export function register(config?: ServiceWorkerConfig): void {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      const swUrl = '/sw.js'
      
      navigator.serviceWorker
        .register(swUrl, { scope: '/' })
        .then(registration => {
          console.log('Service Worker registered:', registration.scope)
          config?.onSuccess?.(registration)
          
          // Check for updates
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing
            
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  // New service worker available
                  console.log('New Service Worker available')
                  config?.onUpdate?.(registration)
                }
              })
            }
          })
        })
        .catch(error => {
          console.error('Service Worker registration failed:', error)
          config?.onError?.(error)
        })
    })
  } else {
    console.warn('Service Worker is not supported in this browser')
  }
}

/**
 * Unregister the Service Worker
 * 
 * Useful for cleanup or disabling offline functionality
 */
export function unregister(): void {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready
      .then(registration => {
        registration.unregister()
        console.log('Service Worker unregistered')
      })
      .catch(error => {
        console.error('Service Worker unregister failed:', error)
      })
  }
}
