import { describe, expect, it } from 'vitest'
import {
  DWELL_SECONDS,
  LAUNCH_WINDOW,
  RUN_BATHS,
  UNLOAD_LIMIT,
  advanceRun,
  emptyRun,
  startRun,
  type RunState,
} from './testRun'
import type { HangerData } from '@/types/dashboard'

const PALETTE = [
  'серебро', 'черный', 'золото', 'шампань', 'титан',
  'бронза', 'медь', 'растрав', 'Rose Gold', 'Rose Bronze',
]

const POOL: HangerData[] = PALETTE.map((color, index) => ({
  number: `cat-${index}`,
  date: '28.09.2026',
  time: '12:00',
  client: 'Тест Каталога',
  profile: `1010${index}`,
  profiles_info: [],
  color,
  lamels_qty: 10,
  kpz_number: '—',
  material_type: 'Тест',
}))

/** Детерминированный генератор: перемешивание проверяется, а не отдаётся на волю Math.random. */
function seededRandom(seed: number): () => number {
  let value = seed
  return () => {
    value = (value * 1103515245 + 12345) % 2147483648
    return value / 2147483648
  }
}

function tick(state: RunState, times: number, random = seededRandom(1)): RunState {
  let current = state
  for (let i = 0; i < times; i += 1) {
    current = advanceRun(current, `19:41:0${i % 10}`, random)
  }
  return current
}

describe('startRun', () => {
  it('нумерует подвесы по порядку входа: первым уходит №1, а не последний', () => {
    const state = startRun(POOL, seededRandom(7))

    expect(state.inBaths).toHaveLength(RUN_BATHS.length)
    expect(state.inBaths.map(hanger => hanger.remainingTime)).toEqual([20, 15, 10, 5])
    // Подвес, которому осталось 5 секунд, вошёл раньше всех — его номер первый.
    expect(state.inBaths[RUN_BATHS.length - 1].number).toBe(1)
    expect(state.inBaths[0].number).toBe(RUN_BATHS.length)
    expect(state.inBaths.every(hanger => PALETTE.includes(hanger.row.color))).toBe(true)
  })

  it('кладёт в боковую очередь запущенные подвесы, новые сверху', () => {
    const state = startRun(POOL, seededRandom(7))

    expect(state.launched.map(hanger => hanger.number)).toEqual(['4', '3', '2', '1'])
    expect(state.unloaded).toEqual([])
  })

  it('выгружает подвесы по номерам: первым уходит №1, дальше по порядку', () => {
    const state = tick(startRun(POOL, seededRandom(7)), 30)

    expect(state.unloaded.map(hanger => Number(hanger.number)))
      .toEqual([6, 5, 4, 3, 2, 1])
  })

  it('берёт столько ванн, сколько есть строк', () => {
    const state = startRun(POOL.slice(0, 2), seededRandom(7))

    expect(state.inBaths).toHaveLength(2)
    expect(state.launched).toHaveLength(2)
  })

  it('пустой витрине нечего запускать', () => {
    expect(startRun([], seededRandom(7))).toEqual(emptyRun())
  })
})

describe('advanceRun', () => {
  it('подвес, вошедший в ванну, лежит в ней все 20 секунд', () => {
    const start = startRun(POOL, seededRandom(7))
    const entry = start.inBaths[0]
    const held = tick(start, DWELL_SECONDS - 1, seededRandom(7))
    const gone = advanceRun(held, '19:41:20', seededRandom(7))

    expect(held.unloaded.every(row => row.number !== String(entry.number))).toBe(true)
    expect(held.inBaths).toHaveLength(RUN_BATHS.length)
    expect(gone.unloaded[0].number).toBe(String(entry.number))
  })

  it('каждые 5 секунд в выгрузку уходит ровно один подвес', () => {
    const state = tick(startRun(POOL, seededRandom(7)), 15)

    expect(state.unloaded).toHaveLength(3)
    expect(state.inBaths).toHaveLength(RUN_BATHS.length)
  })

  it('ушедший подвес сохраняет свой номер, а в его ванну входит новый с откатом 20 секунд', () => {
    const start = startRun(POOL, seededRandom(7))
    const state = tick(start, 5, seededRandom(7))
    const bath = state.inBaths[3]

    expect(state.unloaded).toHaveLength(1)
    expect(state.unloaded[0].number).toBe(String(start.inBaths[3].number))
    expect(state.unloaded[0].color).toBe(start.inBaths[3].row.color)
    expect(bath.number).not.toBe(start.inBaths[3].number)
    expect(bath.remainingTime).toBe(DWELL_SECONDS)
  })

  it('остальные ванны на своём месте: подвес не ходит между ваннами', () => {
    const start = startRun(POOL, seededRandom(7))
    const state = tick(start, 5, seededRandom(7))

    expect(state.inBaths.slice(0, 3).map(hanger => hanger.number))
      .toEqual(start.inBaths.slice(0, 3).map(hanger => hanger.number))
  })

  it('время выгрузки — момент ухода, время загрузки — из витрины', () => {
    const state = advanceRun(tick(startRun(POOL, seededRandom(7)), 4, seededRandom(7)), '19:41:05', seededRandom(7))

    expect(state.unloaded[0].entry_time).toBe('12:00')
    expect(state.unloaded[0].exit_time).toBe('19:41:05')
    expect(state.unloaded[0].time).toBe('19:41:05')
    expect(state.unloaded[0].entry_date).toBe('28.09.2026')
    expect(state.unloaded[0].exit_date).toBe('28.09.2026')

  })

  it('в выгрузке новые сверху, десятая строка уходит вниз', () => {
    const state = tick(startRun(POOL, seededRandom(7)), (UNLOAD_LIMIT + 5) * 5)
    const numbers = state.unloaded.map(hanger => Number(hanger.number))

    expect(state.unloaded).toHaveLength(UNLOAD_LIMIT)
    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
    expect(numbers).toContain(15)
    expect(numbers).not.toContain(4)
  })

  it('в боковой очереди последние запущенные подвесы, новые сверху', () => {
    const state = tick(startRun(POOL, seededRandom(7)), (LAUNCH_WINDOW + 2) * 5)
    const numbers = state.launched.map(hanger => Number(hanger.number))

    expect(state.launched).toHaveLength(LAUNCH_WINDOW)
    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
  })

  it('после круга порядок запуска меняется, но ни одна строка не теряется и не повторяется', () => {
    const start = startRun(POOL, seededRandom(7))
    const state = tick(start, POOL.length * 5, seededRandom(7))

    expect(state.pool.map(item => item.color)).not.toEqual(start.pool.map(item => item.color))
    expect(state.pool.map(item => item.color).sort()).toEqual([...PALETTE].sort())
    expect(state.inBaths).toHaveLength(RUN_BATHS.length)
  })

  it('нумерация подвесов сквозная: круг не начинает счёт заново', () => {
    const state = tick(startRun(POOL, seededRandom(7)), POOL.length * 5 + 5, seededRandom(7))

    expect(Number(state.unloaded[0].number)).toBeGreaterThan(POOL.length)
  })

  it('без строк прогон не падает', () => {
    expect(advanceRun(emptyRun(), '19:41:05', seededRandom(7))).toEqual(emptyRun())
  })
})
