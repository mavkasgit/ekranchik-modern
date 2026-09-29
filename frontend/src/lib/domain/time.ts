// Время: три разных правила под одним прежним именем `formatTime`.
// Явные имена вместо двусмысленного: clock — HH:MM:SS → HH:MM,
// duration — секунды → m:ss, localized — метка времени → локальное время.

export function formatClock(time: string | null | undefined): string {
  if (!time) return '—'
  const parts = time.split(':')
  if (parts.length >= 2) return `${parts[0]}:${parts[1]}`
  return time
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function formatLocalized(
  value: string | number | Date | null | undefined,
  locale = 'ru',
): string {
  if (value === null || value === undefined || value === '') return '—'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString(locale)
}

// Сколько секунд подвесу осталось до схода с линии, если он стоит в ванне
// `fromBath`. Подвес выходит не из своей ванны, а пройдя все ванны до
// контрольной, поэтому время складывается по всей цепочке. Считать только
// остаток своей ванны нельзя: тогда выход из 30-й, 31-й, 32-й и 33-й
// получался одновременным, а подвесы шли не по порядку.
//
// `elapsedSeconds` — сколько секунд прошло с момента, когда пришли эти
// данные. Остаток обработки в каждой ванне уменьшается раз в секунду, а
// сообщения линии приходят раз в 2 с, поэтому между ними секунды надо
// домерить на клиенте: иначе карточка стоит ступенями и время в ней не
// идёт. Ванна, остаток которой уже кончился, даёт ноль, а не минус.
//
// `d_time` у ванны, счётчик которой перешёл сутки, уходит в минус — такое
// значение нельзя прибавлять, поэтому отрицательные обнуляются.
export function dwellChainToExit(
  baths: ReadonlyArray<{ bath_number: number; d_time?: number | null }>,
  fromBath: number,
  controlBath: number,
  elapsedSeconds: number = 0,
): number {
  const elapsed = Math.max(0, elapsedSeconds)
  let total = 0
  for (let bath = fromBath; bath <= controlBath; bath += 1) {
    const found = baths.find((b) => b.bath_number === bath)
    total += Math.max(0, (found?.d_time ?? 0) - elapsed)
  }
  return total
}
