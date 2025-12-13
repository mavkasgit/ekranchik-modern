import { api } from './client'
import type { Profile, ProfileSearchResult } from '@/types/profile'

export interface RecentProfile {
  profile: string
  date: string
  number: string
  has_photo: boolean
  row_number?: number
  count?: number
}

export const analysisApi = {
  getMissingPhotos: async (limit = 100): Promise<Profile[]> => {
    const { data } = await api.get<Profile[]>('/profiles/missing', {
      params: { limit },
    })
    return data
  },

  getRecentProfiles: async (limit = 50): Promise<RecentProfile[]> => {
    const { data } = await api.get<RecentProfile[]>('/profiles/recent', {
      params: { limit },
    })
    return data
  },

  getRecentMissing: async (limit = 50): Promise<RecentProfile[]> => {
    const { data } = await api.get<RecentProfile[]>('/profiles/recent-missing', {
      params: { limit },
    })
    return data
  },

  searchDuplicates: async (
    query: string, 
    threshold = 0.6, 
    limit = 20
  ): Promise<ProfileSearchResult[]> => {
    const { data } = await api.get<ProfileSearchResult[]>('/profiles/search-duplicates', {
      params: { q: query, threshold, limit },
    })
    return data
  },
}
