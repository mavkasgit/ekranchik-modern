import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import { FILE_STATUS_INTERVAL, DATA_REFRESH_INTERVAL } from '@/config/intervals'

export function useDashboard(days = 7, limit = 100, unloadingLimit = 10, loadingOnly = true) {
  return useQuery({
    queryKey: ['dashboard', days, limit, unloadingLimit, loadingOnly],
    queryFn: () => dashboardApi.getData(days, limit, unloadingLimit, loadingOnly),
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

export function useOPCUAStatus() {
  return useQuery({
    queryKey: ['dashboard', 'opcuaStatus'],
    queryFn: dashboardApi.getOPCUAStatus,
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}

export function useOPCUAMatchedUnloadEvents(limit = 100) {
  return useQuery({
    queryKey: ['dashboard', 'opcua-unload-matched', limit],
    queryFn: () => dashboardApi.getOPCUAMatchedUnloadEvents(limit),
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}
