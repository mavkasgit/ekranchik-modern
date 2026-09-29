import { api } from './client'
import {
  journalQueryParams,
  type JournalPage,
  type JournalQuery,
} from '@/lib/domain/journal'

/** Страница проходов из файла журнала подвесов. */
export const journalApi = {
  getPasses: async (query: JournalQuery): Promise<JournalPage> => {
    const { data } = await api.get<JournalPage>('/journal/passes', {
      params: journalQueryParams(query),
    })
    return data
  },
}
