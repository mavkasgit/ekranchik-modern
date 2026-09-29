// Тестовый прогон витрины: подвесы стоят в ванне и по таймеру сходят с линии.
// Единственный владелец правил прогона: страница только рисует то, что отсюда
// пришло.
//
// Подвес не идёт по ваннам 30…33: ванна одна, подвесы стоят в ней очередью и
// сразу уходят в ванну схода. Четыре карточки 30…33 — это четыре места одной
// ванны в порядке выхода: тот, кто уйдёт последним, стоит в 30-й, ближайший к
// сходу — в 33-й. Поэтому остатки на карточках всегда 20, 15, 10 и 5 секунд,
// а не «сколько осталось в своей ванне».

import { formatLocalized } from '@/lib/domain/time'
import type { HangerData } from '@/types/dashboard'

/** Ванны, у которых на дашборде есть карточка прогноза: позиция в массиве — номер ванны. */
export const FORECAST_BATHS = [30, 31, 32, 33]

/** Ванна схода: подвес, дошедший до неё, уходит с линии. */
export const CONTROL_BATH = 34

/** Сколько секунд подвес идёт от входа на линию до схода. */
export const LINE_SECONDS = 20

/**
 * Секунд между выходами. Карточек прогноза четыре, и каждую секунду подвес
 * становится на одну ближе к сходу — то есть шаг лесенки равен
 * ``LINE_SECONDS / FORECAST_BATHS.length``. Ванна вмещает ровно столько
 * подвесов, сколько карточек, поэтому очередь в ванне никогда не пустует.
 */
export const EXIT_INTERVAL_SECONDS = LINE_SECONDS / FORECAST_BATHS.length

export interface RunHanger {
  /** Сквозной номер подвеса: с 1 до сброса прогона. */
  number: number
  /** Сколько секунд подвесу осталось до схода с линии. */
  remainingTime: number
  /** Строка витрины с проставленным временем входа на линию. */
  row: HangerData
}

/** Подвес в ванне схода: он уже сошёл, карточка «Вышел» считает, сколько он там стоит. */
export interface ExitedHanger extends RunHanger {
  /** Сколько секунд подвес простоял в ванне схода. */
  stoodSeconds: number
}

export interface RunState {
  /**
   * Подвесы в ванне, от того кто уйдёт последним, к тому кто уйдёт первым:
   * нулевой элемент рисуется в ``FORECAST_BATHS[0]``, последний — в последней
   * ванне прогноза. Порядок не меняется, пока подвес на линии, поэтому карточки
   * всегда идут лесенкой остатков.
   */
  line: RunHanger[]
  /** Подвес, который только что сошёл с линии: он же верхняя строка выгрузки. */
  atExit: ExitedHanger | null
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
  return { line: [], atExit: null, unloaded: [], pool: [], cursor: 0, nextNumber: 1 }
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

/** Вход на линию: строка из очереди получает номер, полный остаток и время входа. */
function enterLine(row: HangerData, now: Date): RunHanger {
  return {
    number: Number(row.number),
    remainingTime: LINE_SECONDS,
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
 * Старт прогона: круг перемешан и пронумерован, ванна заполнена целиком —
 * витрина открывается на середине прогона, а не на его первой секунде.
 * Подвесы разведены по остаткам так, как если бы вход шёл раз в
 * ``EXIT_INTERVAL_SECONDS``: первый подвес из круга уже сошёл и стоит в ванне
 * схода, последний только что встал в ванну. Номера вдоль маршрута растут.
 */
export function startRun(rows: HangerData[], now: Date, random: () => number = Math.random): RunState {
  if (rows.length === 0) return emptyRun()

  // Время входа витринной строки сохраняется: пока подвес в очереди, видно время,
  // которым его нарисовали; при входе на линию enterLine переставит своё.
  let pool = shuffle(rows, random).map((row, index) => ({ ...row, number: String(index + 1) }))
  let cursor = 0
  let nextNumber = pool.length + 1

  // Круг может быть короче ванны: тогда он перемешивается и нумеруется заново,
  // иначе в ванне просто некому стоять, а очередь загрузки пустеет.
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

  // Подвес, который уже сошёл: карточка «Вышел» сразу на месте, и в выгрузке
  // есть строка, чтобы витрина не открылась пустой. Он забирает первый номер
  // круга — он дальше всех прошёл по линии.
  const atExit: ExitedHanger = { ...takeNext(now), remainingTime: 0, stoodSeconds: 0 }

  // Ванна заполнена целиком. Места перечислены от того, кто уйдёт последним, к
  // тому кто уйдёт первым, поэтому на каждом шаге остаток меньше на
  // EXIT_INTERVAL_SECONDS, карточки идут лесенкой, а нулевой элемент `line` —
  // это ванна FORECAST_BATHS[0]. Заполняем с конца: номера вдоль линии растут.
  const line: RunHanger[] = new Array(FORECAST_BATHS.length)
  for (let bathIndex = FORECAST_BATHS.length - 1; bathIndex >= 0; bathIndex -= 1) {
    line[bathIndex] = {
      ...takeNext(now),
      remainingTime: LINE_SECONDS - bathIndex * EXIT_INTERVAL_SECONDS,
    }
  }

  return {
    line,
    atExit,
    unloaded: [toUnloadedRow(atExit, now)],
    pool,
    cursor,
    nextNumber,
  }
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
 * Секундный тик. Остатки тают у всех; на нуле подвес уходит в ванну схода и в
 * выгрузку, а в ванну встаёт следующий из очереди загрузки. Выход получается
 * раз в ``EXIT_INTERVAL_SECONDS`` — чаще при одной ванне не выйдет.
 *
 * Подвес в ванне схода никуда не идёт, но время на карточке «Вышел» идёт
 * вверх: карточка показывает, сколько он там простоял, а не остаток до чего-то.
 */
export function advanceRun(
  state: RunState,
  now: Date,
  unloadLimit: number,
  random: () => number = Math.random,
): RunState {
  if (state.line.length === 0) return state

  const line = state.line.map(hanger => ({
    ...hanger,
    remainingTime: Math.max(0, hanger.remainingTime - 1),
  }))
  const atExit = state.atExit
    ? { ...state.atExit, stoodSeconds: state.atExit.stoodSeconds + 1 }
    : null

  const leaving = line[line.length - 1]
  if (leaving.remainingTime > 0) {
    return { ...state, line, atExit }
  }

  let pool = state.pool
  let cursor = state.cursor
  let nextNumber = state.nextNumber

  if (cursor >= pool.length) {
    pool = renumberPool(shuffle(pool, random), nextNumber)
    nextNumber += pool.length
    cursor = 0
  }

  const entered = enterLine(pool[cursor], now)
  cursor += 1

  return {
    line: [entered, ...line.slice(0, -1)],
    atExit: { ...leaving, remainingTime: 0, stoodSeconds: 0 },
    // Свежая строка сверху, прежние остаются под ней: по убыванию номера, как
    // на линии, где книга дописывается сверху.
    unloaded: [toUnloadedRow(leaving, now), ...state.unloaded].slice(0, Math.max(0, unloadLimit)),
    pool,
    cursor,
    nextNumber,
  }
}
