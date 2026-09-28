import { describe, expect, it } from 'vitest'
import { colorAbbreviation, colorHex, colorName } from './color'

describe('colorName', () => {
  it('показывает один канонический пункт для всех написаний цвета из книги учёта', () => {
    for (const written of ['Rose Bronze', 'RoseBronze', 'rose bronze', 'ROSE-BRONZE', 'rose_bronze', '  RoseBronze  ']) {
      expect(colorName(written)).toBe('Rose Bronze')
    }
  })

  it('различает Rose Bronze и Rose Gold', () => {
    expect(colorName('RoseGold')).toBe('Rose Gold')
    expect(colorName('Rose Bronze')).not.toBe(colorName('Rose Gold'))
  })

  it('не выдумывает название для цвета, которого нет в справочнике', () => {
    expect(colorName('RAL 9016')).toBe('RAL 9016')
    expect(colorName('  Не указан  ')).toBe('Не указан')
  })
})

describe('colorHex / colorAbbreviation', () => {
  it('один и тот же цвет с любым написанием даёт один hex и одну аббревиатуру', () => {
    expect(colorHex('RoseBronze')).toBe(colorHex('Rose Bronze'))
    expect(colorAbbreviation('RoseBronze')).toBe('RB')
    expect(colorAbbreviation('Rose Bronze')).toBe('RB')
  })

  it('подбирает цвет по названию с уточнением («серебро матовое»)', () => {
    expect(colorHex('серебро матовое')).toBe(colorHex('серебро'))
  })

  it('не подставляет цвет из чужого названия', () => {
    // «Bronze» — не «Rose Bronze»: на экране не должно появляться то, чего в книге учёта нет.
    expect(colorHex('Bronze')).not.toBe(colorHex('Rose Bronze'))
    expect(colorName('Bronze')).toBe('Bronze')
    expect(colorHex('Gold')).not.toBe(colorHex('Rose Gold'))
  })
})
