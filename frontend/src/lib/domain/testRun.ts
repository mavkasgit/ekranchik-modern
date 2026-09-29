// Тестовый прогон витрины: подвесы идут по ваннам подряд и по таймеру сходят
// с линии. Единственный владелец правил прогона: страница только рисует то,
// что отсюда пришло.
//
// Поведение повторяет линию: подвес входит в ванну 30 из очереди загрузки,
// проходит 31, 32, 33 и сходит с линии через ванну 34. В ванне — одно место,
// как на линии: подвес занимает его на DWELL_SECONDS, и следующий входит в ванну
// только когда предыдущий ушёл. Отсюда шаг линии равен времени обработки: в
// выгрузку приходит строка раз в DWELL_SECONDS, а не чаще.
//
// Номера вдоль маршрута растут, как в книге учёта: кто встал раньше, тот дальше
// по линии и сойдёт первым. Очередь и таблицы показывают строки свежими сверху,
// по убыванию номера, — так же, как на линии.

import { formatLocalized } from '@/lib/domain/time'
import type { HangerData } from '@/types/dashboard'

/** Ванны, у которых на дашборде есть карточка прогноза: позиция в массиве — номер ванны. */
export const FORECAST_BATHS = [30, 31, 32, 33]

/** Ванна схода: подвес, дошедший до неё, уходит с линии. */
export const CONTROL_BATH = 34

/** Ванны линии по порядку движения подвеса: позиция в массиве — номер ванны. */
export const LINE_BATHS = [...FORECAST_BATHS, CONTROL_BATH]

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
 *
 * Остаток у всех один: в ванне одно место, подвес занимает его на
 * ``DWELL_SECONDS``, и следующий входит в ванну только после ухода предыдущего.
 * Отсюда всё остальное: ванны поворачиваются вместе, выгрузка получает строку
 * раз в ``DWELL_SECONDS``, а выход каждые 5 секунд при одном подвесе на ванне
 * невозможен — для него на линии должно стоять двадцать подвесов.
 */
export function startRun(rows: HangerData[], now: Date, random: () => number = Math.random): RunState {
  if (rows.length === 0) return emptyRun()

  // Время входа витринной строки сохраняется: пока подвес в очереди, видно время,
  // которым его нарисовали; при входе в ванну enterLine переставит своё.
  let pool = shuffle(rows, random).map((row, index) => ({ ...row, number: String(index + 1) }))
  let cursor = 0
  let nextNumber = pool.length + 1

  // Круг может быть короче блока ванн: тогда он перемешивается и нумеруется заново,
  // иначе в ванне 33 просто некому стоять, а подвес из 32 ушёл бы сразу в 34.
  const takeNext = (at: Date): RunHanger => {
    if (cursor >= pool.length) {
      pool = renumberPool(shuffle(pool, random), nextNumber)
      nextNumber += pool.length
      cursor = 0
    }
    const hanger = enterLine(pool[cursor], at)
    cursor += 1
    return hanger
  }

  const inBaths: RunHanger[] = []
  let atExit: RunHanger | null = null

  for (let step = 0; step < LINE_BATHS.length; step += 1) {
    const hanger = takeNext(now)
    // Шаг 0 — самая дальняя ванна, шаг 4 — ванна 30: номера вдоль маршрута растут.
    const slot = LINE_BATHS.length - 1 - step
    if (slot === LINE_BATHS.length - 1) {
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
 * Секундный тик. Пока остаток больше секунды, ванны просто тикают. Иначе
 * освободившиеся ванны поворачиваются: дошедший до нуля подвес переходит в
 * следующую ванну с полным остатком, сошедший с ванны схода уходит в выгрузку,
 * а в ванну 30 встаёт следующий из очереди загрузки.
 *
 * Ванны обходятся от схода к загрузке: место назначения к этому моменту уже
 * освободилось — и при разгоне, и когда ванны поворачиваются вместе. Если место
 * всё же занято (такого темпа прогон не даёт), подвес остаётся на своём месте с
 * нулевым остатком и уйдёт следующим тиком.
 */
export function advanceRun(
  state: RunState,
  now: Date,
  unloadLimit: number,
  random: () => number = Math.random,
): RunState {
  if (state.inBaths.length === 0 && state.atExit === null) return state

  const slots: (RunHanger | null)[] = [...state.inBaths, state.atExit]
  const ticking = slots.map(hanger => (
    hanger ? { ...hanger, remainingTime: Math.max(0, hanger.remainingTime - 1) } : null
  ))

  const unloadedNow: RunHanger[] = []
  const lastIndex = LINE_BATHS.length - 1

  for (let index = lastIndex; index >= 0; index -= 1) {
    const hanger = ticking[index]
    if (!hanger || hanger.remainingTime > 0) continue

    if (index === lastIndex) {
      unloadedNow.push(hanger)
      ticking[index] = null
    } else if (ticking[index + 1] === null) {
      ticking[index + 1] = { ...hanger, remainingTime: DWELL_SECONDS }
      ticking[index] = null
    }
  }

  let pool = state.pool
  let cursor = state.cursor
  let nextNumber = state.nextNumber

  if (ticking[0] === null) {
    if (cursor >= pool.length) {
      pool = renumberPool(shuffle(pool, random), nextNumber)
      nextNumber += pool.length
      cursor = 0
    }
    const hanger = enterLine(pool[cursor], now)
    cursor += 1
    ticking[0] = hanger
  }

  const inBaths = ticking.slice(0, lastIndex) as RunHanger[]

  return {
    inBaths,
    atExit: ticking[lastIndex],
    // Свежая строка сверху, прежние остаются под ней: по убыванию номера, как
    // на линии, где книга дописывается сверху.
    unloaded: [...unloadedNow.map(hanger => toUnloadedRow(hanger, now)), ...state.unloaded]
      .slice(0, Math.max(0, unloadLimit)),
    pool,
    cursor,
    nextNumber,
  }
}