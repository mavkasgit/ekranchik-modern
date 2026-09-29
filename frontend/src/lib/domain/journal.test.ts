import { describe, expect, it } from 'vitest'
import {
  EMPTY_JOURNAL_QUERY,
  formatBookRow,
  formatBytes,
  formatDelta,
  formatPath,
  journalQueryParams,
  pageCount,
  passClock,
  passDay,
  toggleSort,
  withFilter,
  type JournalPass,
} from './journal'

const PASS: JournalPass = {
  code: '',
  path: [
    { bath: '3', in: '2026-09-29T17:04:00', out: '2026-09-29T18:10:00' },
    { bath: '4', in: '2026-09-29T18:10:00', out: '2026-09-29T19:30:00' },
    { bath: '34', in: '2026-09-29T19:30:00', out: '2026-09-29T20:16:03' },
  ],
  exit_at: '2026-09-29T20:16:03',
  row_date: '28.09.2026',
  row_time: '18:31:00',
}

describe('journalQueryParams', () => {
  it('пустые фильтры не уходят на сервер', () => {
    expect(journalQueryParams(EMPTY_JOURNAL_QUERY)).toEqual({
      sort: 'exit_at',
      direction: 'desc',
      limit: 50,
      offset: 0,
    })
  })

  it('поиск обрезает пробелы, а пустой пробельный поиск молчит', () => {
    const params = journalQueryParams({ ...EMPTY_JOURNAL_QUERY, search: '  5  ' })
    expect(params.search).toBe('5')
    expect(journalQueryParams({ ...EMPTY_JOURNAL_QUERY, search: '   ' }).search).toBeUndefined()
  })

  it('даты уходят только заполненные', () => {
    const params = journalQueryParams({ ...EMPTY_JOURNAL_QUERY, dateFrom: '2026-09-29' })
    expect(params.date_from).toBe('2026-09-29')
    expect(params.date_to).toBeUndefined()
  })
})

describe('toggleSort', () => {
  it('новая колонка встаёт от большего к меньшему и возвращает на первую страницу', () => {
    const sorted = toggleSort({ ...EMPTY_JOURNAL_QUERY, offset: 100 }, 'hanger')
    expect(sorted).toMatchObject({ sort: 'hanger', direction: 'desc', offset: 0 })
  })

  it('та же колонка переворачивает направление', () => {
    const once = toggleSort(EMPTY_JOURNAL_QUERY, 'entry_delta_sec')
    const twice = toggleSort(once, 'entry_delta_sec')
    expect(once.direction).toBe('desc')
    expect(twice.direction).toBe('asc')
  })
})

describe('withFilter', () => {
  it('смена фильтра возвращает на первую страницу', () => {
    expect(withFilter({ ...EMPTY_JOURNAL_QUERY, offset: 50 }, { search: '7' }).offset).toBe(0)
  })

  it('переход на следующую страницу offset сохраняет', () => {
    expect(withFilter(EMPTY_JOURNAL_QUERY, { offset: 50 }).offset).toBe(50)
  })
})

describe('pageCount', () => {
  it('страницы считаются от общего числа записей', () => {
    expect(pageCount(0, 50)).toBe(1)
    expect(pageCount(50, 50)).toBe(1)
    expect(pageCount(51, 50)).toBe(2)
  })
})

describe('formatDelta', () => {
  it('расхождение читается в часах и минутах со знаком', () => {
    expect(formatDelta(-1800)).toBe('−30м')
    expect(formatDelta(5400)).toBe('+1ч 30м')
  })

  it('без строки книги расхождения нет', () => {
    expect(formatDelta(null)).toBe('—')
    expect(formatDelta(undefined)).toBe('—')
  })
})

describe('passClock / passDay', () => {
  it('время выхода и сутки берутся из метки прохода', () => {
    expect(passClock(PASS.exit_at)).toBe('20:16:03')
    expect(passDay(PASS.exit_at)).toBe('2026-09-29')
  })

  it('у аварийного прохода без метки выхода — прочерк, а не пустая дата', () => {
    expect(passClock(null)).toBe('—')
    expect(passDay(undefined)).toBe('')
  })
})

describe('formatPath / formatBookRow / formatBytes', () => {
  it('путь по ваннам читается слева направо', () => {
    expect(formatPath(PASS.path)).toBe('3 → 4 → 34')
    expect(formatPath([])).toBe('—')
  })

  it('строка книги — дата и время до минуты', () => {
    expect(formatBookRow(PASS)).toBe('28.09.2026 18:31')
    expect(formatBookRow({ code: '', path: [] })).toBe('—')
  })

  it('размер файла журнала читается в единицах диска', () => {
    expect(formatBytes(512)).toBe('512 Б')
    expect(formatBytes(2048)).toBe('2.0 КБ')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 МБ')
  })
})
