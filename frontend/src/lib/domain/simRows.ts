// Строки витрины из каталога профилей. Три режима дашборда берут строки отсюда:
// профили случайные из всего каталога, — так же, как их берёт боевая выдача:
// строка книги есть независимо от того, есть ли фото у профиля, а пустая ячейка
// «Фото» у такой строки — обычное дело. Номер подвеса и время ставит прогон,
// когда подвес встаёт на линию.

import { COLOR_CATALOG } from '@/lib/domain/color'
import { formatLocalized } from '@/lib/domain/time'
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

/**
 * Строка витрины: профиль, у которого нет фото, — обычная строка, а не повод
 * отбрасывать профиль. Боевая выдача так же оставляет строку книги и просто
 * оставляет ячейку «Фото» пустой, поэтому витрина ведёт себя так же.
 */

function toRow(profile: Profile, color: string, number: number, now: Date): HangerData {
  return {
    // Номер подвеса есть уже у строки загрузки. В режиме симуляции номер и
    // время переставит прогон, когда подвес действительно встанет в ванну,
    // в витринных режимах остаются те, что проставлены здесь.
    number: String(number),
    // Дата выводится как есть, без форматирования: на линии в таблице загрузки
    // стоит двухзначный год, как в книге учёта.
    date: new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }).format(now),
    time: formatLocalized(now, 'ru-RU'),
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
 * режимы — весь каталог в случайном порядке, и цвет каждой строки тоже
 * случайный из справочника: в каталоге цвета нет, он живёт в книге учёта.
 */
export function buildTestRows(
  profiles: Profile[],
  mode: TestMode,
  random: () => number = Math.random,
): HangerData[] {
  const ordered = shuffle(profiles, random)
  if (ordered.length === 0) return []

  // Один момент на всю витрину: время входа у строк общее, а в режиме симуляции
  // прогон переставит его каждому подвесу, когда тот встанет в ванну.
  const now = new Date()
  if (mode === 'colors') {
    return COLOR_CATALOG.map((color, index) => {
      const profile = ordered[index % ordered.length]
      return toRow(profile, color.name, index + 1, now)
    })
  }

  return ordered.map((profile, index) => (
    toRow(profile, COLOR_CATALOG[Math.floor(random() * COLOR_CATALOG.length)].name, index + 1, now)
  ))
}
