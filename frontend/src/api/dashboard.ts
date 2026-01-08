import { api } from './client'
import type { DashboardResponse, FileStatus, FTPStatus } from '@/types/dashboard'

export const dashboardApi = {
  getData: async (days = 7, limit = 100, unloadingLimit = 10): Promise<DashboardResponse> => {
    const { data } = await api.get<DashboardResponse>('/dashboard', {
      params: { days, limit, unloading_limit: unloadingLimit },
    })
    return data
  },

  getFileStatus: async (): Promise<FileStatus> => {
    const { data } = await api.get<FileStatus>('/dashboard/status/file')
    return data
  },

  getOPCUAStatus: async (): Promise<FTPStatus> => {
    const { data } = await api.get<FTPStatus>('/dashboard/status/opcua')
    return data
  },

  getOPCUAMatchedUnloadEvents: async (limit = 100): Promise<MatchedUnloadEvent[]> => {
    const { data } = await api.get<MatchedUnloadEvent[]>('/dashboard/opcua-unload-matched', {
      params: { limit },
    })
    return data
  },

  // Debug API
  getDebugRawData: async (limit = 100): Promise<DebugRawData> => {
    const { data } = await api.get<DebugRawData>('/dashboard/debug/raw-data', {
      params: { limit },
    })
    return data
  },

  getDebugMatching: async (limit = 30): Promise<DebugMatchingData> => {
    const { data } = await api.get<DebugMatchingData>('/dashboard/debug/matching', {
      params: { limit },
    })
    return data
  },
}

export interface DebugRawData {
  ftp: {
    source: string
    total_cached: number
    showing: number
    events: Array<{
      date: string
      time: string
      hanger: number
      timestamp: string | null
    }>
  }
  excel: {
    total: number
    showing: number
    products: Array<{
      date: string
      time: string
      number: string
      client: string
      profile: string
      color: string
    }>
  }
  today: string
  note: string
}

export interface DebugMatchingData {
  today: string
  total_ftp_events: number
  total_excel_products: number
  showing: number
  matches: Array<{
    ftp_event: {
      date: string
      time: string
      hanger: number
    }
    candidates_count: number
    candidates: Array<{
      entry_date: string
      entry_time: string
      client: string
      profile: string
      diff_hours: number
      status: string
    }>
    matched: {
      entry_date: string | null
      entry_time: string | null
      client: string | null
      profile: string | null
      diff_hours: number | null
    } | null
  }>
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
}
