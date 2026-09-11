// Цвет подвеса: имя цвета из Excel → hex, аббревиатура и стиль ячейки.
// Единственный владелец правила: раньше жило копиями в Dashboard и BathForecastTable.

const COLOR_HEX: Record<string, string> = {
  'серебро': '#C0C0C0',
  'черный': '#1C1C1C',
  'золото': '#FFD700',
  'шампань': '#F7E7CE',
  'титан': '#878681',
  'бронза': '#8B5A2B',
  'медь': '#CD5C5C',
  'растрав': '#D3D3D3',
  'rosegold': '#B76E79',
  'rosebronze': '#800020',
}

const COLOR_ABBREVIATION: Record<string, string> = {
  'серебро': 'сер',
  'черный': 'чер',
  'золото': 'зол',
  'шампань': 'шам',
  'титан': 'тит',
  'бронза': 'брз',
  'медь': 'мед',
  'растрав': 'рст',
  'rosegold': 'RG',
  'rosebronze': 'RB',
}

const UNKNOWN_COLOR_HEX = '#9CA3AF'

function normalizeColorName(colorName: string): string {
  return colorName.toLowerCase().replace(/[\s\-_]/g, '')
}

function matchColor(map: Record<string, string>, colorName: string): string | undefined {
  const name = normalizeColorName(colorName)

  for (const [key, value] of Object.entries(map)) {
    if (normalizeColorName(key) === name) return value
  }

  for (const [key, value] of Object.entries(map)) {
    const normKey = normalizeColorName(key)
    if (name.includes(normKey) || normKey.includes(name)) return value
  }

  return undefined
}

export function colorHex(colorName: string): string {
  return matchColor(COLOR_HEX, colorName) ?? UNKNOWN_COLOR_HEX
}

export function colorAbbreviation(colorName: string): string {
  return matchColor(COLOR_ABBREVIATION, colorName) ?? (colorName.toLowerCase().trim().slice(0, 4) || '—')
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
