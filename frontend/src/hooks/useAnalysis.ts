import { useQuery } from '@tanstack/react-query'
import { analysisApi } from '@/api/analysis'

export function useMissingPhotos(limit = 100) {
  return useQuery({
    queryKey: ['analysis', 'missing', limit],
    queryFn: () => analysisApi.getMissingPhotos(limit),
  })
}

export function useRecentProfiles(limit = 50) {
  return useQuery({
    queryKey: ['analysis', 'recent', limit],
    queryFn: () => analysisApi.getRecentProfiles(limit),
  })
}

export function useRecentMissing(limit = 50) {
  return useQuery({
    queryKey: ['analysis', 'recentMissing', limit],
    queryFn: () => analysisApi.getRecentMissing(limit),
  })
}

export function useDuplicateSearch(query: string, threshold = 0.6, enabled = true) {
  return useQuery({
    queryKey: ['analysis', 'duplicates', query, threshold],
    queryFn: () => analysisApi.searchDuplicates(query, threshold),
    enabled: enabled && query.length > 0,
  })
}
