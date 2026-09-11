// Ключ подвеса: номер подвеса из Excel/OPC UA → строковый ключ для сопоставления.
// Одна форма на весь фронт: раньше `toHangerKey` в Dashboard и `normalizeHangerKey`
// в BathForecastTable считали её двумя независимыми копиями.

export function hangerKey(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return ''
  const raw = String(value).trim()
  if (!raw) return ''

  const numeric = Number(raw.replace(',', '.'))
  if (Number.isFinite(numeric)) {
    return String(Math.trunc(numeric))
  }

  return raw
}
