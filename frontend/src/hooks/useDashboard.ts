import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'

export function useDashboard(days = 7, limit = 100) {
  return useQuery({
    queryKey: ['dashboard', days, limit],
    queryFn: () => dashboardApi.getData(days, limit),
    refetchInterval: 30000, // Refetch every 30s
  })
}

export function useFileStatus() {
  return useQuery({
    queryKey: ['dashboard', 'fileStatus'],
    queryFn: dashboardApi.getFileStatus,
    refetchInterval: 3000, // Check every 3s for file changes
  })
}

export function useFTPStatus() {
  return useQuery({
    queryKey: ['dashboard', 'ftpStatus'],
    queryFn: dashboardApi.getFTPStatus,
    refetchInterval: 30000,
  })
}

export function useTodayEvents() {
  return useQuery({
    queryKey: ['dashboard', 'events'],
    queryFn: dashboardApi.getTodayEvents,
    refetchInterval: 60000,
  })
}
