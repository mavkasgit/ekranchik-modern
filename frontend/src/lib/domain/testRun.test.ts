import { describe, expect, it } from 'vitest'
import {
  EXIT_INTERVAL_SECONDS,
  FORECAST_BATHS,
  LINE_SECONDS,
  advanceRun,
  emptyRun,
  startRun,
  waitingRows,
  type RunState,
} from './testRun'
import { formatLocalized } from './time'
import type { HangerData } from '@/types/dashboard'

const PALETTE = [
  'серебро', 'черный', 'золото', 'шампань', 'титан',
  'бронза', 'медь', 'растрав', 'Rose Gold', 'Rose Bronze',
]

/** Строка каталога в том виде, в каком её кладёт в очередь загрузки. */
function catalogRow(index: number): HangerData {
  return {
    number: `cat-${index}`,
    date: '29.09.26',
    time: '12:00:00',
    client: 'Тест Каталога',
    profile: `1010${index}`,
    profiles_info: [],
    color: PALETTE[index % PALETTE.length],
    lamels_qty: 10,
    kpz_number: '—',
    material_type: 'Тест',
  }
}

const POOL: HangerData[] = Array.from({ length: 30 }, (_, index) => catalogRow(index))

const NOW = new Date('2026-09-28T19:41:05.000')

/** Момент на N секунд позже старта прогона. */
function at(seconds: number): Date {
  return new Date(NOW.getTime() + seconds * 1000)
}

/** Детерминированный генератор: перемешивание проверяется, а не отдаётся на волю Math.random. */
function seededRandom(seed: number): () => number {
  let state = seed
  return () => {
    state = (state * 1103515245 + 12345) % 2147483648
    return state / 2147483648
  }
}

/** Секундные тики прогона: один тик — одна секунда, как у реального остатка в ванне. */
function tick(state: RunState, seconds: number, unloadLimit = 15, random = seededRandom(7)): RunState {
  let current = state
  for (let second = 1; second <= seconds; second += 1) {
    current = advanceRun(current, at(second), unloadLimit, random)
  }
  return current
}

function started(random = seededRandom(7)): RunState {
  return startRun(POOL, NOW, random)
}

/** Остатки на карточках ванн 30…33 в порядке ванн. */
function cardRemainders(state: RunState): number[] {
  return FORECAST_BATHS.map((_, bathIndex) => state.line[bathIndex]?.remainingTime ?? -1)
}

/** Номера подвесов на карточках ванн 30…33 и в ванне схода. */
function lineNumbers(state: RunState): number[] {
  return [...state.line.map(hanger => hanger.number), state.atExit?.number ?? 0]
}

/** Полный круг: каждый подвес из круга успел встать на линию. */
const LAP_SECONDS = EXIT_INTERVAL_SECONDS * POOL.length

describe('старт прогона', () => {
  it('ванна заполнена целиком: по подвесу на каждую карточку', () => {
    const state = started()

    expect(state.line).toHaveLength(FORECAST_BATHS.length)
    expect(state.line.every(hanger => hanger !== undefined)).toBe(true)
  })

  it('остатки на карточках идут лесенкой 20, 15, 10 и 5 секунд', () => {
    expect(cardRemainders(started())).toEqual([20, 15, 10, 5])
  })

  it('подвес, стоящий в ванне схода, сразу есть в выгрузке', () => {
    const state = started()

    expect(state.unloaded).toHaveLength(1)
    expect(Number(state.unloaded[0].number)).toBe(state.atExit!.number)
  })

  it('номера вдоль маршрута растут: от ванны схода к первой ванне', () => {
    expect(lineNumbers(started())).toEqual([5, 4, 3, 2, 1])
  })

  it('цвет строки витрины — из справочника, а не «Не указан»', () => {
    const state = started()

    expect(state.line.every(hanger => PALETTE.includes(hanger.row.color))).toBe(true)
    expect(PALETTE.includes(state.atExit!.row.color)).toBe(true)
  })

  it('очередь загрузки сохраняет время витрины, на линии время прогона', () => {
    const state = started()

    expect(waitingRows(state, 6).every(row => row.time === '12:00:00')).toBe(true)
    expect(state.line.every(hanger => hanger.row.time === formatLocalized(NOW, 'ru-RU'))).toBe(true)
  })

  it('круг короче ванны: линия всё равно заполнена', () => {
    const state = startRun(POOL.slice(0, 1), NOW, seededRandom(7))

    expect(new Set(lineNumbers(state)).size).toBe(FORECAST_BATHS.length + 1)
    expect(state.unloaded).toHaveLength(1)
  })

  it('пустой витрине нечего запускать', () => {
    expect(startRun([], NOW, seededRandom(7))).toEqual(emptyRun())
  })
})

