// Цвет подвеса: имя цвета из книги учёта → каноническое написание, hex, аббревиатура
// и стиль ячейки. Единственный владелец правила: раньше жило копиями в Dashboard и
// BathForecastTable.

interface ColorSpec {
  /** Каноническое написание: его показываем и по нему узнаём любой вариант из книги учёта. */
  name: string
  hex: string
  abbreviation: string
}

/** Справочник цветов: один пункт на цвет, «Rose Bronze» и «RoseBronze» — один. */
const COLOR_CATALOG: ColorSpec[] = [
  { name: 'серебро', hex: '#C0C0C0', abbreviation: 'сер' },
  { name: 'черный', hex: '#1C1C1C', abbreviation: 'чер' },
  { name: 'золото', hex: '#FFD700', abbreviation: 'зол' },
  { name: 'шампань', hex: '#F7E7CE', abbreviation: 'шам' },
  { name: 'титан', hex: '#878681', abbreviation: 'тит' },
  { name: 'бронза', hex: '#8B5A2B', abbreviation: 'брз' },
  { name: 'медь', hex: '#CD5C5C', abbreviation: 'мед' },
  { name: 'растрав', hex: '#D3D3D3', abbreviation: 'рст' },
  { name: 'Rose Gold', hex: '#B76E79', abbreviation: 'RG' },
  { name: 'Rose Bronze', hex: '#800020', abbreviation: 'RB' },
]

const UNKNOWN_COLOR_HEX = '#9CA3AF'

/** Ключ сопоставления: регистр, пробелы, дефисы и подчёркивания не различают цвета. */
function normalizeColorName(colorName: string): string {
  return colorName.toLowerCase().replace(/[\s\-_]/g, '')
}

/** Один пункт на цвет: «Rose Bronze» и «RoseBronze» — один и тот же цвет, не два. */
const COLORS: ColorSpec[] = COLOR_CATALOG.filter((color, index) => {
  const key = normalizeColorName(color.name)
  const firstIndex = COLOR_CATALOG.findIndex((other) => normalizeColorName(other.name) === key)
  return firstIndex === index
})

/**
 * Ближайший по названию цвет. Сначала точное совпадение. Затем — только уточнения
 * записанного значения: «серебро матовое» содержит «серебро» и остаётся серебром.
 * Обратного вхождения нет намеренно: иначе «Bronze» (чужое название) подхватил бы
 * «Rose Bronze» и на экране оператора появился бы цвет, которого в книге учёта нет.
 */
function matchColor(colorName: string): ColorSpec | undefined {
  const key = normalizeColorName(colorName)
  if (!key) return undefined

  for (const color of COLORS) {
    if (normalizeColorName(color.name) === key) return color
  }

  let best: ColorSpec | undefined
  for (const color of COLORS) {
    const name = normalizeColorName(color.name)
    if (!key.includes(name)) continue
    if (!best || name.length > normalizeColorName(best.name).length) best = color
  }
  return best
}

/**
 * Название цвета для показа. Записи, где цвет уже записан в книге учёта иначе
 * («RoseBronze», «rose bronze»), показываем канонически; неизвестные цвета — как есть.
 */
export function colorName(colorName: string): string {
  return COLORS.find((color) => normalizeColorName(color.name) === normalizeColorName(colorName))?.name
    ?? colorName.trim()
}

export function colorHex(colorName: string): string {
  return matchColor(colorName)?.hex ?? UNKNOWN_COLOR_HEX
}

export function colorAbbreviation(colorName: string): string {
  return matchColor(colorName)?.abbreviation ?? (colorName.toLowerCase().trim().slice(0, 4) || '—')
}

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '').trim()
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `rgba(156, 163, 175, ${alpha})`
  }

  const r = Number.parseInt(normalized.slice(0, 2), 16)
  const g = Number.parseInt(normalized.slice(2, 4), 16)
  const b = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function colorCellStyle(hex: string) {
  return {
    background: `linear-gradient(135deg, ${hexToRgba(hex, 0.6)} 0%, ${hexToRgba(hex, 0.4)} 100%)`,
    boxShadow: `inset 0 0 0 1px ${hexToRgba(hex, 0.52)}`,
  }
}
