import { describe, expect, it } from 'vitest'
import {
  CONTROL_BATH,
  DWELL_SECONDS,
  ENTRY_INTERVAL_SECONDS,
  FORECAST_BATHS,
  HANGERS_PER_BATH,
  LINE_BATHS,
  advanceRun,
  cardHangers,
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

/** Подвесы, стоящие на ваннах, от загрузки к сходу: одна строка на ванну — как в карточках. */
function lineNumbers(state: RunState): number[] {
  return cardHangers(state).map(hanger => hanger?.number ?? -1)
}

/** Где в этом снимке прогона стоит подвес с таким номером. */
function where(state: RunState, number: number): number {
  const found = state.baths.findIndex(queue => queue.some(hanger => hanger.number === number))
  expect(found, `подвес ${number} не найден на линии`).toBeGreaterThanOrEqual(0)
  return LINE_BATHS[found]
}

describe('старт прогона', () => {
  it('занимает все ванны линии, в каждой по HANGERS_PER_BATH подвесов', () => {
    const state = started()

    expect(state.baths).toHaveLength(LINE_BATHS.length)
    expect(state.baths.map(queue => queue.length)).toEqual(Array(LINE_BATHS.length).fill(HANGERS_PER_BATH))
  })

  it('карточки ванн стоят лесенкой: 5, 10, 15, 20 секунд, ванна схода — 5', () => {
    const state = started()

    expect(cardHangers(state).map(hanger => hanger?.remainingTime))
      .toEqual([ENTRY_INTERVAL_SECONDS, ENTRY_INTERVAL_SECONDS * 2, ENTRY_INTERVAL_SECONDS * 3, DWELL_SECONDS, ENTRY_INTERVAL_SECONDS])
  })

  it('номера вдоль линии растут: кто встал раньше, тот дальше и сойдёт первым', () => {
    const state = started()

    const numbers = lineNumbers(state)
    const onLine = state.baths.flat().map(hanger => hanger.number)

    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
    expect(numbers[numbers.length - 1]).toBe(Math.min(...onLine))
    expect(cardHangers(state).every(hanger => hanger && PALETTE.includes(hanger.row.color))).toBe(true)
  })

  it('подвесы карточек — разный стаж: у ванны 33 подвес встал на линию минуту назад', () => {
    const state = started()

    expect(cardHangers(state).map(hanger => hanger?.row.time)).toEqual([
      formatLocalized(at(-15), 'ru-RU'),
      formatLocalized(at(-30), 'ru-RU'),
      formatLocalized(at(-45), 'ru-RU'),
      formatLocalized(at(-60), 'ru-RU'),
      formatLocalized(at(-95), 'ru-RU'),
    ])
  })

  it('очередь загрузка продолжает круг: из круга ушло ровно столько подвесов, сколько стоит на линии', () => {
    const state = started()

    expect(state.cursor).toBe(LINE_BATHS.length * HANGERS_PER_BATH)
    expect(state.nextNumber).toBe(POOL.length + 1)
    expect(waitingRows(state, 6).every(row => row.time === '12:00:00')).toBe(true)
  })

  it('круг короче линии: линия всё равно заполнена, номера на ней не повторяются', () => {
    const state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))
    const numbers = state.baths.flat().map(hanger => hanger.number)

    expect(state.baths.map(queue => queue.length)).toEqual(Array(LINE_BATHS.length).fill(HANGERS_PER_BATH))
    expect(new Set(numbers).size).toBe(numbers.length)
    expect(state.nextNumber).toBeGreaterThan(3)
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

    expect(numbers).toEqual([26, 25, 24, 23, 22, 21])
    expect(numbers).toEqual([...numbers].sort((a, b) => b - a))
  })

  it('теряет по одной строке каждые ENTRY_INTERVAL_SECONDS', () => {
    const start = started()

    const state = tick(start, ENTRY_INTERVAL_SECONDS * 3)

    expect(state.cursor).toBe(start.cursor + 3)
    expect(waitingRows(state, 6)).toHaveLength(6)
  })

  it('строка, ушедшая на линию, больше не стоит в окне загрузки', () => {
    const start = started()
    const leaving = Number(waitingRows(start, 1)[0].number)

    const state = tick(start, ENTRY_INTERVAL_SECONDS)

    expect(waitingRows(state, 6).some(row => Number(row.number) === leaving)).toBe(false)
    expect(state.baths[0][state.baths[0].length - 1]?.number).toBe(leaving)
  })
})

