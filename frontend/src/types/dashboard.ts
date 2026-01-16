export interface ProfileInfo {
  name: string
  canonical_name?: string
  processing: string[]
  has_photo: boolean
  photo_thumb?: string
  photo_full?: string
  updated_at?: string
}

export interface HangerData {
  number: string
  date: string
  time: string
  client: string
  profile: string
  canonical_name?: string
  profiles_info: ProfileInfo[]
  profile_photo_thumb?: string
  profile_photo_full?: string
  color: string
  lamels_qty: number | string
  kpz_number: string
  material_type: string
  is_defect?: boolean   // True if "брак" in defect column
  // For realtime unload events - entry/exit times
  entry_date?: string   // Date when loaded (from Excel)
  entry_time?: string   // Time when loaded (from Excel)
  exit_date?: string    // Date when unloaded
  exit_time?: string    // Time when unloaded
}

export interface DashboardResponse {
  success: boolean
  products: HangerData[]
  unloading_products: HangerData[]
  total: number
  total_all: number
  days_filter?: number
  dual_mode: boolean
  error?: string
}

export interface FileStatus {
  is_open: boolean
  last_modified?: string
  file_name?: string
  status_text: string
  error?: string
}

export interface WebSocketMessage {
  type: 'data_update' | 'unload_event' | 'status' | 'error' | 'ping' | 'pong' | 'opcua_status' | 'heartbeat' | 'line_update'
  payload: Record<string, unknown>
  timestamp: string
}
