// Строки витрины из каталога профилей. Три режима дашборда берут строки отсюда:
// профили случайные из тех, у кого есть фото, — так же, как их берёт боевая
// выдача. Номер подвеса и время ставит прогон, когда подвес встаёт на линию.

import { COLOR_CATALOG } from '@/lib/domain/color'
import type { HangerData } from '@/types/dashboard'
import type { Profile } from '@/types/profile'

/** Режим показа витрины: ни одного — боевые данные. */
export type TestMode = 'catalog' | 'colors' | 'sim'

/** Клиент, которым помечены витринные строки: на боевой линии такого клиента нет. */
const TEST_CLIENT = 'Тест Каталога'
const TEST_MATERIAL = 'Тест'
const NO_VALUE = '—'

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

/** Профиль годится в строку дашборда, если у него есть фото — того же предиката, что и на боевом пути. */
function hasPhoto(profile: Profile): boolean {
  return Boolean(profile.photo_thumb)
}

function toRow(profile: Profile, color: string, number: number): HangerData {
  return {
    // Номер подвеса есть уже у строки загрузки. В режиме симуляции его
    // переставит прогон, в витринных режимах он остаётся таким.
    number: String(number),
    date: new Date().toLocaleDateString('ru-RU'),
    time: '',
    client: TEST_CLIENT,
    profile: profile.name,
    canonical_name: profile.name,
    profiles_info: [],
    profile_photo_thumb: profile.photo_thumb ?? undefined,
    profile_photo_full: profile.photo_full ?? undefined,
    color,
    lamels_qty: profile.quantity_per_hanger ?? 0,
    kpz_number: NO_VALUE,
    material_type: TEST_MATERIAL,
  }
}

/**
 * Строки витрины. `colors` — по одной на каждый цвет справочника, остальные
 * режимы — весь круг профилей с фото в случайном порядке, и цвет каждой строки
 * тоже случайный из справочника: в каталоге цвета нет, он живёт в книге учёта.
 */
export function buildTestRows(
  profiles: Profile[],
  mode: TestMode,
  random: () => number = Math.random,
): HangerData[] {
  const withPhoto = profiles.filter(hasPhoto)
  if (withPhoto.length === 0) return []

  const ordered = shuffle(withPhoto, random)
  if (mode === 'colors') {
    return COLOR_CATALOG.map((color, index) => {
      const profile = ordered[index % ordered.length]
      return toRow(profile, color.name, index + 1)
    })
  }

  return ordered.map((profile, index) => (
    toRow(profile, COLOR_CATALOG[Math.floor(random() * COLOR_CATALOG.length)].name, index + 1)
  ))
}
