// Время: три разных правила под одним прежним именем `formatTime`.
// Явные имена вместо двусмысленного: clock — HH:MM:SS → HH:MM,
// duration — секунды → m:ss, localized — метка времени → локальное время.

export function formatClock(time: string | null | undefined): string {
  if (!time) return '—'
  const parts = time.split(':')
  if (parts.length >= 2) return `${parts[0]}:${parts[1]}`
  return time
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function formatLocalized(
  value: string | number | Date | null | undefined,
  locale = 'ru',
): string {
  if (value === null || value === undefined || value === '') return '—'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString(locale)
}
