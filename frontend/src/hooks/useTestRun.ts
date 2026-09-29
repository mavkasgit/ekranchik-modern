import { useEffect, useRef, useState } from 'react'
import { advanceRun, emptyRun, startRun, type RunState } from '@/lib/domain/testRun'
import type { HangerData } from '@/types/dashboard'

/** Секунда: обратный отсчёт в карточках прогноза должен идти ровно. */
const TICK_MS = 1000

/**
 * Прогон витрины: подвесы едут по ваннам, по таймеру уходят в выгрузку.
 * Окно выгрузки — то же, что задаёт оператор в фильтрах. Пустые строки —
 * прогона нет, часы не идут.
 *
 * Потолок выгрузки читается из ссылки, а не из зависимостей эффекта: иначе
 * правка поля фильтра на каждом нажатии перезапускала бы прогон с нуля.
 */
export function useTestRun(rows: HangerData[] | undefined, unloadLimit: number): RunState {
  const [state, setState] = useState<RunState>(emptyRun)
  const unloadLimitRef = useRef(unloadLimit)
  unloadLimitRef.current = unloadLimit

  useEffect(() => {
    if (!rows || rows.length === 0) {
      setState(emptyRun())
      return
    }

    setState(startRun(rows, new Date()))

    const timer = setInterval(
      () => setState(previous => advanceRun(previous, new Date(), unloadLimitRef.current)),
      TICK_MS,
    )
    return () => clearInterval(timer)
  }, [rows])

  return state
}
