import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'


interface BathForecastItem {
  bathNum: number
  inTime: number
  outTime: number
  remainingTime: number
}

/**
 * Component to display forecast for baths 30-33 in a single line
 * Shows remaining time for each hanger in baths 30-33
 */
/**
 * Component to display forecast for baths 30-33
 * Simplified for embedding in table header
 */
export function BathForecast() {
  const [bathData, setBathData] = useState<Map<number, BathForecastItem>>(new Map())
  const [, setUpdateTrigger] = useState(0)

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Get line status with all bath data
        const lineRes = await fetch(`/api/opcua/line/status?t=${Date.now()}`)
        if (lineRes.ok) {
          const lineData = await lineRes.json()
          const newBathData = new Map<number, BathForecastItem>()

          // Process baths 30-33 AND 34
          for (const bath of lineData.baths) {
            const isForecastBath = [30, 31, 32, 33].includes(bath.bath_number)
            const isUnloadBath = bath.bath_number === 34

            // For forecast baths, we need a palette. For unload (34), we just need a valid start time.
            if ((isForecastBath && bath.pallete > 0) || (isUnloadBath && bath.in_time > 0)) {
              const inTime = bath.in_time || 0
              const outTime = bath.out_time || 0
              const remainingTime = Math.max(0, outTime - inTime)

              newBathData.set(bath.bath_number, {
                bathNum: bath.bath_number,
                inTime,
                outTime,
                remainingTime
              })
            }
          }

          setBathData(newBathData)
        }
      } catch (err) {
        console.error('[BathForecast] Error fetching data:', err)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 1000) // Refresh every second for countdown
    return () => clearInterval(interval)
  }, [])

  // Trigger re-render every second for countdown
  useEffect(() => {
    const timer = setInterval(() => {
      setUpdateTrigger(prev => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  if (bathData.size === 0) {
    return null
  }

  // Sort by remaining time (shortest first), excluding bath 34 (handled separately)
  const sortedBaths = Array.from(bathData.values())
    .filter(b => b.bathNum !== 34)
    .sort((a, b) => a.remainingTime - b.remainingTime)

  const bath34Item = bathData.get(34)
  const totalItems = sortedBaths.length + (bath34Item ? 1 : 0)
  // Shift to short labels if we have more than 3 items (e.g., bath 34 + 3 forecast items = 4 total)
  const useShortLabels = totalItems > 3

  // Traffic light logic
  const minTime = sortedBaths.length > 0 ? sortedBaths[0].remainingTime : Infinity

  // Red if:
  // 1. Someone is already out (bath34 exists)
  // 2. Less than 60 seconds remaining for next bath
  const isRed = (bath34Item !== undefined) || (minTime < 60)
  const isYellow = !isRed && minTime < 300
  const isGreen = !isRed && !isYellow

  // Bath 34 (Unload) logic
  const unloadDuration = bath34Item ? bath34Item.inTime : 0
  const unloadMinutes = Math.floor(unloadDuration / 60)
  const unloadSeconds = unloadDuration % 60
  const unloadTimeStr = `${unloadMinutes.toString().padStart(2, '0')}:${unloadSeconds.toString().padStart(2, '0')}`

  return (
    <div className="flex gap-2 items-center py-2 px-4 min-h-[3.5rem] bg-background rounded-md border-2 border-slate-200 dark:border-slate-800 shadow-sm z-20 relative flex-wrap">
      {/* 1. Traffic Light */}
      <div className="flex items-center gap-1.5 mr-1 bg-black/10 px-2 py-1 rounded-full border border-black/5 shrink-0">
        <div className={`w-3 h-3 rounded-full transition-all duration-300 ${isRed ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)] animate-pulse scale-110' : 'bg-red-900/30'}`} />
        <div className={`w-3 h-3 rounded-full transition-all duration-300 ${isYellow ? 'bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.8)] scale-110' : 'bg-yellow-900/30'}`} />
        <div className={`w-3 h-3 rounded-full transition-all duration-300 ${isGreen ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)] scale-110' : 'bg-green-900/30'}`} />
      </div>

      {/* 2 & 3. Grouped Content (Forecast & Unload) */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 flex-1 min-w-[200px]">
        {/* 2. Bath 34 Unload Timer (if active) */}
        {bath34Item && (
          <div className="flex items-center gap-2 animate-in fade-in slide-in-from-left-2 whitespace-nowrap">
            <span className="font-bold text-lg text-foreground">
              {useShortLabels ? 'Вышел:' : 'Уже вышел:'}
            </span>
            <span className="font-mono text-lg font-bold text-red-600">
              {unloadTimeStr}
            </span>
            <span className="text-muted-foreground opacity-50 ml-1">|</span>
          </div>
        )}

        {/* 3. Forecast Label & Items */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-bold text-lg text-foreground whitespace-nowrap">
            {useShortLabels ? 'Прогноз:' : 'Прогноз выхода:'}
          </span>
          {sortedBaths.map((item) => (
            <BathForecastItem key={item.bathNum} item={item} useShortLabels={useShortLabels} />
          ))}
        </div>
      </div>

      {/* 4. Current Time */}
      <div className="flex items-center gap-2 text-muted-foreground/80 whitespace-nowrap pl-4 border-l border-slate-200 dark:border-slate-800">
        <Clock className="w-4 h-4" />
        <ClockDisplay />
      </div>
    </div>
  )
}

function ClockDisplay() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <span className="font-mono text-lg font-bold text-foreground">
      {time.toLocaleTimeString('ru-RU')}
    </span>
  )
}

function BathForecastItem({ item, useShortLabels }: { item: BathForecastItem, useShortLabels: boolean }) {
  const minutes = Math.floor(item.remainingTime / 60)
  const seconds = item.remainingTime % 60
  const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`

  // Color based on remaining time
  let timeColor = 'text-green-600' // > 5 min
  if (item.remainingTime < 60) {
    timeColor = 'text-red-600 animate-pulse' // < 1 min + pulse
  } else if (item.remainingTime < 300) {
    timeColor = 'text-orange-500' // 1-5 min
  }

  return (
    <div className="font-mono text-lg font-medium whitespace-nowrap">
      {!useShortLabels && <span className="opacity-70">Ванна </span>}
      {item.bathNum} — <span className={`font-bold ${timeColor}`}>{timeStr}</span>
    </div>
  )
}
