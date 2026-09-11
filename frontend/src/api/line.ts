import { api } from './client'
import type { CompletedCycle, LineStatus } from '@/types/line'

export const lineApi = {
  getStatus: async (): Promise<LineStatus> => {
    // t= — чтобы промежуточный кэш не отдавал вчерашние счётчики ванн
    const { data } = await api.get<LineStatus>('/opcua/line/status', { params: { t: Date.now() } })
    return data
  },

  getCycles: async (limit = 10): Promise<CompletedCycle[]> => {
    const { data } = await api.get<{ cycles: CompletedCycle[] }>('/opcua/line/cycles', {
      params: { limit },
    })
    return data.cycles ?? []
  },
}