describe('очередь загрузки', () => {
  it('показывает окно из очереди, а не весь круг', () => {
    const state = started()

    expect(waitingRows(state, 6)).toHaveLength(6)
    expect(waitingRows(state, 3)).toHaveLength(3)
    expect(state.pool).toHaveLength(POOL.length)
  })

  it('свежие строки сверху, по убыванию номера — как в книге учёта', () => {
    const numbers = waitingRows(started(), 6).map(row => Number(row.number))

    expect(numbers).toEqual([11, 10, 9, 8, 7, 6])
    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
  })

  it('строка, ушедшая на линию, больше не стоит в окне загрузки', () => {
    const start = started()
    const queued = Number(waitingRows(start, 1)[0].number)

    const state = tick(start, EXIT_INTERVAL_SECONDS)

    expect(waitingRows(state, 6).some(row => Number(row.number) === queued)).toBe(false)
    expect(state.line[0]?.number).toBe(queued)
  })
})

describe('темп прогона', () => {
  it('подвес стоит в ванне все 20 секунд и уходит только на двадцатой', () => {
    const start = started()
    const watched = start.line[0]!.number

    let state = start
    for (let second = 1; second <= LINE_SECONDS - 1; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
    }

    // Двадцать секунд — это весь путь подвеса от входа до схода, а не время
    // в одной ванне: раньше двадцатой он в выгрузку попасть не может.
    expect(state.line.some(hanger => hanger.number === watched)).toBe(true)
    expect(state.unloaded.some(row => Number(row.number) === watched)).toBe(false)
    expect(tick(start, LINE_SECONDS).unloaded[0].number).toBe(String(watched))
  })

  it('подвес уходит сразу в ванну схода, а не проходит ванны по очереди', () => {
    const start = started()
    const leaving = start.line[0]!

    const state = tick(start, LINE_SECONDS)

    expect(state.unloaded[0].number).toBe(String(leaving.number))
    expect(state.line.some(hanger => hanger.number === leaving.number)).toBe(false)
  })

  it('выход с линии раз в 5 секунд, а не каждый тик', () => {
    const start = started()

    expect(tick(start, EXIT_INTERVAL_SECONDS - 1).unloaded).toHaveLength(1)
    expect(tick(start, EXIT_INTERVAL_SECONDS).unloaded).toHaveLength(2)
    expect(tick(start, EXIT_INTERVAL_SECONDS * 2).unloaded).toHaveLength(3)
  })

  it('в ванне всегда ровно четыре подвеса, ни одна карточка не пустует', () => {
    let state = started()
    const snapshots: number[][] = []

    for (let second = 1; second <= LINE_SECONDS * 3; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      snapshots.push(cardRemainders(state))
    }

    expect(snapshots.every(remainders => remainders.every(remaining => remaining >= 0))).toBe(true)
  })

  it('лесенка остатков держится весь прогон, кроме секунды выхода', () => {
    let state = started()
    const ladders: number[][] = []

    for (let second = 1; second <= LINE_SECONDS; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      ladders.push(cardRemainders(state))
    }

    // Секунды до выхода тают лесенкой, на пятой линия повернулась и лесенка
    // восстановилась: ушедший подвес заменён новым с полным остатком.
    expect(ladders.slice(0, EXIT_INTERVAL_SECONDS - 1)).toEqual(
      Array.from({ length: EXIT_INTERVAL_SECONDS - 1 }, (_, index) => [19 - index, 14 - index, 9 - index, 4 - index]),
    )
    expect(ladders[EXIT_INTERVAL_SECONDS - 1]).toEqual([20, 15, 10, 5])
  })

  it('время на карточке «Вышел» идёт вверх, а не стоит на нуле', () => {
    const start = started()
    const exited = start.atExit!.number

    // Карточка показывает, сколько подвес простоял в ванне схода: остаток
    // тает, значит время в ванне растёт.
    const stood = [1, 2, 3].map(seconds => {
      const state = tick(start, seconds)
      return state.atExit?.number === exited ? state.atExit.stoodSeconds : -1
    })

    expect(stood).toEqual([1, 2, 3])
  })

  it('выгруженный подвес сохраняет профиль и цвет строки каталога', () => {
    const start = started()
    const leaving = start.line[0]!

    const state = tick(start, LINE_SECONDS)

    expect(state.unloaded[0].profile).toBe(leaving.row.profile)
    expect(state.unloaded[0].color).toBe(leaving.row.color)
  })

  it('время выгрузки — момент ухода, время входа на линию — когда подвес встал', () => {
    const start = started()

    const state = tick(start, LINE_SECONDS)

    expect(state.unloaded[0].entry_time).toBe(formatLocalized(NOW, 'ru-RU'))
    expect(state.unloaded[0].exit_time).toBe(formatLocalized(at(LINE_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].time).toBe(formatLocalized(at(LINE_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].entry_date).toBe('29.09.26')
    expect(state.unloaded[0].exit_date).toBe('29.09.26')
  })

  it('выгрузка читается свежими сверху, по убыванию номера', () => {
    const state = tick(started(), LINE_SECONDS * 2)
    const numbers = state.unloaded.map(row => Number(row.number))

    expect(numbers).toEqual([9, 8, 7, 6, 5, 4, 3, 2, 1])
    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
  })

  it('выгрузку режет потолок из аргумента, а не константа', () => {
    const state = tick(started(), LINE_SECONDS * 4, 3)

    expect(state.unloaded).toHaveLength(3)
    expect(state.unloaded.map(row => Number(row.number))).toEqual([17, 16, 15])
  })

  it('без строк прогон не падает', () => {
    expect(advanceRun(emptyRun(), NOW, 15, seededRandom(7))).toEqual(emptyRun())
  })
})

describe('круг профилей', () => {
  it('после круга в очереди те же профили, но в другом порядке', () => {
    const start = started()
    const state = tick(start, LAP_SECONDS)

    expect(state.pool.map(item => item.profile)).not.toEqual(start.pool.map(item => item.profile))
    expect(state.pool.map(item => item.profile).sort()).toEqual(start.pool.map(item => item.profile).sort())
  })

  it('после круга строки получают новые номера — профиль возвращается в очередь как новый подвес', () => {
    const start = started()
    const beforeLap = start.pool.map(row => Number(row.number))

    const state = tick(start, LAP_SECONDS)
    const afterLap = state.pool.map(row => Number(row.number))
    const firstNumber = Math.min(...afterLap)

    expect(firstNumber).toBeGreaterThan(POOL.length)
    expect(afterLap.map(number => number - firstNumber + 1).sort((a, b) => a - b))
      .toEqual([...beforeLap].sort((a, b) => a - b))
  })

  it('нумерация подвесов сквозная: круг не начинает счёт заново', () => {
    const state = tick(started(), LAP_SECONDS)

    expect(state.nextNumber).toBeGreaterThan(POOL.length)
  })

  it('короткий круг не роняет прогон: номера на линии остаются разными', () => {
    let state = startRun(POOL.slice(0, 1), NOW, seededRandom(7))

    for (let second = 1; second <= LAP_SECONDS; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
    }

    expect(new Set(lineNumbers(state)).size).toBe(FORECAST_BATHS.length + 1)
    expect(state.unloaded.length).toBeGreaterThan(0)
  })
})
