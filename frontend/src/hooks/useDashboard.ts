import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import { FILE_STATUS_INTERVAL, DATA_REFRESH_INTERVAL } from '@/config/intervals'

export function useDashboard(days = 7, limit = 100, unloadingLimit = 10) {
  return useQuery({
    queryKey: ['dashboard', days, limit, unloadingLimit],
    queryFn: () => dashboardApi.getData(days, limit, unloadingLimit),
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}

export function useFileStatus() {
  return useQuery({
    queryKey: ['dashboard', 'fileStatus'],
    queryFn: dashboardApi.getFileStatus,
    refetchInterval: FILE_STATUS_INTERVAL,
  })
}

export function useFTPStatus() {
  return useQuery({
    queryKey: ['dashboard', 'ftpStatus'],
    queryFn: dashboardApi.getFTPStatus,
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}

export function useTodayEvents() {
  return useQuery({
    queryKey: ['dashboard', 'events'],
    queryFn: dashboardApi.getTodayEvents,
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}

export function useMatchedUnloadEvents(limit = 100) {
  return useQuery({
    queryKey: ['dashboard', 'unload-matched', limit],
    queryFn: () => dashboardApi.getMatchedUnloadEvents(limit),
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}
