import { api } from './client'
import type { DashboardResponse, FileStatus, FTPStatus, UnloadEvent } from '@/types/dashboard'

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

  getFTPStatus: async (): Promise<FTPStatus> => {
    const { data } = await api.get<FTPStatus>('/dashboard/status/ftp')
    return data
  },

  getTodayEvents: async (): Promise<UnloadEvent[]> => {
    const { data } = await api.get<UnloadEvent[]>('/dashboard/events')
    return data
  },

  getMatchedUnloadEvents: async (limit = 100): Promise<MatchedUnloadEvent[]> => {
    const { data } = await api.get<MatchedUnloadEvent[]>('/dashboard/unload-matched', {
      params: { limit },
    })
    return data
  },

  // Simulation API
  startSimulation: async (): Promise<SimulationStatus> => {
    const { data } = await api.post<SimulationStatus>('/dashboard/simulation/start')
    return data
  },

  stopSimulation: async (): Promise<SimulationStatus> => {
    const { data } = await api.post<SimulationStatus>('/dashboard/simulation/stop')
    return data
  },

  getSimulationStatus: async (): Promise<SimulationStatus> => {
    const { data } = await api.get<SimulationStatus>('/dashboard/simulation/status')
    return data
  },
}

export interface SimulationStatus {
  active: boolean
  file_path?: string
  current_event: number
  total_events: number
  progress_percent: number
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
