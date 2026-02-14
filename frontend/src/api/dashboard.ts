import { api } from './client'
import type { DashboardResponse, FileStatus } from '@/types/dashboard'

export const dashboardApi = {
  getData: async (days = 7, limit = 100, unloadingLimit = 10, loadingOnly = true): Promise<DashboardResponse> => {
    const params: Record<string, any> = {
      days,
      limit,
      unloading_limit: unloadingLimit,
    };
    if (!loadingOnly) {
      params.loading_only = false;
    }
    const { data } = await api.get<DashboardResponse>('/dashboard', { params });
    return data;
  },

  getFileStatus: async (): Promise<FileStatus> => {
    const { data } = await api.get<FileStatus>('/dashboard/status/file')
    return data
  },

  getOPCUAStatus: async (): Promise<FileStatus> => {
    const { data } = await api.get<FileStatus>('/dashboard/status/opcua')
    return data
  },

  getOPCUAMatchedUnloadEvents: async (limit = 100): Promise<MatchedUnloadEvent[]> => {
    const { data } = await api.get<MatchedUnloadEvent[]>('/dashboard/opcua-unload-matched', {
      params: { limit },
    })
    return data
  },
}

export interface MatchedUnloadEvent {
  exit_date: string
  exit_time: string
  hanger: number
  entry_date?: string
  entry_time?: string
  client: string
  profile: string
  profiles_info: Array<{
    name: string
    canonical_name?: string
    has_photo: boolean
    photo_thumb?: string
    photo_full?: string
    processing: string[]
  }>
  color: string
  lamels_qty: number | string
  kpz_number: string
  material_type: string
  // Forecast info - current bath and processing time
  current_bath?: number | null
  bath_entry_time?: string | null
  bath_processing_time?: number | null
}
