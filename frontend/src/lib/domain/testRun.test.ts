import { describe, expect, it } from 'vitest'
import {
  CONTROL_BATH,
  DWELL_SECONDS,
  FORECAST_BATHS,
  LINE_BATHS,
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

/** Подвесы, стоящие на ваннах, от загрузки к сходу. */
function lineNumbers(state: RunState): number[] {
  return [...state.inBaths.map(hanger => hanger.number), ...(state.atExit ? [state.atExit.number] : [])]
}

/** Снимок линии: ванна, номер подвеса и остаток. Пустая ванна — null. */
function lineTrace(state: RunState): ([number, number, number] | null)[] {
  return [
    ...state.inBaths.map((hanger, index) => [FORECAST_BATHS[index], hanger?.number ?? 0, hanger?.remainingTime ?? 0] as [number, number, number]),
    state.atExit ? [CONTROL_BATH, state.atExit.number, state.atExit.remainingTime] : null,
  ]
}

/** Где в этом снимке прогона стоит подвес с таким номером; −1, если его на линии нет. */
function where(state: RunState, number: number): number {
  return lineTrace(state).find(bath => bath !== null && bath[1] === number)?.[0] ?? -1
}

describe('старт прогона', () => {
  it('занимает четыре ванны прогноза и ванну схода', () => {
    const state = started()

    expect(state.inBaths).toHaveLength(FORECAST_BATHS.length)
    expect(state.atExit).not.toBeNull()
  })

  it('в ванне ровно один подвес, как на линии', () => {
    const state = started()

    expect(lineTrace(state)).toHaveLength(LINE_BATHS.length)
    expect(new Set(lineNumbers(state)).size).toBe(LINE_BATHS.length)
  })

  it('в каждой ванне полный остаток: линия только что встала', () => {
    const state = started()

    expect(lineTrace(state).map(bath => bath?.[2])).toEqual(Array(LINE_BATHS.length).fill(DWELL_SECONDS))
  })

  it('номера вдоль линии растут: кто встал раньше, тот дальше и сойдёт первым', () => {
    const state = started()

    expect(lineNumbers(state)).toEqual([5, 4, 3, 2, 1])
    expect([...state.inBaths, state.atExit!].every(hanger => PALETTE.includes(hanger.row.color))).toBe(true)
  })

  it('очередь загрузки сохраняет время витрины, а на линии время прогона', () => {
    const state = started()

    expect(waitingRows(state, 6).every(row => row.time === '12:00:00')).toBe(true)
    expect(lineNumbers(state).length).toBe(LINE_BATHS.length)
    expect([...state.inBaths, state.atExit!].every(hanger => hanger.row.time === formatLocalized(NOW, 'ru-RU'))).toBe(true)
  })

  it('круг короче блока ванн: линия всё равно заполнена целиком', () => {
    const state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))

    expect(state.inBaths).toHaveLength(FORECAST_BATHS.length)
    expect(state.atExit).not.toBeNull()
    // Номера на линии не повторяются, даже когда профилей меньше, чем ванн.
    expect(new Set(lineNumbers(state)).size).toBe(LINE_BATHS.length)
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

    const state = tick(start, DWELL_SECONDS)

    expect(waitingRows(state, 6).some(row => Number(row.number) === queued)).toBe(false)
    expect(state.inBaths[0].number).toBe(queued)
  })
})

describe('темп прогона', () => {
  it('подвес лежит в ванне все 20 секунд и уходит только на двадцатой', () => {
    const start = started()
    const watched = start.inBaths[FORECAST_BATHS.length - 1].number

    let state = start
    const trace: [number, number][] = []
    for (let second = 1; second <= DWELL_SECONDS + 1; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      const bath = where(state, watched)
      trace.push(bath < 0
        ? [-1, -1]
        : [bath, state.inBaths.find(h => h?.number === watched)?.remainingTime ?? state.atExit?.remainingTime ?? -1])
    }

    // Первые девятнадцать секунд подвес стоит в ванне 33 с остатком 19…1, на
    // двадцатой — переход в ванну схода с полным остатком.
    expect(trace).toEqual([
      ...Array.from({ length: DWELL_SECONDS - 1 }, (_, index) => [33, DWELL_SECONDS - 1 - index]),
      [CONTROL_BATH, DWELL_SECONDS],
      [CONTROL_BATH, DWELL_SECONDS - 1],
    ])
  })

  it('с линии уходит подвес раз в 20 секунд, а не каждый тик', () => {
    expect(tick(started(), DWELL_SECONDS - 1).unloaded).toHaveLength(0)
    expect(tick(started(), DWELL_SECONDS).unloaded).toHaveLength(1)
    expect(tick(started(), DWELL_SECONDS * 2).unloaded).toHaveLength(2)
  })

  it('подвес идёт по ваннам подряд: из 33 в ванну схода, а не прыгает', () => {
    const start = started()
    const atControlBath = start.atExit!.number
    const atBath33 = start.inBaths[FORECAST_BATHS.length - 1].number

    const state = tick(start, DWELL_SECONDS)

    expect(state.unloaded.map(row => Number(row.number))).toEqual([atControlBath])
    expect(state.atExit?.number).toBe(atBath33)
  })

  it('ни одна ванна не пустует между подвесами даже на коротком круге', () => {
    let state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))
    const snapshots: ([number, number, number] | null)[][] = []

    for (let second = 1; second <= DWELL_SECONDS * 3; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      snapshots.push(lineTrace(state))
    }

    // В каждом снимке ровно по подвесу на ванну: 30, 31, 32, 33 и 34.
    expect(snapshots.every(line => line.length === LINE_BATHS.length && line.every(bath => bath !== null))).toBe(true)
  })

  it('выгруженный подвес сохраняет профиль и цвет строки каталога', () => {
    const start = started()
    const leaving = start.atExit!

    const state = tick(start, DWELL_SECONDS)

    expect(state.unloaded[0].profile).toBe(leaving.row.profile)
    expect(state.unloaded[0].color).toBe(leaving.row.color)
  })

  it('выгрузка читается свежими сверху, по убыванию номера', () => {
    const state = tick(started(), DWELL_SECONDS * 3)
    const numbers = state.unloaded.map(row => Number(row.number))

    expect(numbers).toEqual([3, 2, 1])
  })

  it('время выгрузки — момент ухода, время входа на линию — когда подвес встал', () => {
    const start = started()
    const entryTime = start.atExit!.row.time

    const state = tick(start, DWELL_SECONDS)

    expect(state.unloaded[0].entry_time).toBe(entryTime)
    expect(state.unloaded[0].exit_time).toBe(formatLocalized(at(DWELL_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].time).toBe(formatLocalized(at(DWELL_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].entry_date).toBe('29.09.26')
    expect(state.unloaded[0].exit_date).toBe('29.09.26')
  })

  it('выгрузку режет потолок из аргумента, а не константа', () => {
    const state = tick(started(), DWELL_SECONDS * 4, 3)

    expect(state.unloaded).toHaveLength(3)
    expect(state.unloaded.map(row => Number(row.number))).toEqual([4, 3, 2])
  })

  it('без строк прогон не падает', () => {
    expect(advanceRun(emptyRun(), NOW, 15, seededRandom(7))).toEqual(emptyRun())
  })
})

describe('круг профилей', () => {
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

  it('короткий круг не роняет прогон: номера на линии остаются разными', () => {
    let state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))

    for (let second = 1; second <= DWELL_SECONDS * 40; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
    }

    expect(new Set(lineNumbers(state)).size).toBe(LINE_BATHS.length)
    expect(state.unloaded.length).toBeGreaterThan(0)
  })
})