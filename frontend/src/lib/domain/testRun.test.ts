import { describe, expect, it } from 'vitest'
import {
  DWELL_SECONDS,
  FORECAST_BATHS,
  LAUNCH_WINDOW,
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
    date: '28.09.2026',
    time: '',
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
  let value = seed
  return () => {
    value = (value * 9301 + 49297) % 233280
    return value / 233280
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

describe('startRun', () => {
  it('занимает четыре ванны прогноза и ванну схода', () => {
    const state = started()

    expect(state.inBaths).toHaveLength(FORECAST_BATHS.length)
    expect(state.atExit).not.toBeNull()
  })

  it('в каждой ванне полный остаток: линия только что встала', () => {
    const state = started()

    expect(state.inBaths.map(hanger => hanger.remainingTime)).toEqual([20, 20, 20, 20])
    expect(state.atExit?.remainingTime).toBe(20)
  })

  it('запускает подвесы по порядку очереди, в ванну 34 — того, кто сойдёт первым', () => {
    const state = started()

    expect(state.inBaths.map(hanger => hanger.number)).toEqual([1, 2, 3, 4])
    expect(state.atExit?.number).toBe(5)
    expect(state.inBaths.every(hanger => PALETTE.includes(hanger.row.color))).toBe(true)
  })

  it('в очереди загрузки время пустое, а ушедшему на линию время уже проставлено', () => {
    const state = started()

    expect(waitingRows(state, 6).every(row => row.time === '')).toBe(true)
    expect(state.launched.every(row => row.time !== '')).toBe(true)
  })

  it('подвес, вставший в ванну 30 позже, встал на линию позже того, кто стоит в ванне 34', () => {
    const state = tick(started(), DWELL_SECONDS)

    expect(state.inBaths[0].row.time > state.atExit!.row.time).toBe(true)
  })

  it('кладёт в боковую очередь запущенные подвесы, новые сверху', () => {
    const state = started()

    expect(state.launched.map(row => Number(row.number))).toEqual([5, 4, 3, 2, 1])
    expect(state.unloaded).toEqual([])
  })

  it('круг короче блока ванн: линия всё равно заполнена целиком', () => {
    const state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))

    expect(state.inBaths).toHaveLength(FORECAST_BATHS.length)
    expect(state.atExit).not.toBeNull()
    // Номера на линии не повторяются, даже когда профилей меньше, чем ванн.
    const onLine = [...state.inBaths.map(hanger => hanger.number), state.atExit!.number]
    expect(new Set(onLine).size).toBe(FORECAST_BATHS.length + 1)
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

  it('окно держит размер, пока подвесы уходят с линии', () => {
    const start = started()

    const state = tick(start, DWELL_SECONDS)

    expect(waitingRows(state, 6)).toHaveLength(6)
    expect(state.cursor).toBe(start.cursor + 1)
  })

  it('строка, ушедшая на линию, больше не стоит в окне загрузки', () => {
    const start = started()
    const leaving = waitingRows(start, 1)[0].number

    const state = tick(start, DWELL_SECONDS)

    expect(waitingRows(state, 6).some(row => row.number === leaving)).toBe(false)
    expect(state.launched.some(row => row.number === leaving)).toBe(true)
  })
})

describe('advanceRun', () => {
  it('подвес лежит в ванне все 20 секунд и уходит только на двадцатой', () => {
    const start = started()
    const held = tick(start, DWELL_SECONDS - 1)
    const gone = tick(start, DWELL_SECONDS)

    expect(held.unloaded).toEqual([])
    expect(gone.unloaded).toHaveLength(1)
  })

  it('с линии уходит один подвес раз в 20 секунд, а не каждый тик', () => {
    expect(tick(started(), DWELL_SECONDS - 1).unloaded).toHaveLength(0)
    expect(tick(started(), DWELL_SECONDS).unloaded).toHaveLength(1)
    expect(tick(started(), DWELL_SECONDS * 2).unloaded).toHaveLength(2)
  })

  it('подвес идёт по ваннам подряд, а не прыгает', () => {
    const start = started()
    const exitNumber = start.atExit!.number
    const bath33Number = start.inBaths[FORECAST_BATHS.length - 1].number

    const state = tick(start, DWELL_SECONDS)

    expect(state.unloaded.map(row => Number(row.number))).toEqual([exitNumber])
    expect(state.atExit?.number).toBe(bath33Number)
  })

  it('в ванну 30 встаёт следующий из очереди, а ванны сдвигаются вперёд', () => {
    const start = started()
    const before = start.inBaths.map(hanger => hanger.number)
    const queued = waitingRows(start, 1)[0].number

    const state = tick(start, DWELL_SECONDS)

    expect(state.inBaths.map(hanger => hanger.number)).toEqual([Number(queued), ...before.slice(0, 3)])
  })

  it('выгруженный подвес сохраняет профиль и цвет строки каталога', () => {
    const start = started()
    const state = tick(start, DWELL_SECONDS)

    expect(state.unloaded[0].profile).toBe(start.atExit!.row.profile)
    expect(state.unloaded[0].color).toBe(start.atExit!.row.color)
  })

  it('ни одна ванна не пустует между подвесами даже на коротком круге', () => {
    const shortCircle = startRun(POOL.slice(0, 3), NOW, seededRandom(7))
    let state = shortCircle
    const snapshots: number[][] = []

    for (let second = 1; second <= DWELL_SECONDS * 2; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      snapshots.push([...state.inBaths.map(hanger => hanger.number), ...(state.atExit ? [state.atExit.number] : [])])
    }

    // В каждом снимке ровно по подвесу на ванну: 30, 31, 32, 33 и 34.
    expect(snapshots.every(bathNumbers => bathNumbers.length === FORECAST_BATHS.length + 1)).toBe(true)
  })

  it('время выгрузки — момент ухода, время входа на линию — когда встал', () => {
    const start = started()
    const entryTime = start.atExit!.row.time

    const state = tick(start, DWELL_SECONDS)

    expect(state.unloaded[0].entry_time).toBe(entryTime)
    expect(state.unloaded[0].exit_time).toBe(formatLocalized(at(DWELL_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].time).toBe(formatLocalized(at(DWELL_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].entry_date).toBe('28.09.2026')
    expect(state.unloaded[0].exit_date).toBe('28.09.2026')
  })

  it('выгрузку режет потолок из аргумента, а не константа', () => {
    const state = tick(started(), DWELL_SECONDS * 4, 3)

    expect(state.unloaded).toHaveLength(3)
    // Новые сверху: последний сошедший подвес стоит первой строкой.
    expect(state.unloaded.map(row => Number(row.number))).toEqual([2, 3, 4])
  })

  it('в боковой очереди последние запущенные подвесы, новые сверху', () => {
    const state = tick(started(), DWELL_SECONDS * LAUNCH_WINDOW)
    const numbers = state.launched.map(row => Number(row.number))

    expect(state.launched).toHaveLength(LAUNCH_WINDOW)
    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
  })

  it('после круга в очереди те же профили, но в другом порядке', () => {
    const start = started()
    const state = tick(start, DWELL_SECONDS * POOL.length)

    expect(state.pool.map(item => item.profile)).not.toEqual(start.pool.map(item => item.profile))
    expect(state.pool.map(item => item.profile).sort()).toEqual(start.pool.map(item => item.profile).sort())
  })

  it('после круга строки получают новые номера — профиль возвращается в очередь как новый подвес', () => {
    const start = started()
    const beforeLap = start.pool.map(row => Number(row.number))

    const state = tick(start, DWELL_SECONDS * POOL.length)
    const afterLap = state.pool.map(row => Number(row.number))
    const firstNumber = Math.min(...afterLap)

    expect(firstNumber).toBeGreaterThan(POOL.length)
    expect(afterLap.map(number => number - firstNumber + 1).sort((a, b) => a - b))
      .toEqual([...beforeLap].sort((a, b) => a - b))
  })

  it('нумерация подвесов сквозная: круг не начинает счёт заново', () => {
    const state = tick(started(), DWELL_SECONDS * POOL.length)

    expect(state.nextNumber).toBeGreaterThan(POOL.length)
  })

  it('без строк прогон не падает', () => {
    expect(advanceRun(emptyRun(), NOW, 15, seededRandom(7))).toEqual(emptyRun())
  })
})
