import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import { FILE_STATUS_INTERVAL, DATA_REFRESH_INTERVAL } from '@/config/intervals'
import { DASHBOARD_KEY, FILE_STATUS_KEY, MATCHED_UNLOAD_KEY, OPCUA_STATUS_KEY } from '@/lib/queryKeys'

export function useDashboard(days = 7, limit = 100, loadingOnly = true) {
  return useQuery({
    queryKey: [...DASHBOARD_KEY, days, limit, loadingOnly],
    queryFn: () => dashboardApi.getData(days, limit, 10, loadingOnly),
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}

export function useFileStatus() {
  return useQuery({
    queryKey: FILE_STATUS_KEY,
    queryFn: dashboardApi.getFileStatus,
    refetchInterval: FILE_STATUS_INTERVAL,
  })
}

export function useOPCUAStatus() {
  return useQuery({
    queryKey: OPCUA_STATUS_KEY,
    queryFn: dashboardApi.getOPCUAStatus,
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}

export function useOPCUAMatchedUnloadEvents(limit = 100) {
  return useQuery({
    queryKey: [...MATCHED_UNLOAD_KEY, limit],
    queryFn: () => dashboardApi.getOPCUAMatchedUnloadEvents(limit),
    refetchInterval: DATA_REFRESH_INTERVAL,
  })
}
