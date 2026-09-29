import { describe, expect, it } from 'vitest'
import { dwellChainToExit } from './time'

const CONTROL_BATH = 34

const baths = [
  { bath_number: 30, d_time: 250 },
  { bath_number: 31, d_time: 1896 },
  { bath_number: 32, d_time: 1158 },
  { bath_number: 33, d_time: 1800 },
  { bath_number: 34, d_time: 0 },
]

describe('dwellChainToExit', () => {
  it('складывает время своей ванны и всех последующих до схода', () => {
    // Подвес в 30-й выйдет не через остаток своей ванны (250 с), а пройдя
    // 30→31→32→33→34. Считать только свою ванну нельзя: тогда выход из
    // 30-й, 31-й и 32-й получался одновременным.
    expect(dwellChainToExit(baths, 30, CONTROL_BATH)).toBe(250 + 1896 + 1158 + 1800)
    expect(dwellChainToExit(baths, 32, CONTROL_BATH)).toBe(1158 + 1800)
  })

  it('даёт подвесам выходить по порядку: чем дальше ванна, тем раньше сход', () => {
    const from30 = dwellChainToExit(baths, 30, CONTROL_BATH)
    const from31 = dwellChainToExit(baths, 31, CONTROL_BATH)
    const from32 = dwellChainToExit(baths, 32, CONTROL_BATH)
    const from33 = dwellChainToExit(baths, 33, CONTROL_BATH)

    expect(from30).toBeGreaterThan(from31)
    expect(from31).toBeGreaterThan(from32)
    expect(from32).toBeGreaterThan(from33)
  })

  it('в сходе показывает ноль — подвес уже на выходе', () => {
    expect(dwellChainToExit(baths, CONTROL_BATH, CONTROL_BATH)).toBe(0)
  })

  it('не прибавляет отрицательный d_time ванны, перешедшей сутки', () => {
    const wrapped = [
      { bath_number: 33, d_time: 1800 },
      { bath_number: 34, d_time: -448 },
    ]
    expect(dwellChainToExit(wrapped, 33, CONTROL_BATH)).toBe(1800)
  })

  it('ванна без данных не ломает расчёт', () => {
    expect(dwellChainToExit([], 30, CONTROL_BATH)).toBe(0)
    expect(dwellChainToExit(baths, 30, 30)).toBe(250)
  })
})
