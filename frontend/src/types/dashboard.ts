export interface ProfileInfo {
  name: string;
  canonical_name?: string;
  processing: string[];
  has_photo: boolean;
  photo_thumb?: string;
  photo_full?: string;
  updated_at?: string;
}

export interface HangerData {
  number: string;
  date: string;
  time: string;
  client: string;
  profile: string;
  canonical_name?: string;
  profiles_info: ProfileInfo[];
  profile_photo_thumb?: string;
  profile_photo_full?: string;
  color: string;
  lamels_qty: number | string;
  kpz_number: string;
  material_type: string;
  is_defect?: boolean; // True if "брак" in defect column
  // For realtime unload events - entry/exit times
  entry_date?: string | null; // Дата загрузки (из книги); null — строка не подобрана
  entry_time?: string | null; // Время загрузки (из книги); null — строка не подобрана
  exit_date?: string | null; // Дата выгрузки
  exit_time?: string | null; // Время выгрузки
  // Forecast info - current bath and processing time
  current_bath?: number | null; // Bath number 30-33 where hanger currently is
  bath_entry_time?: string | null; // Time when hanger entered current bath (HH:MM:SS)
  bath_processing_time?: number | null; // Expected processing time in seconds for current bath
  time_warning?: string | null;
  /** Причина пометки строки — рисуется как отдельный бейдж, см. WARNING_BADGES */
  time_warning_code?: string | null;
}

export interface DashboardResponse {
  success: boolean;
  products: HangerData[];
  total: number;
  total_all: number;
  days_filter?: number;
  error?: string;
}

/** Роль книги учёта: какую читают по умолчанию и какую — при блокировке основной. */
export type BookRole = "main" | "reserve";

export interface FileStatus {
  is_open: boolean;
  last_modified?: string;
  file_name?: string;
  file_path?: string;
  status_text: string;
  error?: string;
  seconds_since_modified?: number;
  /** Роль читаемой книги; null — режим запасной книги выключен. */
  role?: BookRole | null;
  main_file_path?: string | null;
  reserve_file_path?: string | null;
  /** Когда в основной книге последний раз прибавлялись строки. */
  main_last_growth?: string | null;
  /** Статистика обеих книг: почему читается именно эта. */
  main_rows?: number | null;
  reserve_rows?: number | null;
  reserve_last_growth?: string | null;
  main_present?: boolean | null;
  reserve_present?: boolean | null;
  observed_since?: string | null;
  standby_reason?: string | null;
}

/** Путь, который оператор вводил раньше. */
export interface RecentBookPath {
  path: string;
  used_at?: string | null;
}

/** Текущие книги и история введённых путей. */
export interface ExcelBooksState {
  main?: string | null;
  reserve?: string | null;
  active?: string | null;
  recent: RecentBookPath[];
}

/** Роли книг: какая основная, какая запасная (пустая запасная — режим выключен). */
export interface ExcelBooksResponse {
  success: boolean;
  main: string;
  reserve: string | null;
  /** Книга, которую читают сейчас: после сохранения ролей это основная. */
  active: string;
}

export interface WebSocketMessage {
  type:
    | "data_update"
    | "unload_event"
    | "status"
    | "error"
    | "ping"
    | "pong"
    | "opcua_status"
    | "heartbeat"
    | "line_update";
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface ExcelSelectResponse {
  success: boolean;
  active: string;
}
