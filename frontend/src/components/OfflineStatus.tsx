/**
 * OfflineStatus Component
 * Displays online/offline status, last sync timestamp, and refresh button
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.4, 8.1, 8.5
 */

import { useOffline } from '@/contexts/OfflineContext'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Wifi, WifiOff, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

interface OfflineStatusProps {
  className?: string
}

/**
 * Formats a timestamp into a human-readable relative time string
 * @param timestamp - Unix timestamp in milliseconds, or null
 * @returns Formatted string like "5 минут назад", "2 часа назад", "3 дня назад"
 * Requirements: 3.4
 */
export function formatLastSync(timestamp: number | null): string {
  if (!timestamp) {
    return 'Данные не синхронизированы'
  }
  
  const now = Date.now()
  const diff = now - timestamp
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  
  if (minutes < 1) {
    return 'Обновлено: только что'
  }
  
  if (minutes < 60) {
    return `Обновлено: ${minutes} ${getMinutesWord(minutes)} назад`
  }
  
  if (hours < 24) {
    return `Обновлено: ${hours} ${getHoursWord(hours)} назад`
  }
  
  return `Обновлено: ${days} ${getDaysWord(days)} назад`
}

/**
 * Returns the correct Russian word form for minutes
 */
function getMinutesWord(count: number): string {
  if (count % 10 === 1 && count % 100 !== 11) {
    return 'минуту'
  }
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) {
    return 'минуты'
  }
  return 'минут'
}

/**
 * Returns the correct Russian word form for hours
 */
function getHoursWord(count: number): string {
  if (count % 10 === 1 && count % 100 !== 11) {
    return 'час'
  }
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) {
    return 'часа'
  }
  return 'часов'
}

/**
 * Returns the correct Russian word form for days
 */
function getDaysWord(count: number): string {
  if (count % 10 === 1 && count % 100 !== 11) {
    return 'день'
  }
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) {
    return 'дня'
  }
  return 'дней'
}

/**
 * OfflineStatus component displays:
 * - Online/Offline badge with icon
 * - Last sync timestamp in relative format
 * - Refresh button with loading state
 */
export function OfflineStatus({ className }: OfflineStatusProps) {
  const { isOnline, lastSync, forceRefresh, isRefreshing } = useOffline()
  
  const handleRefresh = async () => {
    try {
      await forceRefresh()
    } catch (error) {
      // Error is already logged in forceRefresh
      // Could add toast notification here if needed
    }
  }
  
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {/* Online/Offline indicator badge */}
      <Badge 
        variant={isOnline ? 'default' : 'secondary'}
        className={cn(
          'flex items-center gap-1',
          isOnline ? 'bg-green-500 hover:bg-green-600' : 'bg-amber-500 hover:bg-amber-600'
        )}
      >
        {isOnline ? (
          <>
            <Wifi className="w-3 h-3" />
            Онлайн
          </>
        ) : (
          <>
            <WifiOff className="w-3 h-3" />
            Офлайн
          </>
        )}
      </Badge>
      
      {/* Last sync timestamp */}
      <span className="text-sm text-muted-foreground">
        {formatLastSync(lastSync)}
      </span>
      
      {/* Refresh button with loading spinner */}
      <Button
        size="sm"
        variant="ghost"
        onClick={handleRefresh}
        disabled={!isOnline || isRefreshing}
        title={!isOnline ? 'Обновление недоступно в офлайн режиме' : 'Обновить данные'}
      >
        <RefreshCw className={cn('w-4 h-4', isRefreshing && 'animate-spin')} />
      </Button>
    </div>
  )
}
