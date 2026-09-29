// Тестовый прогон витрины: подвесы идут по ваннам подряд и по таймеру сходят
// с линии. Единственный владелец правил прогона: страница только рисует то,
// что отсюда пришло.
//
// Поведение повторяет линию: подвес входит в ванну 30 из очереди загрузки,
// проходит 31, 32, 33 и сходит с линии через ванну 34. Номера вдоль маршрута
// растут, как в книге учёта: кто встал раньше, тот дальше по линии и сойдёт
// первым. Очередь и таблицы показывают строки свежими сверху, по убыванию
// номера, — так же, как на линии.

import { formatLocalized } from '@/lib/domain/time'
import type { HangerData } from '@/types/dashboard'

/** Ванны, у которых на дашборде есть карточка прогноза: позиция в массиве — номер ванны. */
export const FORECAST_BATHS = [30, 31, 32, 33]

/** Ванна схода: подвес, дошедший до неё, уходит с линии. */
export const CONTROL_BATH = 34

/** Сколько подвес лежит в ванне до перехода в следующую. */
export const DWELL_SECONDS = 20

export interface RunHanger {
  /** Сквозной номер подвеса: с 1 до сброса прогона. */
  number: number
  /** Остаток до перехода в следующую ванну, секунды. */
  remainingTime: number
  /** Строка витрины с проставленным временем входа на линию. */
  row: HangerData
}

export interface RunState {
  /** Подвесы в ваннах прогноза. Позиция в массиве — ванна из FORECAST_BATHS. */
  inBaths: RunHanger[]
  /** Подвес в ванне схода: он следующий сойдёт с линии. */
  atExit: RunHanger | null
  /** Выгруженные подвесы: свежие сверху, по убыванию номера. */
  unloaded: HangerData[]
  /** Круг профилей: очередь загрузки и источник номеров на следующий круг. */
  pool: HangerData[]
  /** Позиция в круге: откуда берём следующего подвеса. */
  cursor: number
  /** Следующий сквозной номер подвеса. */
  nextNumber: number
}

export function emptyRun(): RunState {
  return { inBaths: [], atExit: null, unloaded: [], pool: [], cursor: 0, nextNumber: 1 }
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

/** Вход на линию: строка из очереди получает номер и время, когда подвес встал в ванну. */
function enterLine(row: HangerData, now: Date): RunHanger {
  return {
    number: Number(row.number),
    remainingTime: DWELL_SECONDS,
    row: { ...row, time: formatLocalized(now, 'ru-RU') },
  }
}

/** Выгрузка: момент входа на линию из витрины и реальный момент схода. */
function toUnloadedRow(hanger: RunHanger, now: Date): HangerData {
  const exitTime = formatLocalized(now, 'ru-RU')
  return {
    ...hanger.row,
    time: exitTime,
    entry_date: hanger.row.date,
    exit_date: hanger.row.date,
    entry_time: hanger.row.time,
    exit_time: exitTime,
  }
}

/** Новый круг: те же строки возвращаются в очередь уже под другими номерами. */
function renumberPool(rows: HangerData[], firstNumber: number): HangerData[] {
  return rows.map((row, offset) => ({ ...row, number: String(firstNumber + offset) }))
}

/**
 * Старт прогона: круг перемешан и пронумерован, первые подвесы разведены по
 * ваннам. Первый подвес из круга встаёт дальше всех по маршруту — в ванну
 * схода, — поэтому номера вдоль линии растут и сходятся по порядку.
 */
export function startRun(rows: HangerData[], now: Date, random: () => number = Math.random): RunState {
  if (rows.length === 0) return emptyRun()

  const ordered = shuffle(rows, random)
  // Время входа витринной строки сохраняется: пока подвес в очереди, видно время,
  // которым его нарисовали; при входе в ванну enterLine переставит своё.
  let pool = ordered.map((row, index) => ({ ...row, number: String(index + 1) }))
  let nextNumber = pool.length + 1
  let cursor = 0

  // Круг может быть короче блока ванн: тогда он перемешивается и нумеруется заново,
  // иначе в ванне 33 просто некому стоять, а подвес из 32 ушёл бы сразу в 34.
  const takeNext = (): RunHanger => {
    if (cursor >= pool.length) {
      pool = renumberPool(shuffle(pool, random), nextNumber)
      nextNumber += pool.length
      cursor = 0
    }
    const hanger = enterLine(pool[cursor], now)
    cursor += 1
    return hanger
  }

  const inBaths: RunHanger[] = []
  let atExit: RunHanger | null = null

  for (let step = 0; step < FORECAST_BATHS.length + 1; step += 1) {
    const hanger = takeNext()
    // Шаг 0 — самая дальняя ванна, шаг 4 — ванна 30: номера вдоль маршрута растут.
    const slot = FORECAST_BATHS.length - step
    if (slot === FORECAST_BATHS.length) {
      atExit = hanger
    } else {
      inBaths[slot] = hanger
    }
  }

  return { inBaths, atExit, unloaded: [], pool, cursor, nextNumber }
}

/**
 * Очередь загрузки: столько строк, сколько оператор видит в таблице загрузки.
 * Свежие строки сверху, то есть по убыванию номера подвеса: книга учёта
 * дописывается сверху, и на линии так же — сверху последняя заведённая.
 */
export function waitingRows(state: RunState, limit: number): HangerData[] {
  return state.pool.slice(state.cursor, state.cursor + Math.max(0, limit)).reverse()
}

/**
 * Секундный тик. Пока остаток больше секунды, ванны просто тикают. Иначе ванны
 * поворачиваются: каждый подвес переходит в следующую ванну, сошедший с ванны
 * 34 уходит в выгрузку, а в ванну 30 встаёт следующий из очереди загрузки.
 */
export function advanceRun(
  state: RunState,
  now: Date,
  unloadLimit: number,
  random: () => number = Math.random,
): RunState {
  const block = state.inBaths
  if (block.length === 0 && state.atExit === null) return state

  const standing = block.length > 0 ? block : [state.atExit as RunHanger]
  const soonest = Math.min(...standing.map(hanger => hanger.remainingTime))

  if (soonest > 1) {
    return {
      ...state,
      inBaths: block.map(hanger => ({ ...hanger, remainingTime: hanger.remainingTime - 1 })),
      atExit: state.atExit ? { ...state.atExit, remainingTime: state.atExit.remainingTime - 1 } : null,
    }
  }

  let pool = state.pool
  let cursor = state.cursor
  let nextNumber = state.nextNumber

  const takeNext = (): RunHanger => {
    if (cursor >= pool.length) {
      pool = renumberPool(shuffle(pool, random), nextNumber)
      nextNumber += pool.length
      cursor = 0
    }
    const hanger = enterLine(pool[cursor], now)
    cursor += 1
    return hanger
  }

  // Подвесы сдвигаются на ванну вперёд, освободившуюся ванну 30 занимает новый.
  const carried = block.slice(0, -1).map(hanger => ({ ...hanger, remainingTime: DWELL_SECONDS }))
  const inBaths = [takeNext(), ...carried]
  const atExit = { ...block[block.length - 1], remainingTime: DWELL_SECONDS }
  const unloadedNow = state.atExit ? [state.atExit] : []

  return {
    inBaths,
    atExit,
    // Свежая строка сверху, прежние остаются под ней: по убыванию номера, как
    // на линии, где книга дописывается сверху.
    unloaded: [...unloadedNow.map(hanger => toUnloadedRow(hanger, now)), ...state.unloaded]
      .slice(0, Math.max(0, unloadLimit)),
    pool,
    cursor,
    nextNumber,
  }
}
