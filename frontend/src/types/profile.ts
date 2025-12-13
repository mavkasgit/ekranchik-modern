export interface Profile {
  id: number
  name: string
  quantity_per_hanger: number | null
  length: number | null
  notes: string | null
  photo_thumb: string | null
  photo_full: string | null
  usage_count: number
  created_at: string
  updated_at: string
}

export interface ProfileSearchResult extends Profile {
  similarity?: number
  match_priority?: number
}

export interface ProfileCreate {
  name: string
  quantity_per_hanger?: number | null
  length?: number | null
  notes?: string | null
}

export interface PhotoUploadResponse {
  success: boolean
  thumbnail: string
  full: string
}
