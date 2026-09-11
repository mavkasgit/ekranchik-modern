import { useQuery } from '@tanstack/react-query'
import { lineApi } from '@/api/line'
import { LINE_STATUS_KEY } from '@/lib/queryKeys'
import { DATA_REFRESH_INTERVAL } from '@/config/intervals'

/**
 * Состояние линии: HTTP-запрос — первичная загрузка и fallback,
 * сообщения `line_update` обновляют тот же кэш каждые 2 секунды.
 */
export function useLineStatus() {
  return useQuery({
    queryKey: LINE_STATUS_KEY,
    queryFn: lineApi.getStatus,
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}
