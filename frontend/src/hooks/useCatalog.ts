import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { catalogApi } from '@/api/catalog'
import type { ProfileCreate } from '@/types/profile'

export function useCatalogSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: ['catalog', 'search', query],
    queryFn: () => catalogApi.search(query),
    enabled: enabled && query.length > 0,
    staleTime: 30000,
  })
}

export function useCatalogAll() {
  return useQuery({
    queryKey: ['catalog', 'all'],
    queryFn: () => catalogApi.getAll(),
  })
}

export function useProfile(name: string) {
  return useQuery({
    queryKey: ['catalog', 'profile', name],
    queryFn: () => catalogApi.getByName(name),
    enabled: !!name,
  })
}

export function useCreateOrUpdateProfile() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: (profile: ProfileCreate) => catalogApi.createOrUpdate(profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ProfileCreate }) => 
      catalogApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useDeleteProfile() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: (id: number) => catalogApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useUploadPhoto() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: ({ name, file, thumbnail }: { name: string; file: File; thumbnail?: File }) => 
      catalogApi.uploadPhoto(name, file, thumbnail),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useUpdateThumbnail() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: ({ name, thumbnail }: { name: string; thumbnail: File }) => 
      catalogApi.updateThumbnail(name, thumbnail),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useDeletePhoto() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: (name: string) => catalogApi.deletePhoto(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}
