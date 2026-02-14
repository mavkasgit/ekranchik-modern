import { useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'

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
export function BathForecastTable() {
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
          
          // Process baths 30-33
          for (const bath of lineData.baths) {
            if ([30, 31, 32, 33].includes(bath.bath_number) && bath.pallete > 0) {
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
          console.log('[BathForecastTable] Bath data:', newBathData)
        }
      } catch (err) {
        console.error('[BathForecastTable] Error fetching data:', err)
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

  // Sort by remaining time (shortest first)
  const sortedBaths = Array.from(bathData.values()).sort((a, b) => a.remainingTime - b.remainingTime)

  return (
    <Card className="border-4 border-blue-500 mb-4">
      <CardContent className="p-4">
        <div className="flex gap-4 flex-wrap items-center">
          <span className="font-bold text-sm text-gray-600">Прогноз выхода:</span>
          {sortedBaths.map((item) => (
            <BathForecastItem key={item.bathNum} item={item} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function BathForecastItem({ item }: { item: BathForecastItem }) {
  const minutes = Math.floor(item.remainingTime / 60)
  const seconds = item.remainingTime % 60
  const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  
  // Color based on remaining time
  let bgColor = 'bg-green-100 text-green-700' // > 5 min
  if (item.remainingTime < 60) {
    bgColor = 'bg-red-100 text-red-700' // < 1 min
  } else if (item.remainingTime < 300) {
    bgColor = 'bg-yellow-100 text-yellow-700' // 1-5 min
  }
  
  return (
    <div className={`${bgColor} px-4 py-2 rounded-lg font-mono text-lg whitespace-nowrap`}>
      Ванна {item.bathNum} - {timeStr}
    </div>
  )
}
