import { useState, useEffect } from 'react'

/**
 * Hook for countdown timer
 * @param bathEntryTime - Time when hanger entered bath (HH:MM:SS)
 * @param processingTime - Processing time in seconds
 * @returns Remaining time in MM:SS format, or null if invalid
 */
export function useCountdown(
  bathEntryTime: string | null | undefined,
  processingTime: number | null | undefined
): string | null {
  const [remaining, setRemaining] = useState<string | null>(null)

  useEffect(() => {
    if (!bathEntryTime || !processingTime || processingTime <= 0) {
      setRemaining(null)
      return
    }

    const updateCountdown = () => {
      try {
        // Parse entry time (HH:MM:SS)
        const timeParts = bathEntryTime.split(':')
        if (timeParts.length < 2) {
          setRemaining(null)
          return
        }

        const entryHour = parseInt(timeParts[0], 10)
        const entryMinute = parseInt(timeParts[1], 10)
        const entrySecond = parseInt(timeParts[2] || '0', 10)

        // Calculate entry time in seconds since midnight
        const entryTotalSeconds = entryHour * 3600 + entryMinute * 60 + entrySecond

        // Get current time in seconds since midnight
        const now = new Date()
        const currentTotalSeconds = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()

        // Calculate elapsed time
        let elapsedSeconds = currentTotalSeconds - entryTotalSeconds

        // Handle day boundary (if current time is less than entry time, add 24 hours)
        if (elapsedSeconds < 0) {
          elapsedSeconds += 24 * 3600
        }

        // Calculate remaining time
        const remainingSeconds = Math.max(0, processingTime - elapsedSeconds)

        // Format as MM:SS
        const minutes = Math.floor(remainingSeconds / 60)
        const seconds = remainingSeconds % 60
        const formatted = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`

        setRemaining(formatted)
      } catch (e) {
        setRemaining(null)
      }
    }

    // Update immediately
    updateCountdown()

    // Update every second
    const interval = setInterval(updateCountdown, 1000)

    return () => clearInterval(interval)
  }, [bathEntryTime, processingTime])

  return remaining
}
