/**
 * Unit tests for OfflineStatus component
 * Feature: catalog-offline-mode
 * Validates: Requirements 3.4, 8.5
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OfflineStatus, formatLastSync } from './OfflineStatus'
import { useOffline } from '@/contexts/OfflineContext'

// Mock the useOffline hook
vi.mock('@/contexts/OfflineContext', () => ({
  useOffline: vi.fn()
}))

describe('OfflineStatus Component - Unit Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Property 6: Timestamp Formatting', () => {
    /**
     * Validates: Requirements 3.4
     * Test: timestamp formats correctly for specific values
     */
    
    it('formats timestamp as "только что" for less than 1 minute', () => {
      const now = Date.now()
      const timestamp = now - 30000 // 30 seconds ago
      
      const result = formatLastSync(timestamp)
      
      expect(result).toBe('Обновлено: только что')
    })

    it('formats timestamp with minutes for 1-59 minutes', () => {
      const now = Date.now()
      
      // Test 1 minute
      const oneMinute = now - 60000
      expect(formatLastSync(oneMinute)).toBe('Обновлено: 1 минуту назад')
      
      // Test 5 minutes
      const fiveMinutes = now - 5 * 60000
      expect(formatLastSync(fiveMinutes)).toBe('Обновлено: 5 минут назад')
      
      // Test 21 minutes (different word form)
      const twentyOneMinutes = now - 21 * 60000
      expect(formatLastSync(twentyOneMinutes)).toBe('Обновлено: 21 минуту назад')
      
      // Test 59 minutes
      const fiftyNineMinutes = now - 59 * 60000
      expect(formatLastSync(fiftyNineMinutes)).toBe('Обновлено: 59 минут назад')
    })

    it('formats timestamp with hours for 1-23 hours', () => {
      const now = Date.now()
      
      // Test 1 hour
      const oneHour = now - 3600000
      expect(formatLastSync(oneHour)).toBe('Обновлено: 1 час назад')
      
      // Test 5 hours
      const fiveHours = now - 5 * 3600000
      expect(formatLastSync(fiveHours)).toBe('Обновлено: 5 часов назад')
      
      // Test 23 hours
      const twentyThreeHours = now - 23 * 3600000
      expect(formatLastSync(twentyThreeHours)).toBe('Обновлено: 23 часа назад')
    })

    it('formats timestamp with days for 24+ hours', () => {
      const now = Date.now()
      
      // Test 1 day
      const oneDay = now - 86400000
      expect(formatLastSync(oneDay)).toBe('Обновлено: 1 день назад')
      
      // Test 3 days
      const threeDays = now - 3 * 86400000
      expect(formatLastSync(threeDays)).toBe('Обновлено: 3 дня назад')
      
      // Test 7 days
      const sevenDays = now - 7 * 86400000
      expect(formatLastSync(sevenDays)).toBe('Обновлено: 7 дней назад')
    })

    it('returns "Данные не синхронизированы" for null timestamp', () => {
      const result = formatLastSync(null)
      
      expect(result).toBe('Данные не синхронизированы')
    })

    it('handles Russian plural forms correctly for minutes', () => {
      const now = Date.now()
      
      // 1 минуту (1, 21, 31, 41, 51)
      expect(formatLastSync(now - 1 * 60000)).toContain('минуту')
      expect(formatLastSync(now - 21 * 60000)).toContain('минуту')
      
      // 2-4 минуты (2, 3, 4, 22, 23, 24, 32, 33, 34)
      expect(formatLastSync(now - 2 * 60000)).toContain('минуты')
      expect(formatLastSync(now - 3 * 60000)).toContain('минуты')
      expect(formatLastSync(now - 4 * 60000)).toContain('минуты')
      
      // 5-20 минут (5, 6, 7, ..., 20, 25, 26, ..., 30)
      expect(formatLastSync(now - 5 * 60000)).toContain('минут')
      expect(formatLastSync(now - 11 * 60000)).toContain('минут')
      expect(formatLastSync(now - 20 * 60000)).toContain('минут')
    })

    it('handles Russian plural forms correctly for hours', () => {
      const now = Date.now()
      
      // 1 час (1, 21)
      expect(formatLastSync(now - 1 * 3600000)).toContain('час')
      expect(formatLastSync(now - 21 * 3600000)).toContain('час')
      
      // 2-4 часа (2, 3, 4, 22, 23)
      expect(formatLastSync(now - 2 * 3600000)).toContain('часа')
      expect(formatLastSync(now - 3 * 3600000)).toContain('часа')
      expect(formatLastSync(now - 4 * 3600000)).toContain('часа')
      
      // 5-20 часов (5, 6, ..., 20)
      expect(formatLastSync(now - 5 * 3600000)).toContain('часов')
      expect(formatLastSync(now - 11 * 3600000)).toContain('часов')
      expect(formatLastSync(now - 20 * 3600000)).toContain('часов')
    })

    it('handles Russian plural forms correctly for days', () => {
      const now = Date.now()
      
      // 1 день (1, 21, 31)
      expect(formatLastSync(now - 1 * 86400000)).toContain('день')
      
      // 2-4 дня (2, 3, 4, 22, 23, 24)
      expect(formatLastSync(now - 2 * 86400000)).toContain('дня')
      expect(formatLastSync(now - 3 * 86400000)).toContain('дня')
      expect(formatLastSync(now - 4 * 86400000)).toContain('дня')
      
      // 5-20 дней (5, 6, ..., 20, 25, 26, ..., 30)
      expect(formatLastSync(now - 5 * 86400000)).toContain('дней')
      expect(formatLastSync(now - 11 * 86400000)).toContain('дней')
      expect(formatLastSync(now - 20 * 86400000)).toContain('дней')
    })
  })

  describe('Property 10: Refresh Loading State', () => {
    /**
     * Validates: Requirements 8.5
     * Test: refresh button shows loading state during refresh
     */
    
    it('shows loading spinner when isRefreshing is true', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: true,
        lastSync: Date.now(),
        forceRefresh: mockForceRefresh,
        isRefreshing: true
      })
      
      render(<OfflineStatus />)
      
      // Find the refresh button
      const refreshButton = screen.getByRole('button', { name: /обновить данные/i })
      
      // Button should be disabled during refresh
      expect(refreshButton).toBeDisabled()
      
      // Button should have spinning icon (animate-spin class)
      const icon = refreshButton.querySelector('svg')
      expect(icon).toHaveClass('animate-spin')
    })

    it('does not show loading spinner when isRefreshing is false', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: true,
        lastSync: Date.now(),
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      // Find the refresh button
      const refreshButton = screen.getByRole('button', { name: /обновить данные/i })
      
      // Button should be enabled when not refreshing
      expect(refreshButton).not.toBeDisabled()
      
      // Button should not have spinning icon
      const icon = refreshButton.querySelector('svg')
      expect(icon).not.toHaveClass('animate-spin')
    })

    it('disables refresh button when offline', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: false,
        lastSync: Date.now(),
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      // Find the refresh button
      const refreshButton = screen.getByRole('button', { name: /обновление недоступно в офлайн режиме/i })
      
      // Button should be disabled when offline
      expect(refreshButton).toBeDisabled()
    })

    it('enables refresh button when online and not refreshing', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: true,
        lastSync: Date.now(),
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      // Find the refresh button
      const refreshButton = screen.getByRole('button', { name: /обновить данные/i })
      
      // Button should be enabled
      expect(refreshButton).not.toBeDisabled()
    })
  })

  describe('Component Integration', () => {
    it('displays online badge when online', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: true,
        lastSync: Date.now(),
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      expect(screen.getByText('Онлайн')).toBeInTheDocument()
    })

    it('displays offline badge when offline', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: false,
        lastSync: Date.now(),
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      expect(screen.getByText('Офлайн')).toBeInTheDocument()
    })

    it('displays formatted last sync timestamp', () => {
      const mockForceRefresh = vi.fn()
      const now = Date.now()
      const fiveMinutesAgo = now - 5 * 60000
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: true,
        lastSync: fiveMinutesAgo,
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      expect(screen.getByText('Обновлено: 5 минут назад')).toBeInTheDocument()
    })

    it('displays "Данные не синхронизированы" when lastSync is null', () => {
      const mockForceRefresh = vi.fn()
      
      vi.mocked(useOffline).mockReturnValue({
        isOnline: true,
        lastSync: null,
        forceRefresh: mockForceRefresh,
        isRefreshing: false
      })
      
      render(<OfflineStatus />)
      
      expect(screen.getByText('Данные не синхронизированы')).toBeInTheDocument()
    })
  })
})
