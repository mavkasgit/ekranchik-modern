// Тестовый прогон витрины: подвесы идут по ваннам, по таймеру уходят
// в выгрузку, в освободившуюся ванну входит следующий. Единственный владелец
// правил прогона: страница только рисует то, что отсюда пришло.

import { SIDEBAR_ROW_LIMIT } from '@/config/limits'
import type { HangerData } from '@/types/dashboard'

/** Ванны прогона: позиция подвеса в списке — номер ванны. */
export const RUN_BATHS = [30, 31, 32, 33]
/** Сколько подвес лежит в ванне до выгрузки. */
export const DWELL_SECONDS = 20
/** Разгон ванн на старте: с таким остатком уходит ровно один подвес каждые 5 секунд. */
const START_COUNTDOWN = [20, 15, 10, 5]
/** Строк в боковой очереди прогона: столько же, сколько тянет живая очередь. */
export const LAUNCH_WINDOW = SIDEBAR_ROW_LIMIT
/** Строк в таблице выгрузки: одиннадцатая вытесняет самую старую. */
export const UNLOAD_LIMIT = 10

export interface RunHanger {
  /** Сквозной номер подвеса: с 1 до сброса прогона. */
  number: number
  /** Остаток до выгрузки, секунды. */
  remainingTime: number
  /** Строка витрины: профиль, цвет, фото. */
  row: HangerData
}

export interface RunState {
  /** Подвесы в ваннах. Позиция в массиве — номер ванны. */
  inBaths: RunHanger[]
  /** Запущенные подвесы для боковой очереди: новые сверху. */
  launched: HangerData[]
  /** Выгруженные подвесы: новые сверху. */
  unloaded: HangerData[]
  /** Порядок запуска на текущий круг. */
  pool: HangerData[]
  /** Позиция в пуле: откуда берём следующего подвеса. */
  cursor: number
  /** Следующий сквозной номер подвеса. */
  nextNumber: number
}

export function emptyRun(): RunState {
  return { inBaths: [], launched: [], unloaded: [], pool: [], cursor: 0, nextNumber: 1 }
}

function shuffle<T>(items: T[], random: () => number): T[] {
  const result = [...items]
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1))
    const taken = result[i]
    result[i] = result[j]
    result[j] = taken
  }
  return result
}

/** Выгрузка: витринное время загрузки и реальный момент схода с линии. */
function toUnloadedRow(hanger: RunHanger, unloadTime: string): HangerData {
  const row = hanger.row
  return {
    ...row,
    number: String(hanger.number),
    time: unloadTime,
    entry_date: row.date,
    exit_date: row.date,
    entry_time: row.time,
    exit_time: unloadTime,
  }
}

/** Старт прогона: круг перемешан, первые подвесы разведены по ваннам разгоном. */
export function startRun(rows: HangerData[], random: () => number = Math.random): RunState {
  const pool = shuffle(rows, random)
  const starting = pool.slice(0, RUN_BATHS.length)
  const inBaths: RunHanger[] = []
  const launched: HangerData[] = []
  let nextNumber = 1

  // На старте линия уже в работе: подвес, которому осталось пять секунд, вошёл раньше
  // того, которому осталось двадцать. Номер — по порядку входа, поэтому первым
  // с линии сходит №1, а последним встаёт в ванну следующий.
  const entered = START_COUNTDOWN
    .map((remainingTime, bathIndex) => ({ remainingTime, bathIndex }))
    .filter(({ bathIndex }) => bathIndex < starting.length)
    .sort((a, b) => a.remainingTime - b.remainingTime)

  for (const { remainingTime, bathIndex } of entered) {
    const row = starting[bathIndex]
    const hanger: RunHanger = { number: nextNumber, remainingTime, row }
    nextNumber += 1
    inBaths[bathIndex] = hanger
    launched.unshift({ ...row, number: String(hanger.number) })
  }

  return { inBaths, launched, unloaded: [], pool, cursor: entered.length, nextNumber }
}

/**
 * Секундный тик: остаток у всех уменьшается, дошедшие до нуля уходят в выгрузку,
 * в их ванны входят новые. Круг кончился — порядок запуска перемешивается заново.
 */
export function advanceRun(
  state: RunState,
  unloadTime: string,
  random: () => number = Math.random,
): RunState {
  if (state.inBaths.length === 0) return state

  const finished: RunHanger[] = []
  const entered: RunHanger[] = []
  let cursor = state.cursor
  let nextNumber = state.nextNumber

  const inBaths = state.inBaths.map((hanger) => {
    const remainingTime = hanger.remainingTime - 1
    if (remainingTime > 0) return { ...hanger, remainingTime }

    finished.push(hanger)
    const row = state.pool[cursor % state.pool.length]
    const refilled: RunHanger = { number: nextNumber, remainingTime: DWELL_SECONDS, row }
    nextNumber += 1
    cursor += 1
    entered.push(refilled)
    return refilled
  })

  const lapComplete = cursor >= state.pool.length

  return {
    inBaths,
    launched: [...entered.reverse().map(hanger => ({ ...hanger.row, number: String(hanger.number) })), ...state.launched]
      .slice(0, LAUNCH_WINDOW),
    unloaded: [...finished.reverse().map(hanger => toUnloadedRow(hanger, unloadTime)), ...state.unloaded]
      .slice(0, UNLOAD_LIMIT),
    pool: lapComplete ? shuffle(state.pool, random) : state.pool,
    cursor: lapComplete ? 0 : cursor,
    nextNumber,
  }
}
