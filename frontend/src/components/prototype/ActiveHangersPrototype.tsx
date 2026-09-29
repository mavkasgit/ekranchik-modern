// ПРОТОТИП — выбросить после выбора варианта.
//
// Вопрос: как ужать блок «Сейчас на линии», чтобы подвесов было видно
// много, а не по одному на 110 пикселей. Три варианта переключаются
// параметром ?variant=A|B|C прямо на /opcua, вкладка «Hanger Tracking».
//
// Показаны поля, которые сервер отдаёт в /api/opcua/hangers/active: номер,
// текущая ванна, путь, номер прохода и момент первого замера — по нему
// считается, сколько подвес уже в линии.

import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { formatInLine, passClock } from '@/lib/domain/journal'

export interface PrototypeHanger {
  number: number
  current_bath: number | string | null
  baths_visited: (number | string)[]
  cycle_id: number | null
  line_entry_at: string | null
  entry_bath: number | null
  first_seen_source: string
}

const VARIANTS = {
  A: 'Плотная таблица',
  B: 'Плитка в 3 колонки',
  C: 'Лента чипов',
} as const

type VariantKey = keyof typeof VARIANTS

const KEYS = Object.keys(VARIANTS) as VariantKey[]

/** Номер подвеса с ведущими нулями: `#045`. */
function hangerLabel(number: number): string {
  return `#${String(number).padStart(3, '0')}`
}

/** Текущая ванна числом либо прочерк, когда неизвестна. */
function bathLabel(bath: number | string | null): string {
  return bath === null || bath === '' ? '—' : `#${bath}`
}

/** Путь по ваннам: `3 → 4 → 34`. */
function pathLabel(path: (number | string)[]): string {
  return path.length > 0 ? path.map(bath => bathLabel(bath)).join(' → ') : '—'
}

