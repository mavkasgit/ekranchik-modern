import { describe, expect, it } from 'vitest'
import {
  EMPTY_JOURNAL_QUERY,
  formatBookRow,
  formatBytes,
  formatDelta,
  formatInLine,
  formatPath,
  journalQueryParams,
  pageCount,
  passClock,
  passDay,
  passTimes,
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

describe('passTimes', () => {
  it('вход и выход показываются вместе — по линии и по книге', () => {
    const pass: JournalPass = {
      code: '',
      path: [],
      line_entry_at: '2026-09-29T17:04:00',
      line_exit_at: '2026-09-29T20:16:03',
      book_entry_at: '2026-09-28T18:31:00',
      book_exit_at: null,
    }
    // Порядок хронологический: сначала книга (загрузили), потом линия
    // (замерили, потом выгрузили) — проход читается как рассказ.
    expect(passTimes(pass)).toEqual([
      { source: 'книга', role: 'вход', at: '28.09 18:31' },
      { source: 'линия', role: 'вход', at: '29.09 17:04' },
      { source: 'линия', role: 'выход', at: '29.09 20:16' },
    ])
  })

  it('выхода по книге нет и в списке не значится пустым временем', () => {
    // Книга ведёт только загрузку в линию. Пустая строка «выход» в таблице
    // читалась бы как «оператор не вписал», а на самом деле колонки нет.
    const times = passTimes({ code: '', path: [], book_entry_at: '2026-09-28T18:31:00' })
    expect(times.map(t => t.role)).toEqual(['вход'])
    expect(times[0].source).toBe('книга')
  })

  it('сутки показываются только когда момент переходит в другой день', () => {
    // Ночная смена: загрузили 28-го в 23:55, монитор увидел 29-го в 00:04.
    // Если разные сутки не показать, «00:04» читается как замер в 00:04
    // этого же дня — то есть на шесть часов позже загрузки.
    const times = passTimes({
      code: '',
      path: [],
      book_entry_at: '2026-09-28T23:55:00',
      line_entry_at: '2026-09-29T00:04:00',
    })
    expect(times.map(t => t.at)).toEqual(['28.09 23:55', '29.09 00:04'])
  })

  it('на одних сутках моменты читаются часами, порядок — по источнику', () => {
    // Порядок не хронологический, а по источнику: сначала книга, потом
    // линия. Иначе вход по книге (18:31) встал бы между замером (17:04)
    // и выгрузкой (20:16), и «книга» рассыпалась бы по строке.
    const times = passTimes({
      code: '',
      path: [],
      book_entry_at: '2026-09-29T18:31:00',
      line_entry_at: '2026-09-29T17:04:00',
      line_exit_at: '2026-09-29T20:16:00',
    })
    expect(times.map(t => t.at)).toEqual(['18:31', '17:04', '20:16'])
  })

  it('запись без новых полей читается по прежним', () => {
    // Файл журнала живёт 30 суток, а новые поля появились не вчера:
    // записи, сделанные старой версией, лежат в нём рядом с новыми. Без
    // запасного чтения колонка времён у них молчала бы пустотой.
    const times = passTimes({
      code: '',
      path: [],
      first_seen_at: '2026-09-29T17:04:00',
      exit_at: '2026-09-29T20:16:00',
      row_date: '29.09.2026',
      row_time: '18:31:00',
    })
    expect(times.map(t => t.at)).toEqual(['18:31', '17:04', '20:16'])
    expect(times.map(t => t.role)).toEqual(['вход', 'вход', 'выход'])
  })
})

describe('formatInLine', () => {
  it('сколько подвес в линии считается от первого замера', () => {
    const now = new Date('2026-09-29T20:16:03')
    expect(formatInLine('2026-09-29T17:04:00', now)).toBe('3ч 12м')
    expect(formatInLine('2026-09-29T20:10:00', now)).toBe('6м')
  })

  it('без времени замера на линии простоя нет — прочерк', () => {
    expect(formatInLine(null, new Date())).toBe('—')
  })

  it('подвес не может стоять на линии дольше суток', () => {
    // Монитор мог не видеть подвеса сутки (разрыв связи, авария). Показывать
    // «26ч» оператору незачем: это не «много стоит», это «данные старые».
    const now = new Date('2026-09-30T20:00:00')
    expect(formatInLine('2026-09-29T18:00:00', now)).toBe('>1сут')
  })
})
