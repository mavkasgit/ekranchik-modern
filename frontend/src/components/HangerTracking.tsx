import { useEffect, useState } from 'react'
import {
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Search,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useJournal } from '@/hooks/useJournal'
import {
  EMPTY_JOURNAL_QUERY,
  formatBookRow,
  formatBytes,
  formatDelta,
  formatInLine,
  formatPath,
  pageCount,
  passClock,
  passTimes,
  toggleSort,
  withFilter,
  type JournalQuery,
  type JournalSortField,
} from '@/lib/domain/journal'

interface Hanger {
  number: number
  current_bath: number | string | null
  baths_visited: (number | string)[]
  cycle_id: number | null
  line_entry_at: string | null
  entry_bath: number | null
  first_seen_source: string
}

interface OPCUAStatus {
  connected: boolean
  endpoint: string
}

/** Заголовок колонки журнала: сортируется она или нет. */
interface Column {
  title: string
  sort?: JournalSortField
}

const COLUMNS: Column[] = [
  { title: 'Времена подвеса', sort: 'exit_at' },
  { title: 'Подвес', sort: 'hanger' },
  { title: 'Строка книги' },
  { title: 'Профиль', sort: 'profile' },
  { title: 'Расхождение', sort: 'entry_delta_sec' },
  { title: 'Путь по ваннам' },
]

/** Бейдж вердикта сопоставления: пустой код — обычный проход. */
const CODE_LABELS: Record<string, string> = {
  NO_ROW: 'НЕТ СТРОКИ',
  CYCLE_ERROR: 'ОШИБКА ПРОХОДА',
}


