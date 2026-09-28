import { useEffect, useState } from 'react'
import { advanceRun, emptyRun, startRun, type RunState } from '@/lib/domain/testRun'
import { formatLocalized } from '@/lib/domain/time'
import type { HangerData } from '@/types/dashboard'

/** Секунда: обратный отсчёт в карточках прогноза должен идти ровно. */
const TICK_MS = 1000

/**
 * Прогон витрины: подвесы едут по ваннам, по таймеру уходят в выгрузку.
 * Пустые строки — прогона нет, часы не идут.
 */
export function useTestRun(rows: HangerData[] | undefined): RunState {
  const [state, setState] = useState<RunState>(emptyRun)

  useEffect(() => {
    if (!rows || rows.length === 0) {
      setState(emptyRun())
      return
    }

    setState(startRun(rows))

    const timer = setInterval(
      () => setState(previous => advanceRun(previous, formatLocalized(new Date(), 'ru-RU'))),
      TICK_MS,
    )
    return () => clearInterval(timer)
  }, [rows])

  return state
}