describe('темп прогона', () => {
  it('выгрузка получает ровно один подвес каждые ENTRY_INTERVAL_SECONDS', () => {
    let state = started()
    const exitsPerTick: number[] = []

    for (let second = 1; second <= ENTRY_INTERVAL_SECONDS * 6; second += 1) {
      const before = state.unloaded.length
      state = advanceRun(state, at(second), 100, seededRandom(7))
      exitsPerTick.push(state.unloaded.length - before)
    }

    expect(exitsPerTick).toEqual(Array.from({ length: ENTRY_INTERVAL_SECONDS * 6 }, (_, index) => (index + 1) % ENTRY_INTERVAL_SECONDS === 0 ? 1 : 0))
  })

  it('подвес лежит в ванне все 20 секунд и уходит из неё только на двадцатой', () => {
    const start = started()
    const watched = start.baths[FORECAST_BATHS.length - 1][HANGERS_PER_BATH - 1].number

    let state = start
    const trace: [number, number][] = []
    for (let second = 1; second <= DWELL_SECONDS + 1; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      const bathIndex = state.baths.findIndex(queue => queue.some(hanger => hanger.number === watched))
      const hanger = bathIndex < 0 ? null : state.baths[bathIndex].find(item => item.number === watched) ?? null
      trace.push(hanger ? [LINE_BATHS[bathIndex], hanger.remainingTime] : [-1, -1])
    }

    // Двадцать секунд в ванне 33 с остатком 19…1 и только на двадцатой —
    // переход в ванну схода с полным остатком.
    expect(trace).toEqual([
      ...Array.from({ length: DWELL_SECONDS - 1 }, (_, index) => [33, DWELL_SECONDS - 1 - index]),
      [CONTROL_BATH, DWELL_SECONDS],
      [CONTROL_BATH, DWELL_SECONDS - 1],
    ])
  })

  it('ни одна ванна не пустует между подвесами даже на коротком круге', () => {
    let state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))
    const snapshots: number[][] = []

    for (let second = 1; second <= DWELL_SECONDS * 3; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
      snapshots.push(state.baths.map(queue => queue.length))
    }

    expect(snapshots.every(occupancy => occupancy.every(count => count === HANGERS_PER_BATH))).toBe(true)
  })

  it('подвес идёт по ваннам подряд: из 33 в ванну схода, а не прыгает', () => {
    const start = started()
    const atBath33 = start.baths[FORECAST_BATHS.length - 1][0].number
    const atControlBath = start.baths[LINE_BATHS.length - 1][0].number

    const state = tick(start, ENTRY_INTERVAL_SECONDS)

    expect(state.unloaded.map(row => Number(row.number))).toEqual([atControlBath])
    expect(where(state, atBath33)).toBe(CONTROL_BATH)
  })

  it('ванны поворачиваются вместе: ушедшие встают в следующую ванну, встающие — с полным остатком', () => {
    const start = started()
    const headOfBath32 = start.baths[2][0].number

    const state = tick(start, ENTRY_INTERVAL_SECONDS)

    expect(state.baths[3][state.baths[3].length - 1].number).toBe(headOfBath32)
    expect(state.baths.map(queue => queue[queue.length - 1].remainingTime))
      .toEqual(Array(LINE_BATHS.length).fill(DWELL_SECONDS))
  })

  it('выгруженный подвес сохраняет профиль и цвет строки каталога', () => {
    const start = started()
    const leaving = start.baths[LINE_BATHS.length - 1][0]

    const state = tick(start, ENTRY_INTERVAL_SECONDS)

    expect(state.unloaded[0].profile).toBe(leaving.row.profile)
    expect(state.unloaded[0].color).toBe(leaving.row.color)
  })

  it('время выгрузки — момент ухода, время входа на линию — когда подвес встал', () => {
    const start = started()
    const entryTime = start.baths[LINE_BATHS.length - 1][0].row.time

    const state = tick(start, ENTRY_INTERVAL_SECONDS)

    expect(state.unloaded[0].entry_time).toBe(entryTime)
    expect(state.unloaded[0].exit_time).toBe(formatLocalized(at(ENTRY_INTERVAL_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].time).toBe(formatLocalized(at(ENTRY_INTERVAL_SECONDS), 'ru-RU'))
    expect(state.unloaded[0].entry_date).toBe('29.09.26')
    expect(state.unloaded[0].exit_date).toBe('29.09.26')
  })

  it('выгрузка читается свежими сверху, по убыванию номера', () => {
    const state = tick(started(), ENTRY_INTERVAL_SECONDS * 3)
    const numbers = state.unloaded.map(row => Number(row.number))

    expect(numbers).toEqual([3, 2, 1])
  })

  it('выгрузку режет потолок из аргумента, а не константа', () => {
    const state = tick(started(), ENTRY_INTERVAL_SECONDS * 4, 3)

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
    const state = tick(start, ENTRY_INTERVAL_SECONDS * POOL.length)

    expect(state.pool.map(item => item.profile)).not.toEqual(start.pool.map(item => item.profile))
    expect(state.pool.map(item => item.profile).sort()).toEqual(start.pool.map(item => item.profile).sort())
  })

  it('после круга строки получают новые номера — профиль возвращается в очередь как новый подвес', () => {
    const start = started()
    const beforeLap = start.pool.map(row => Number(row.number))

    const state = tick(start, ENTRY_INTERVAL_SECONDS * POOL.length)
    const afterLap = state.pool.map(row => Number(row.number))
    const firstNumber = Math.min(...afterLap)

    expect(firstNumber).toBeGreaterThan(POOL.length)
    expect(afterLap.map(number => number - firstNumber + 1).sort((a, b) => a - b))
      .toEqual([...beforeLap].sort((a, b) => a - b))
  })

  it('нумерация подвесов сквозная: круг не начинает счёт заново', () => {
    const state = tick(started(), ENTRY_INTERVAL_SECONDS * POOL.length)

    expect(state.nextNumber).toBeGreaterThan(POOL.length)
  })

  it('короткий круг не роняет прогон: номера на линии остаются разными', () => {
    let state = startRun(POOL.slice(0, 3), NOW, seededRandom(7))

    for (let second = 1; second <= ENTRY_INTERVAL_SECONDS * 40; second += 1) {
      state = advanceRun(state, at(second), 15, seededRandom(7))
    }

    const numbers = state.baths.flat().map(hanger => hanger.number)

    expect(new Set(numbers).size).toBe(numbers.length)
    expect(state.unloaded.length).toBeGreaterThan(0)
  })
})