// Тестовый прогон витрины: подвесы идут по ваннам конвейером и по таймеру
// сходят с линии. Единственный владелец правил прогона: страница только рисует
// то, что отсюда пришло.
//
// Поведение повторяет линию: подвес входит в ванну 30 из очереди загрузки,
// проходит 31, 32, 33 и сходит с линии через ванну 34. Номера вдоль маршрута
// растут, как в книге учёта: кто встал раньше, тот дальше по линии и сойдёт
// первым. Очередь и таблицы показывают строки свежими сверху, по убыванию
// номера, — так же, как на линии.
//
// Темп: подвес лежит в ванне DWELL_SECONDS, а на линию заходит каждые
// ENTRY_INTERVAL_SECONDS, поэтому в ванне стоит сразу несколько подвесов —
// ровно столько, сколько помещается в окно обработки. Отсюда два следствия:
// выгрузка получает строку каждые ENTRY_INTERVAL_SECONDS, а карточки ванн
// встают лесенкой — каждая показывает свой срез одних и тех же двадцати
// секунд, поэтому подвесы в них не ходят вразнобой.

import { formatLocalized } from '@/lib/domain/time'
import type { HangerData } from '@/types/dashboard'

/** Ванны, у которых на дашборде есть карточка прогноза: позиция в массиве — номер ванны. */
export const FORECAST_BATHS = [30, 31, 32, 33]

/** Ванна схода: подвес, дошедший до неё, уходит с линии. */
export const CONTROL_BATH = 34

/** Ванны линии по порядку движения подвеса: позиция в массиве — ванна. */
export const LINE_BATHS = [...FORECAST_BATHS, CONTROL_BATH]

/** Сколько подвес лежит в ванне до перехода в следующую. */
export const DWELL_SECONDS = 20

/** Секунд между входами подвесов на линию: темп, с которым ванны поворачиваются. */
export const ENTRY_INTERVAL_SECONDS = 5

/** Подвесов в ванне при таком темпе: длина очереди ванны. */
export const HANGERS_PER_BATH = Math.ceil(DWELL_SECONDS / ENTRY_INTERVAL_SECONDS)

export interface RunHanger {
  /** Сквозной номер подвеса: с 1 до сброса прогона. */
  number: number
  /** Остаток до перехода в следующую ванну, секунды. */
  remainingTime: number
  /** Строка витрины с проставленным временем входа на линию. */
  row: HangerData
}

export interface RunState {
  /**
   * Очереди ванн линии: индекс — ванна из ``LINE_BATHS``, внутри — подвесы от
   * головы (уходит из ванны первым) к хвосту (встал последним). В каждой ванне
   * ровно ``HANGERS_PER_BATH`` подвесов: линия встала на темп входа.
   */
  baths: RunHanger[][]
  /** Выгруженные подвесы: свежие сверху, по убыванию номера. */
  unloaded: HangerData[]
  /** Круг профилей: очередь загрузки и источник номеров на следующий круг. */
  pool: HangerData[]
  /** Позиция в круге: откуда берём следующего подвеса. */
  cursor: number
  /** Следующий сквозной номер подвеса. */
  nextNumber: number
  /** Секунд с последнего входа подвеса на линию. */
  sinceEntry: number
}

