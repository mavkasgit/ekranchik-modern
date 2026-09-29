import { describe, expect, it } from 'vitest'
import { COLOR_CATALOG } from './color'
import { buildTestRows } from './simRows'
import type { Profile } from '@/types/profile'

function catalogProfile(index: number, photo: string | null = `images/p${index}-thumb.jpg`): Profile {
  return {
    id: index,
    name: `1010${index}`,
    quantity_per_hanger: 12,
    length: 6000,
    notes: null,
    photo_thumb: photo,
    photo_full: photo ? photo.replace('-thumb', '') : null,
    usage_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

const CATALOG: Profile[] = Array.from({ length: 12 }, (_, index) => catalogProfile(index))

/** Детерминированный генератор: выбор профилей проверяется, а не отдаётся на волю Math.random. */
function seededRandom(seed: number): () => number {
  let value = seed
  return () => {
    value = (value * 9301 + 49297) % 233280
    return value / 233280
  }
}

describe('buildTestRows', () => {
  it('берёт только профили, у которых есть фото для строки дашборда', () => {
    const withGaps = [
      catalogProfile(1),
      catalogProfile(2, null),
      catalogProfile(3, ''),
      catalogProfile(4),
    ]

    const rows = buildTestRows(withGaps, 'catalog', seededRandom(7))

    expect(rows.map(row => row.profile).sort()).toEqual(['10101', '10104'])
  })

  it('в режиме каталога показывает каждый профиль с фото', () => {
    const rows = buildTestRows(CATALOG, 'catalog', seededRandom(7))

    expect(rows).toHaveLength(CATALOG.length)
    expect(rows.map(row => row.profile).sort()).toEqual(CATALOG.map(profile => profile.name).sort())
  })

  it('в режиме симуляции берёт тот же круг, но в случайном порядке', () => {
    const rows = buildTestRows(CATALOG, 'sim', seededRandom(7))

    expect(rows.map(row => row.profile).sort()).toEqual(CATALOG.map(profile => profile.name).sort())
    expect(rows.map(row => row.profile)).not.toEqual(CATALOG.map(profile => profile.name))
  })

  it('в режиме цветов даёт ровно одну строку на каждый цвет справочника', () => {
    const rows = buildTestRows(CATALOG, 'colors', seededRandom(7))

    expect(rows.map(row => row.color)).toEqual(COLOR_CATALOG.map(color => color.name))
  })

  it('в режиме цветов профили под цветами разные, а не один на все строки', () => {
    const rows = buildTestRows(CATALOG, 'colors', seededRandom(7))

    expect(new Set(rows.map(row => row.profile)).size).toBe(COLOR_CATALOG.length)
  })

  it('время пустое, а номер подвеса уже проставлен — как у строки загрузки', () => {
    const rows = buildTestRows(CATALOG, 'sim', seededRandom(7))

    expect(rows.every(row => row.time === '')).toBe(true)
    expect(rows.map(row => row.number)).toEqual(rows.map((_, index) => String(index + 1)))
  })

  it('в режиме цветов строки пронумерованы подряд', () => {
    const rows = buildTestRows(CATALOG, 'colors', seededRandom(7))

    expect(rows.map(row => row.number)).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'])
  })

  it('строка остаётся опознаваемо витринной, а не боевой', () => {
    const rows = buildTestRows(CATALOG, 'sim', seededRandom(7))

    expect(rows.every(row => row.client === 'Тест Каталога')).toBe(true)
    expect(rows.every(row => row.material_type === 'Тест')).toBe(true)
  })

  it('фото профиля доезжает до строки в обоих размерах', () => {
    const rows = buildTestRows(CATALOG, 'sim', seededRandom(7))

    expect(rows.every(row => row.profile_photo_thumb?.includes('-thumb'))).toBe(true)
    expect(rows.every(row => row.profile_photo_full && !row.profile_photo_full.includes('-thumb'))).toBe(true)
  })

  it('каталогу без профилей с фото нечего показывать в любом режиме', () => {
    const withoutPhoto = [catalogProfile(1, null)]

    expect(buildTestRows(withoutPhoto, 'sim', seededRandom(7))).toEqual([])
    expect(buildTestRows(withoutPhoto, 'colors', seededRandom(7))).toEqual([])
    expect(buildTestRows(withoutPhoto, 'catalog', seededRandom(7))).toEqual([])
  })
})
