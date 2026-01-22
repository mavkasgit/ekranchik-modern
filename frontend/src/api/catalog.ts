import { api } from './client'
import type { Profile, ProfileSearchResult, ProfileCreate, PhotoUploadResponse } from '@/types/profile'

export const catalogApi = {
  search: async (query: string, limit = 50): Promise<ProfileSearchResult[]> => {
    const { data } = await api.get<ProfileSearchResult[]>('/catalog', {
      params: { q: query, limit },
    })
    return data
  },

  getAll: async (limit = 500): Promise<Profile[]> => {
    const { data } = await api.get<Profile[]>('/catalog/all', {
      params: { limit },
    })
    return data
  },

  getByName: async (name: string): Promise<Profile> => {
    const { data } = await api.get<Profile>(`/catalog/${encodeURIComponent(name)}`)
    return data
  },

  createOrUpdate: async (profile: ProfileCreate): Promise<Profile> => {
    const { data } = await api.post<Profile>('/catalog', profile)
    return data
  },

  update: async (id: number, profile: ProfileCreate): Promise<Profile> => {
    const { data } = await api.put<Profile>(`/catalog/${id}`, profile)
    return data
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/catalog/${id}`)
  },

  uploadPhoto: async (name: string, file: File, thumbnail?: File): Promise<PhotoUploadResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    if (thumbnail) {
      formData.append('thumbnail', thumbnail)
    }
    
    const { data } = await api.post<PhotoUploadResponse>(
      `/catalog/${encodeURIComponent(name)}/photo`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return data
  },

  updateThumbnail: async (name: string, thumbnail: File): Promise<{ success: boolean; thumbnail: string }> => {
    const formData = new FormData()
    formData.append('file', thumbnail)
    
    const { data } = await api.put<{ success: boolean; thumbnail: string }>(
      `/catalog/${encodeURIComponent(name)}/thumbnail`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return data
  },

  deletePhoto: async (name: string): Promise<void> => {
    await api.delete(`/catalog/${encodeURIComponent(name)}/photo`)
  },

  deleteFullPhoto: async (name: string): Promise<void> => {
    await api.delete(`/catalog/${encodeURIComponent(name)}/photo/full`)
  },

  deleteThumbnail: async (name: string): Promise<void> => {
    await api.delete(`/catalog/${encodeURIComponent(name)}/photo/thumbnail`)
  },
}