export function emptyRun(): RunState {
  return { baths: [], unloaded: [], pool: [], cursor: 0, nextNumber: 1, sinceEntry: 0 }
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
 * Старт прогона: круг перемешан и пронумерован, линия заполнена целиком —
 * витрина открывается на середине прогона, а не на его первой секунде.
 * Подвесы разведены по ваннам так, как если бы строка входа шла раз в
 * ``ENTRY_INTERVAL_SECONDS``: ближайший к сходу подвес встал в ванну 30 раньше
 * всех, и номера вдоль линии растут.
 */
export function startRun(rows: HangerData[], now: Date, random: () => number = Math.random): RunState {
  if (rows.length === 0) return emptyRun()

  // Время входа витринной строки сохраняется: пока подвес в очереди, видно время,
  // которым его нарисовали; при входе в ванну enterLine переставит своё.
  let pool = shuffle(rows, random).map((row, index) => ({ ...row, number: String(index + 1) }))
  let cursor = 0
  let nextNumber = pool.length + 1

  // Круг может быть короче линии: тогда он перемешивается и нумеруется заново,
  // иначе в ваннах просто некому стоять, а очередь загрузки пустеет.
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

  const lineSize = LINE_BATHS.length * HANGERS_PER_BATH
  const lineSeconds = LINE_BATHS.length * DWELL_SECONDS
  const lastBathIndex = LINE_BATHS.length - 1
  const baths: RunHanger[][] = LINE_BATHS.map(() => [])

  for (let step = 0; step < lineSize; step += 1) {
    // Подвес, который сойдёт с линии первым, стоит дальше всех по маршруту;
    // шаг идёт от схода к загрузке, поэтому номера вдоль линии растут.
    const bathIndex = lastBathIndex - Math.floor(step / HANGERS_PER_BATH)
    const secondsToExit = (step + 1) * ENTRY_INTERVAL_SECONDS
    const entryAt = new Date(now.getTime() + (secondsToExit - lineSeconds) * 1000)
    const hanger = takeNext(entryAt)

    baths[bathIndex].push({
      ...hanger,
      remainingTime: secondsToExit - (lastBathIndex - bathIndex) * DWELL_SECONDS,
    })
  }

  return { baths, unloaded: [], pool, cursor, nextNumber, sinceEntry: 0 }
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
 * Подвесы, которые рисуют карточки ванн, в порядке движения по линии.
 *
 * В ванне стоит несколько подвесов, поэтому карточка показывает не одну и ту же
 * позицию очереди у всех ванн, а свою: 30 — головного подвеса, 31 — второго,
 * 32 — третьего, 33 — четвёртого. Остатки у карточек расходятся шагом
 * ENTRY_INTERVAL_SECONDS, и витрина показывает лесенку 5, 10, 15, 20 секунд
 * вместо пяти одинаковых таймеров. Ванна схода показывает голову своей
 * очереди: этот подвес следующим сойдёт с линии.
 */
export function cardHangers(state: RunState): (RunHanger | null)[] {
  const lastBathIndex = LINE_BATHS.length - 1

  return state.baths.map((queue, bathIndex) => queue[bathIndex === lastBathIndex ? 0 : bathIndex] ?? null)
}

/**
 * Секундный тик. Остатки тают; дошедшие до нуля переходят в следующую ванну,
 * сошедший с ванны схода уходит в выгрузку, а в ванну 30 встаёт очередной из
 * очереди загрузки — раз в ``ENTRY_INTERVAL_SECONDS``.
 */
export function advanceRun(
  state: RunState,
  now: Date,
  unloadLimit: number,
  random: () => number = Math.random,
): RunState {
  if (state.baths.length === 0) return state

  const sinceEntry = state.sinceEntry + 1
  const entersNow = sinceEntry >= ENTRY_INTERVAL_SECONDS
  const lastBathIndex = LINE_BATHS.length - 1

  const baths = state.baths.map(queue =>
    queue.map(hanger => ({ ...hanger, remainingTime: Math.max(0, hanger.remainingTime - 1) })),
  )

  // Ванны поворачиваются от схода к загрузке: подвес, дошедший до нуля в ванне
  // i+1, должен освободить место раньше, чем придёт подвес из ванны i.
  const unloadedNow: RunHanger[] = []
  for (let bathIndex = lastBathIndex; bathIndex >= 0; bathIndex -= 1) {
    const queue = baths[bathIndex]
    while (queue.length > 0 && queue[0].remainingTime <= 0) {
      const [hanger] = queue.splice(0, 1)
      if (bathIndex === lastBathIndex) {
        unloadedNow.push(hanger)
      } else {
        // Встал последним в ванне, в которую только что ушёл головной, — в хвост.
        baths[bathIndex + 1].push({ ...hanger, remainingTime: DWELL_SECONDS })
      }
    }
  }

  let pool = state.pool
  let cursor = state.cursor
  let nextNumber = state.nextNumber

  if (entersNow) {
    if (cursor >= pool.length) {
      pool = renumberPool(shuffle(pool, random), nextNumber)
      nextNumber += pool.length
      cursor = 0
    }
    const hanger = enterLine(pool[cursor], now)
    cursor += 1
    baths[0].push(hanger)
  }

  return {
    baths,
    // Свежая строка сверху, прежние остаются под ней: по убыванию номера, как
    // на линии, где книга дописывается сверху.
    unloaded: [...unloadedNow.map(hanger => toUnloadedRow(hanger, now)), ...state.unloaded]
      .slice(0, Math.max(0, unloadLimit)),
    pool,
    cursor,
    nextNumber,
    sinceEntry: entersNow ? sinceEntry - ENTRY_INTERVAL_SECONDS : sinceEntry,
  }
}