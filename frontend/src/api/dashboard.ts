import { api } from './client'
import type { DashboardResponse, FileStatus, FTPStatus, UnloadEvent } from '@/types/dashboard'

export const dashboardApi = {
  getData: async (days = 7, limit = 100): Promise<DashboardResponse> => {
    const { data } = await api.get<DashboardResponse>('/dashboard', {
      params: { days, limit },
    })
    return data
  },

  getFileStatus: async (): Promise<FileStatus> => {
    const { data } = await api.get<FileStatus>('/dashboard/status/file')
    return data
  },

  getFTPStatus: async (): Promise<FTPStatus> => {
    const { data } = await api.get<FTPStatus>('/dashboard/status/ftp')
    return data
  },

  getTodayEvents: async (): Promise<UnloadEvent[]> => {
    const { data } = await api.get<UnloadEvent[]>('/dashboard/events')
    return data
  },
}