export function HangerTracking() {
  const [hangers, setHangers] = useState<Hanger[]>([])
  const [activeHangers, setActiveHangers] = useState<Hanger[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [opcuaStatus, setOpcuaStatus] = useState<OPCUAStatus | null>(null)
  const [query, setQuery] = useState<JournalQuery>(EMPTY_JOURNAL_QUERY)
  const [searchDraft, setSearchDraft] = useState('')
  // Секундный тик: «в линии» должно расти само, как на живой линии, а не
  // обновляться раз в десять секунд вместе с опросом сервера.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const journal = useJournal(query)
  const passes = journal.data?.items ?? []
  const pages = pageCount(journal.data?.total ?? 0, query.limit)

  const fetchOPCUAStatus = async () => {
    try {
      const res = await fetch('/api/opcua/status')
      if (res.ok) {
        const data = await res.json()
        setOpcuaStatus(data)
      }
    } catch (err) {
      console.error('Failed to fetch OPC UA status:', err)
    }
  }

  const fetchHangers = async () => {
    setLoading(true)
    try {
      const [allRes, activeRes] = await Promise.all([
        fetch('/api/opcua/hangers'),
        fetch('/api/opcua/hangers/active')
      ])

      if (!allRes.ok || !activeRes.ok) {
        const errorText = await allRes.text()
        throw new Error(`Failed to fetch hanger data: ${errorText}`)
      }

      const allData = await allRes.json()
      const activeData = await activeRes.json()

      setHangers(allData.hangers || [])
      setActiveHangers(activeData.hangers || [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const scanHangers = async () => {
    try {
      const response = await fetch('/api/opcua/hangers/scan', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to scan hangers')
      await fetchHangers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to scan')
    }
  }

  useEffect(() => {
    fetchOPCUAStatus()
    fetchHangers()

    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchOPCUAStatus()
        fetchHangers()
      }, 10000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh])

  // Поля дат показывают ровно то, что в запросе: подставлять туда сутки
  // последнего прохода значило бы показать границу, которой нет.
  const hasDateFilter = Boolean(query.dateFrom || query.dateTo)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Hanger Tracking</h2>
          <p className="text-sm text-gray-600 mt-1">Track hangers through production line</p>
          {opcuaStatus && (
            <div className="flex items-center gap-2 mt-2">
              {opcuaStatus.connected ? (
                <>
                  <CheckCircle className="w-4 h-4 text-green-600" />
                  <span className="text-xs text-green-600 font-medium">OPC UA Connected</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-red-600" />
                  <span className="text-xs text-red-600 font-medium">OPC UA Disconnected</span>
                </>
              )}
              <span className="text-xs text-gray-500">({opcuaStatus.endpoint})</span>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={scanHangers}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Scan
          </button>
        </div>
      </div>

      {/* Auto-refresh toggle */}
      <div className="mb-4 flex items-center gap-2">
        <input
          type="checkbox"
          id="hangerAutoRefresh"
          checked={autoRefresh}
          onChange={(e) => setAutoRefresh(e.target.checked)}
          className="w-4 h-4 rounded border-gray-300"
        />
        <label htmlFor="hangerAutoRefresh" className="text-sm text-gray-600">
          Auto-refresh every 10 seconds
        </label>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm mb-4">
          {error}
        </div>
      )}

      {/* Statistics */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium">Total Hangers</div>
          <div className="text-2xl font-bold text-blue-900">{hangers.length}</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium">Active Now</div>
          <div className="text-2xl font-bold text-green-900">{activeHangers.length}</div>
        </div>
        <div className="bg-purple-50 rounded-lg p-4">
          <div className="text-sm text-purple-600 font-medium">Avg Baths/Hanger</div>
          <div className="text-2xl font-bold text-purple-900">
            {hangers.length > 0 ? (hangers.reduce((sum, h) => sum + (h.baths_visited?.length || 0), 0) / hangers.length).toFixed(1) : '—'}
          </div>
        </div>
      </div>


      {/* Журнал проходов: файл, а не память монитора (issue #34) */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-900">Журнал подвесов</h3>
          <span className="text-xs text-gray-500">
            {journal.data?.total ?? 0} записей
          </span>
        </div>

        <div className="flex flex-wrap items-end gap-3 mb-3">
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              setQuery(current => withFilter(current, { search: searchDraft }))
            }}
          >
            <div>
              <label htmlFor="journal-search" className="block text-xs text-gray-600 mb-1">
                Поиск: подвес, ID, код, строка
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="journal-search"
                  value={searchDraft}
                  onChange={(e) => setSearchDraft(e.target.value)}
                  placeholder="10104"
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm w-56"
                />
                <button
                  type="submit"
                  className="flex items-center gap-1 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
                  <Search className="w-4 h-4" />
                  Найти
                </button>
              </div>
            </div>
          </form>

          <div>
            <label htmlFor="journal-from" className="block text-xs text-gray-600 mb-1">
              Сутки от
            </label>
            <input
              id="journal-from"
              type="date"
              value={query.dateFrom}
              onChange={(e) => setQuery(current => withFilter(current, { dateFrom: e.target.value }))}
              title={hasDateFilter ? undefined : 'Пусто — весь журнал'}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label htmlFor="journal-to" className="block text-xs text-gray-600 mb-1">
              Сутки по
            </label>
            <input
              id="journal-to"
              type="date"
              value={query.dateTo}
              onChange={(e) => setQuery(current => withFilter(current, { dateTo: e.target.value }))}
              title={hasDateFilter ? undefined : 'Пусто — весь журнал'}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
          {(query.search || query.dateFrom || query.dateTo) && (
            <button
              onClick={() => {
                setSearchDraft('')
                setQuery(current => withFilter(current, { search: '', dateFrom: '', dateTo: '' }))
              }}
              className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
            >
              Сбросить
            </button>
          )}
        </div>

        {passes.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
            <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600 font-medium mb-1">
              {journal.isLoading ? 'Читаем журнал…' : 'Подвесов в журнале нет'}
            </p>
            <p className="text-sm text-gray-500">
              {journal.isError
                ? 'Журнал недоступен'
                : 'Запись идёт сама, как только подвес сходит с линии'}
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    {COLUMNS.map(column => (
                      <th
                        key={column.title}
                        className="text-left py-2 px-3 font-medium text-gray-600"
                      >
                        {column.sort ? (
                          <button
                            onClick={() => setQuery(current => toggleSort(current, column.sort!))}
                            className="inline-flex items-center gap-1 hover:text-gray-900"
                          >
                            {column.title}
                            {query.sort === column.sort ? (
                              query.direction === 'desc' ? (
                                <ArrowDown className="w-3 h-3" />
                              ) : (
                                <ArrowUp className="w-3 h-3" />
                              )
                            ) : (
                              <ArrowUpDown className="w-3 h-3 text-gray-400" />
                            )}
                          </button>
                        ) : (
                          column.title
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {passes.map(pass => (
                    <tr
                      key={`${pass.cycle_id ?? 'err'}-${pass.exit_at ?? ''}-${pass.hanger}`}
                      className="border-b border-gray-100 hover:bg-gray-50"
                    >
                      <td className="py-2 px-3">
                        {passTimes(pass).map((time) => (
                          <div
                            key={`${time.source}-${time.role}`}
                            className="flex items-baseline gap-1.5 leading-tight"
                          >
                            <span className="text-[10px] uppercase text-gray-400 w-9">
                              {time.source}
                            </span>
                            <span className="text-[10px] text-gray-400 w-9">{time.role}</span>
                            <span className="font-mono text-xs text-gray-700 whitespace-nowrap">
                              {time.at}
                            </span>
                          </div>
                        ))}
                      </td>
                      <td className="py-3 px-3 font-mono text-gray-900 whitespace-nowrap">
                        {pass.cycle_id != null && (
                          <span className="mr-2 text-xs font-normal text-gray-400">
                            ID {pass.cycle_id}
                          </span>
                        )}
                        <span className="font-semibold">{pass.hanger ?? '—'}</span>
                      </td>
                      <td className="py-3 px-3 text-gray-700">
                        {pass.code ? (
                          <span className="inline-flex items-center gap-1 px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-medium">
                            <AlertCircle className="w-3 h-3" />
                            {CODE_LABELS[pass.code] ?? pass.code}
                          </span>
                        ) : (
                          <span className="flex items-baseline gap-2">
                            <span className="font-mono text-gray-700">
                              {formatBookRow(pass)}
                            </span>
                            {pass.sheet_row != null && (
                              <span
                                className="font-mono text-xs text-gray-400"
                                title="Номер строки в листе «Подвесы» книги учёта"
                              >
                                лист {pass.sheet_row}
                              </span>
                            )}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-gray-700">
                        {pass.profile ?? '—'}
                        {pass.kpz_number && (
                          <span className="ml-2 text-xs text-gray-500">КПЗ {pass.kpz_number}</span>
                        )}
                      </td>
                      <td className="py-3 px-3 font-mono text-gray-700">
                        {formatDelta(pass.entry_delta_sec)}
                      </td>
                      <td className="py-3 px-3 text-xs text-gray-700 font-mono">
                        {formatPath(pass.path)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between mt-3">
              <p className="text-xs text-gray-500">
                Показано {query.offset + 1}–{query.offset + passes.length} из {journal.data?.total ?? 0}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setQuery(current => withFilter(current, { offset: Math.max(0, current.offset - current.limit) }))}
                  disabled={query.offset === 0}
                  className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Назад
                </button>
                <span className="text-xs text-gray-600">
                  {Math.floor(query.offset / query.limit) + 1} / {pages}
                </span>
                <button
                  onClick={() => setQuery(current => withFilter(current, { offset: current.offset + current.limit }))}
                  disabled={query.offset + query.limit >= (journal.data?.total ?? 0)}
                  className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  Далее
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}

        {journal.data && journal.data.files.length > 0 && (
          <div className="mt-4 pt-3 border-t border-gray-200">
            <p className="text-xs text-gray-600 font-medium mb-1">
              Файлы журнала ({journal.data.retention_days} суток хранения)
            </p>
            <p className="text-xs text-gray-500 font-mono break-all">
              {journal.data.directory}
            </p>
            <ul className="mt-1 space-y-0.5">
              {journal.data.files.slice(0, 5).map(file => (
                <li key={file.name} className="text-xs text-gray-500 font-mono">
                  {file.name} — {formatBytes(file.size_bytes)}
                </li>
              ))}
              {journal.data.files.length > 5 && (
                <li className="text-xs text-gray-400">
                  …и ещё {journal.data.files.length - 5}
                </li>
              )}
            </ul>
          </div>
        )}
      </div>

      {/* Подвесы на линии: плотная таблица, а не карточки.

          Карточка занимала около 110 пикселей на подвес, и на двенадцати
          подвесах блок уезжал за экран — а оператору нужен весь список. Одна
          строка на подвес, колонки выровнены, как в таблице журнала выше. */}
      {activeHangers.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-900">Сейчас на линии</h3>
            <span className="text-xs text-gray-500">{activeHangers.length}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="py-1 px-2 font-medium">Подвес</th>
                  <th className="py-1 px-2 font-medium">Вход на линию</th>
                  <th className="py-1 px-2 font-medium text-right">В линии</th>
                  <th className="py-1 px-2 font-medium">Ванна</th>
                  <th className="py-1 px-2 font-medium">Путь</th>
                  <th className="py-1 px-2 font-medium text-right">Ванн</th>
                </tr>
              </thead>
              <tbody>
                {activeHangers.filter(Boolean).map(hanger => (
                  <tr
                    key={hanger.number}
                    className="border-b border-gray-100 odd:bg-green-50/60 hover:bg-green-50"
                  >
                    <td className="py-1 px-2 font-mono text-gray-900 whitespace-nowrap">
                      {hanger.cycle_id != null && (
                        <span className="mr-1 text-[10px] font-normal text-gray-400">
                          ID {hanger.cycle_id}
                        </span>
                      )}
                      <span className="font-semibold">
                        #{String(hanger.number).padStart(3, '0')}
                      </span>
                    </td>
                    <td className="py-1 px-2 font-mono text-gray-700 whitespace-nowrap">
                      {passClock(hanger.line_entry_at)}
                      {hanger.entry_bath != null && (
                        <span className="ml-1 text-[10px] text-gray-400">
                          ванна {hanger.entry_bath}
                        </span>
                      )}
                    </td>
                    <td className="py-1 px-2 text-right font-mono text-gray-700 whitespace-nowrap">
                      {formatInLine(hanger.line_entry_at, now, hanger.first_seen_source)}
                    </td>
                    <td className="py-1 px-2 font-mono text-gray-700">
                      {hanger.current_bath ?? '—'}
                    </td>
                    <td className="py-1 px-2 font-mono text-gray-500 truncate max-w-[280px]">
                      {hanger.baths_visited?.length
                        ? hanger.baths_visited.map(b => `Ванна[${b}]`).join(' → ')
                        : '—'}
                    </td>
                    <td className="py-1 px-2 text-right font-mono text-gray-500">
                      {hanger.baths_visited?.length ?? 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