/** Вариант A — плотная таблица: одна строка на подвес. */
function VariantA({ hangers, now }: { hangers: PrototypeHanger[]; now: Date }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="py-1 px-2 font-medium">Подвес</th>
            <th className="py-1 px-2 font-medium">Вход на линию</th>
            <th className="py-1 px-2 font-medium text-right">В линии</th>
            <th className="py-1 px-2 font-medium">Ванна</th>
            <th className="py-1 px-2 font-medium">Путь</th>
            <th className="py-1 px-2 font-medium text-right">Ванн</th>
          </tr>
        </thead>
        <tbody>
          {hangers.map(hanger => (
            <tr
              key={hanger.number}
              className="border-b border-gray-100 odd:bg-green-50/60 hover:bg-green-50"
            >
              <td className="py-1 px-2 font-mono text-gray-900 whitespace-nowrap">
                {hanger.cycle_id != null && (
                  <span className="mr-1 text-[10px] font-normal text-gray-400">
                    ID {hanger.cycle_id}
                  </span>
                )}
                <span className="font-semibold">{hangerLabel(hanger.number)}</span>
              </td>
              <td className="py-1 px-2 font-mono text-gray-700 whitespace-nowrap">
                {passClock(hanger.line_entry_at)}
                {hanger.entry_bath != null && (
                  <span className="ml-1 text-[10px] text-gray-400">
                    ванна {hanger.entry_bath}
                  </span>
                )}
              </td>
              <td className="py-1 px-2 text-right font-mono text-gray-700 whitespace-nowrap">
                {formatInLine(hanger.line_entry_at, now, hanger.first_seen_source)}
              </td>
              <td className="py-1 px-2 font-mono text-gray-700">
                {bathLabel(hanger.current_bath)}
              </td>
              <td className="py-1 px-2 font-mono text-gray-500 truncate max-w-[280px]">
                {pathLabel(hanger.baths_visited ?? [])}
              </td>
              <td className="py-1 px-2 text-right font-mono text-gray-500">
                {hanger.baths_visited?.length ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Вариант B — плитка в три колонки: номер и ванна крупно, путь мелко. */
function VariantB({ hangers, now }: { hangers: PrototypeHanger[]; now: Date }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {hangers.map(hanger => (
        <div key={hanger.number} className="border border-green-200 bg-green-50 rounded-md px-3 py-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-mono font-semibold text-sm text-gray-900">
              {hangerLabel(hanger.number)}
            </span>
            <span className="text-xs text-green-700">
              ванна {bathLabel(hanger.current_bath)}
            </span>
          </div>
          <div className="text-[11px] text-gray-500 font-mono truncate" title={pathLabel(hanger.baths_visited ?? [])}>
            {passClock(hanger.line_entry_at)} · {formatInLine(hanger.line_entry_at, now, hanger.first_seen_source)} · {pathLabel(hanger.baths_visited ?? [])}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Вариант C — лента чипов, перенос по строкам. */
function VariantC({ hangers, now }: { hangers: PrototypeHanger[]; now: Date }) {
  return (
    <div className="flex flex-wrap gap-1">
      {hangers.map(hanger => (
        <span
          key={hanger.number}
          title={`путь: ${pathLabel(hanger.baths_visited ?? [])}`}
          className="inline-flex items-center gap-1.5 border border-green-200 bg-green-50 rounded-full pl-2 pr-2.5 py-0.5 text-xs text-gray-800 font-mono max-w-[280px]"
        >
          <span className="font-semibold">{hangerLabel(hanger.number)}</span>
          <span className="text-green-700">ванна {bathLabel(hanger.current_bath)}</span>
          <span className="text-gray-500">
            {passClock(hanger.line_entry_at)} · {formatInLine(hanger.line_entry_at, now, hanger.first_seen_source)}
          </span>
          {hanger.baths_visited && hanger.baths_visited.length > 0 && (
            <span className="text-gray-400 truncate">{pathLabel(hanger.baths_visited)}</span>
          )}
        </span>
      ))}
    </div>
  )
}

/** Плавающая переключалка вариантов: стрелки и клавиши ← →. */
function VariantSwitcher({ current }: { current: VariantKey }) {
  const [params, setParams] = useSearchParams()

  const cycle = useCallback(
    (step: number) => {
      const index = KEYS.indexOf(current)
      const next = KEYS[(index + step + KEYS.length) % KEYS.length]
      const updated = new URLSearchParams(params)
      updated.set('variant', next)
      setParams(updated, { replace: true })
    },
    [current, params, setParams],
  )

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      ) {
        return
      }
      if (event.key === 'ArrowLeft') cycle(-1)
      if (event.key === 'ArrowRight') cycle(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cycle])

  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-full bg-gray-900 px-4 py-2 text-white shadow-lg">
      <button
        onClick={() => cycle(-1)}
        className="px-2 text-lg leading-none hover:text-green-300"
        aria-label="Предыдущий вариант"
      >
        ←
      </button>
      <span className="text-xs font-mono whitespace-nowrap">
        ПРОТОТИП · {current} ({VARIANTS[current]})
      </span>
      <button
        onClick={() => cycle(1)}
        className="px-2 text-lg leading-none hover:text-green-300"
        aria-label="Следующий вариант"
      >
        →
      </button>
    </div>
  )
}

/**
 * Точка входа прототипа. Ставится вместо рабочего блока активных
 * подвесов, пока вариант не выбран.
 */
export function ActiveHangersPrototype({ hangers }: { hangers: PrototypeHanger[] }) {
  const [params, setParams] = useSearchParams()
  const key = (params.get('variant') ?? 'A').toUpperCase() as VariantKey
  const current: VariantKey = key in VARIANTS ? key : 'A'
  // Секундный тик: «в линии» должно расти само, как на живой линии.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900">Сейчас на линии</h3>
        <span className="text-xs text-gray-500">{hangers.length}</span>
      </div>

      {hangers.length === 0 ? (
        <p className="text-xs text-gray-500 py-2">Подвесов на линии нет.</p>
      ) : (
        <>
          {current === 'A' && <VariantA hangers={hangers} now={now} />}
          {current === 'B' && <VariantB hangers={hangers} now={now} />}
          {current === 'C' && <VariantC hangers={hangers} now={now} />}
        </>
      )}

      {Object.keys(params).length === 0 && (
        <button
          onClick={() => {
            const updated = new URLSearchParams(params)
            updated.set('variant', 'A')
            setParams(updated, { replace: true })
          }}
          className="mt-2 text-[11px] text-gray-400 underline"
        >
          включить переключатель вариантов
        </button>
      )}

      <VariantSwitcher current={current} />
    </div>
  )
}
