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
  // Четыре момента прохода: по линии и по книге учёта. В книге ведётся
  // только загрузка в линию, поэтому book_exit_at всегда пуст.
  line_entry_at?: string | null
  line_exit_at?: string | null
  book_entry_at?: string | null
  book_exit_at?: string | null
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

/** Откуда момент: линия (монитор) или книга учёта (запись оператора). */
export type PassTimeSource = 'линия' | 'книга'

/** Один момент прохода: откуда он и вход это или выход. */
export interface PassTime {
  source: PassTimeSource
  role: 'вход' | 'выход'
  at: string
}

/** Сутки и время момента: ``28.09 18:31``. */
function stamp(iso: string): string {
  const day = /^\d{4}-(\d{2})-(\d{2})/.exec(iso)
  const clock = /T(\d{2}:\d{2})/.exec(iso)
  if (!clock) return '—'
  return day ? `${day[2]}.${day[1]} ${clock[1]}` : clock[1]
}

/**
 * Все моменты прохода одним списком — по линии и по книге.
 *
 * Сутки в моменте показываются только когда они разные: ночная смена
 * грузит подвес в 23:55, а монитор видит его в 00:04 уже следующих
 * суток, и без даты эти два момента читаются как полчаса вместо суток.
 * Порядок — как в цеху: сначала книга (заказали и загрузили), потом
 * линия (замерили и выгрузили).
 */
export function passTimes(pass: JournalPass): PassTime[] {
  const moments: Array<[PassTimeSource, 'вход' | 'выход', string | null | undefined]> = [
    ['книга', 'вход', pass.book_entry_at],
    ['линия', 'вход', pass.line_entry_at],
    ['линия', 'выход', pass.line_exit_at],
    ['книга', 'выход', pass.book_exit_at],
  ]
  const present = moments
    .filter(([, , at]) => !!at)
    .map(([source, role, at]) => ({ source, role, at: at as string }))
  if (present.length <= 1) return present.map(({ source, role, at }) => ({ source, role, at: stamp(at) }))

  const days = new Set(present.map(({ at }) => at.slice(0, 10)))
  const showDay = days.size > 1
  return present.map(({ source, role, at }) => ({
    source,
    role,
    at: showDay ? stamp(at) : stamp(at).split(' ').pop() as string,
  }))
}

/**
 * Сколько подвес простоял на линии: от первого замера до ``now``.
 *
 * Больше суток показывается как «>1сут»: это не «долго стоит», а «данные
 * старые» — монитор не видел подвес сутки, и точная цифра врёт.
 */
export function formatInLine(iso: string | null | undefined, now: Date): string {
  if (!iso) return '—'
  const since = new Date(iso).getTime()
  if (Number.isNaN(since)) return '—'
  const minutes = Math.floor((now.getTime() - since) / 60000)
  if (minutes < 0) return '—'
  if (minutes >= 24 * 60) return '>1сут'
  const hours = Math.floor(minutes / 60)
  return hours > 0 ? `${hours}ч ${minutes % 60}м` : `${minutes}м`
}
