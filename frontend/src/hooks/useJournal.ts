import { useQuery } from '@tanstack/react-query'
import { journalApi } from '@/api/journal'
import { JOURNAL_KEY } from '@/lib/queryKeys'
import { DATA_REFRESH_INTERVAL } from '@/config/intervals'
import type { JournalQuery } from '@/lib/domain/journal'

/**
 * Страница проходов из файла журнала подвесов.
 *
 * Опрос идёт наравне с остальными таблицами: журнал пополняется фоновой
 * задачей сервера, поэтому открытая вкладка должна подхватывать новые
 * проходы без перезагрузки страницы.
 */
export function useJournal(query: JournalQuery) {
  return useQuery({
    queryKey: [...JOURNAL_KEY, query],
    queryFn: () => journalApi.getPasses(query),
    refetchInterval: DATA_REFRESH_INTERVAL,
    // Пока вкладка не видна, опрос не идёт: журнал лежит на диске и переживает
    // перезапуск, а оператор вернётся к тем же фильтрам.
    refetchIntervalInBackground: false,
    placeholderData: previous => previous,
  })
}
