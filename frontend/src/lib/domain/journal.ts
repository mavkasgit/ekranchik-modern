// Журнал подвесов: правила таблицы журнала (issue #34).
//
// Здесь только то, что можно проверить без сервера: как из состояния
// таблицы собирается запрос, как переключается сортировка и как проход
// читается глазами. Всё остальное — загрузка и отрисовка.

/** Колонки, по которым журнал умеет сортироваться (бэкенд отдаёт тот же набор). */
export type JournalSortField =
  | 'exit_at'
  | 'first_seen_at'
  | 'hanger'
  | 'cycle_id'
  | 'entry_delta_sec'
  | 'code'
  | 'profile'

export type SortDirection = 'asc' | 'desc'

export const JOURNAL_PAGE_SIZE = 50

export interface JournalPass {
  recorded_at?: string | null
  cycle_id?: number | null
  hanger?: number | null
  code: string
  source?: string | null
  entry_bath?: number | null
  first_seen_at?: string | null
  exit_at?: string | null
  total_time_sec?: number | null
  type?: string | null
  reason?: string | null
  path: Array<{ bath: string; in?: string | null; out?: string | null }>
  row_date?: string | null
  row_time?: string | null
  row_number?: string | null
  profile?: string | null
  color?: string | null
  kpz_number?: string | null
  lamels_qty?: number | string | null
  client?: string | null
  material_type?: string | null
  is_defect?: boolean | null
  entry_delta_sec?: number | null
  rows_after_exit?: number
  note?: string | null
}

export interface JournalFile {
  name: string
  size_bytes: number
  modified_at: string
}

export interface JournalPage {
  items: JournalPass[]
  total: number
  limit: number
  offset: number
  directory: string
  files: JournalFile[]
  retention_days: number
}

export interface JournalQuery {
  search: string
  dateFrom: string
  dateTo: string
  sort: JournalSortField
  direction: SortDirection
  limit: number
  offset: number
}

export const EMPTY_JOURNAL_QUERY: JournalQuery = {
  search: '',
  dateFrom: '',
  dateTo: '',
  sort: 'exit_at',
  direction: 'desc',
  limit: JOURNAL_PAGE_SIZE,
  offset: 0,
}

/**
 * Параметры запроса выборки. Пустые поля не уходят на сервер: пустой поиск
 * и пустые даты означают «весь журнал», а не «пустое значение».
 */
export function journalQueryParams(query: JournalQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {
    sort: query.sort,
    direction: query.direction,
    limit: query.limit,
    offset: query.offset,
  }
  if (query.search.trim()) params.search = query.search.trim()
  if (query.dateFrom) params.date_from = query.dateFrom
  if (query.dateTo) params.date_to = query.dateTo
  return params
}

/**
 * Клик по заголовку колонки: та же колонка переворачивает направление,
 * новая — встаёт в начало (от большего к меньшему), потому что журнал
 * читается свежими сверху.
 */
export function toggleSort(
  query: JournalQuery,
  field: JournalSortField,
): JournalQuery {
  const direction: SortDirection =
    query.sort === field ? (query.direction === 'desc' ? 'asc' : 'desc') : 'desc'
  return { ...query, sort: field, direction, offset: 0 }
}

/** Любое изменение выборки возвращает на первую страницу. */
export function withFilter(
  query: JournalQuery,
  patch: Partial<JournalQuery>,
): JournalQuery {
  const offset = 'offset' in patch ? (patch.offset ?? 0) : 0
  return { ...query, ...patch, offset }
}

/** Страницы пагинации по общему числу записей. */
export function pageCount(total: number, limit: number): number {
  if (limit <= 0) return 1
  return Math.max(1, Math.ceil(total / limit))
}

/** Расхождение входа: часы и минуты со знаком, как в разборе прохода. */
export function formatDelta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const sign = seconds < 0 ? '−' : '+'
  const minutes = Math.round(Math.abs(seconds) / 60)
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return hours > 0 ? `${sign}${hours}ч ${rest}м` : `${sign}${rest}м`
}

/** Время выхода прохода: HH:MM:SS из ISO-метки. */
export function passClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  const match = /T(\d{2}:\d{2}:\d{2})/.exec(iso)
  return match ? match[1] : '—'
}

/** Сутки выхода прохода: YYYY-MM-DD из ISO-метки. */
export function passDay(iso: string | null | undefined): string {
  if (!iso) return ''
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(iso)
  return match ? match[1] : ''
}

/** Путь по ваннам строкой: ``3 → 4 → 34``. */
export function formatPath(path: JournalPass['path']): string {
  if (!path || path.length === 0) return '—'
  return path.map(step => step.bath).join(' → ')
}

/** Человекочитаемый размер файла журнала. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

/** Строка книги учёта: ``28.09.2026 18:31`` либо прочерк. */
export function formatBookRow(pass: JournalPass): string {
  if (!pass.row_date || !pass.row_time) return '—'
  return `${pass.row_date} ${pass.row_time.slice(0, 5)}`
}
