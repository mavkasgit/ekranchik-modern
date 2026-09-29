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
  entry_date?: string | null   // Дата загрузки (из книги); null — строка не подобрана
  entry_time?: string | null   // Время загрузки (из книги); null — строка не подобрана
  exit_date?: string | null    // Дата выгрузки
  exit_time?: string | null    // Время выгрузки
  // Forecast info - current bath and processing time
  current_bath?: number | null  // Bath number 30-33 where hanger currently is
  bath_entry_time?: string | null  // Time when hanger entered current bath (HH:MM:SS)
  bath_processing_time?: number | null  // Expected processing time in seconds for current bath
  time_warning?: string | null
  /** Причина пометки строки — рисуется как отдельный бейдж, см. WARNING_BADGES */
  time_warning_code?: string | null
}

export interface DashboardResponse {
  success: boolean
  products: HangerData[]
  total: number
  total_all: number
  days_filter?: number
  error?: string
}

export interface FileStatus {
  is_open: boolean
  last_modified?: string
  file_name?: string
  file_path?: string
  status_text: string
  error?: string
  seconds_since_modified?: number
}

export interface WebSocketMessage {
  type: 'data_update' | 'unload_event' | 'status' | 'error' | 'ping' | 'pong' | 'opcua_status' | 'heartbeat' | 'line_update'
  payload: Record<string, unknown>
  timestamp: string
}

export interface ExcelSelectResponse {
  success: boolean
  active: string
}


