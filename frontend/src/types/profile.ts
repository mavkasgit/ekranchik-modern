export interface Profile {
  id: number;
  name: string;
  quantity_per_hanger: number | null;
  length: number | null;
  notes: string | null;
  photo_thumb: string | null;
  photo_full: string | null;
  /** Версии файлов для `?v=` в URL: меняются при замене файла на диске. */
  photo_thumb_version: string | null;
  photo_full_version: string | null;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProfileSearchResult extends Profile {
  similarity?: number;
  match_priority?: number;
}

export interface ProfileCreate {
  name: string;
  quantity_per_hanger?: number | null;
  length?: number | null;
  notes?: string | null;
}

export interface PhotoUploadResponse {
  success: boolean;
  thumbnail: string;
  full: string;
}
