import { useCallback, useEffect, useRef, useState } from 'react'
import { Clock } from 'lucide-react'
import { useRealtimeData } from '@/hooks/useRealtimeData'

interface BathForecastItem {
  bathNum: number
  hangerNumber: number
  article: string
  color: string
  inTime: number
  outTime: number
  remainingTime: number
}

interface BathForecastProps {
  hangerMetaByNumber?: HangerMetaByNumber
}

interface HangerMeta {
  profile?: string | null
  color?: string | null
}

type HangerMetaByNumber = Record<string, HangerMeta>

function normalizeHangerKey(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return ''
  const raw = String(value).trim()
  if (!raw) return ''

  const normalizedNumeric = Number(raw.replace(',', '.'))
  if (Number.isFinite(normalizedNumeric)) {
    return String(Math.trunc(normalizedNumeric))
  }

  return raw
}

function normalizeMetaValue(value: string | null | undefined): string {
  const text = (value ?? '').trim()
  return text || '—'
}

function pickMetaValue(primary: string | null | undefined, fallback: string | null | undefined): string {
  const primaryNormalized = normalizeMetaValue(primary)
  if (primaryNormalized !== '—') return primaryNormalized
  return normalizeMetaValue(fallback)
}

function getColorHex(colorName: string): string {
  const name = colorName.toLowerCase().trim()

  const colorMap: Record<string, string> = {
    'серебро': '#C0C0C0',
    'черный': '#1C1C1C',
    'золото': '#FFD700',
    'шампань': '#F7E7CE',
    'титан': '#878681',
    'бронза': '#8B5A2B',
    'медь': '#CD5C5C',
    'растрав': '#D3D3D3',
    'rosegold': '#B76E79',
  }

  if (colorMap[name]) return colorMap[name]

  for (const [key, value] of Object.entries(colorMap)) {
    if (name.includes(key) || key.includes(name)) return value
  }

  return '#9CA3AF'
}

function abbreviateColor(colorName: string): string {
  const name = colorName.toLowerCase().trim()
  const abbrevMap: Record<string, string> = {
    'серебро': 'сер',
    'черный': 'чер',
    'золото': 'зол',
    'шампань': 'шам',
    'титан': 'тит',
    'бронза': 'брз',
    'медь': 'мед',
    'растрав': 'рст',
    'rosegold': 'роз',
  }
  if (abbrevMap[name]) return abbrevMap[name]
  return name.slice(0, 4) || '—'
}

function extractProfileText(profile: string): string {
  const normalized = profile
    .replace(/\s+/g, '')
    .replace(/[^0-9()+*xхX×\/.,;]/g, '')
  return normalized || '—'
}

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '').trim()
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `rgba(156, 163, 175, ${alpha})`
  }

  const r = Number.parseInt(normalized.slice(0, 2), 16)
  const g = Number.parseInt(normalized.slice(2, 4), 16)
  const b = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function getCellStyle(colorHex: string) {
  return {
    background: `linear-gradient(135deg, ${hexToRgba(colorHex, 0.6)} 0%, ${hexToRgba(colorHex, 0.4)} 100%)`,
    boxShadow: `inset 0 0 0 1px ${hexToRgba(colorHex, 0.52)}`,
  }
}

export function BathForecast({ hangerMetaByNumber = {} }: BathForecastProps) {
  const [bathData, setBathData] = useState<Map<number, BathForecastItem>>(new Map())
  const lastKnownHangerByBathRef = useRef<Map<number, number>>(new Map())

  const fetchData = useCallback(async () => {
    try {
      const lineRes = await fetch(`/api/opcua/line/status?t=${Date.now()}`)
      if (lineRes.ok) {
        const lineData = await lineRes.json()
        const newBathData = new Map<number, BathForecastItem>()

        for (const bath of lineData.baths) {
          const isForecastBath = [30, 31, 32, 33].includes(bath.bath_number)
          const isUnloadBath = bath.bath_number === 34
          const inTime = bath.in_time || 0
          const outTime = bath.out_time || 0
          const remainingTime = Math.max(0, outTime - inTime)

          const rawPalletNumber = Number(bath.pallete) || 0
          if (rawPalletNumber > 0) {
            lastKnownHangerByBathRef.current.set(bath.bath_number, rawPalletNumber)
          }

          if (isUnloadBath && inTime <= 0 && rawPalletNumber <= 0) {
            lastKnownHangerByBathRef.current.delete(34)
          }

          const fallbackPalletNumber = lastKnownHangerByBathRef.current.get(bath.bath_number) || 0
          const palletNumber = rawPalletNumber > 0 ? rawPalletNumber : fallbackPalletNumber
          const hasUnloadSignal = isUnloadBath && (inTime > 0 || rawPalletNumber > 0 || fallbackPalletNumber > 0)

          if ((isForecastBath && rawPalletNumber > 0) || hasUnloadSignal) {
            newBathData.set(bath.bath_number, {
              bathNum: bath.bath_number,
              hangerNumber: palletNumber,
              article: normalizeMetaValue(bath.article),
              color: normalizeMetaValue(bath.color),
              inTime,
              outTime,
              remainingTime,
            })
          }
        }

        setBathData(newBathData)
      }
    } catch (err) {
      console.error('[BathForecast] Error fetching data:', err)
    }
  }, [])

  useRealtimeData({
    onMessage: (message) => {
      if (message.type === 'data_update' || message.type === 'unload_event' || message.type === 'opcua_status') {
        void fetchData()
      }
    }
  })

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  useEffect(() => {
    const interval = setInterval(() => {
      void fetchData()
    }, 10000)

    return () => clearInterval(interval)
  }, [fetchData])

  useEffect(() => {
    const timer = setInterval(() => {
      setBathData(prev => {
        if (prev.size === 0) return prev

        const next = new Map<number, BathForecastItem>()
        let changed = false

        for (const [bathNum, item] of prev.entries()) {
          if (bathNum === 34) {
            next.set(bathNum, { ...item, inTime: item.inTime + 1 })
            changed = true
            continue
          }

          if (item.remainingTime > 0) {
            next.set(bathNum, { ...item, remainingTime: Math.max(0, item.remainingTime - 1) })
            changed = true
            continue
          }

          next.set(bathNum, item)
        }

        return changed ? next : prev
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [])

  const sortedBaths = Array.from(bathData.values())
    .filter(b => b.bathNum !== 34)
    .sort((a, b) => a.remainingTime - b.remainingTime)

  const bath34Item = bathData.get(34)

  const minTime = sortedBaths.length > 0 ? sortedBaths[0].remainingTime : Infinity
  const isRed = (bath34Item !== undefined) || (minTime < 60)
  const isYellow = !isRed && minTime < 300
  const isGreen = !isRed && !isYellow

  const unloadDuration = bath34Item ? bath34Item.inTime : 0
  const unloadMinutes = Math.floor(unloadDuration / 60)
  const unloadSeconds = unloadDuration % 60
  const unloadTimeStr = `${unloadMinutes.toString().padStart(2, '0')}:${unloadSeconds.toString().padStart(2, '0')}`

  const totalForecastItems = sortedBaths.length + (bath34Item ? 1 : 0)
  const isCompact = totalForecastItems > 2

  return (
    <div className="flex items-stretch py-1 px-2 bg-background rounded-md border border-slate-200 dark:border-slate-800 shadow-sm z-20 relative">
      <div className="flex items-center gap-1 mr-2 bg-black/10 px-1.5 py-1 rounded-full border border-black/5 shrink-0 self-center">
        <div className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${isRed ? 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.8)] animate-pulse scale-110' : 'bg-red-900/30'}`} />
        <div className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${isYellow ? 'bg-yellow-500 shadow-[0_0_6px_rgba(234,179,8,0.8)] scale-110' : 'bg-yellow-900/30'}`} />
        <div className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${isGreen ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.8)] scale-110' : 'bg-green-900/30'}`} />
      </div>

      {bath34Item && (
        <UnloadCard
          item={bath34Item}
          hangerMetaByNumber={hangerMetaByNumber}
          isCompact={isCompact}
          unloadTimeStr={unloadTimeStr}
        />
      )}

      <div className="flex flex-col justify-center px-2 border-r border-slate-200 dark:border-slate-800 shrink-0">
        <span className="font-bold text-[18px] leading-[18px] text-foreground whitespace-nowrap">
          {isCompact ? 'Прогноз:' : 'Прогноз выхода:'}
        </span>
      </div>

      <div className="flex items-stretch flex-1 min-w-0 overflow-hidden gap-1">
        {sortedBaths.length > 0 ? (
          sortedBaths.map((item) => (
            <BathCard
              key={item.bathNum}
              item={item}
              hangerMetaByNumber={hangerMetaByNumber}
            />
          ))
        ) : null}
      </div>

      <div className="flex items-center gap-1.5 pl-3 border-l border-slate-200 dark:border-slate-800 shrink-0">
        <Clock className="w-4 h-4 text-muted-foreground" />
        <span className="font-mono text-[18px] font-bold leading-[18px] text-foreground whitespace-nowrap">
          <ClockInline />
        </span>
      </div>
    </div>
  )
}

function ClockInline() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <span>{time.toLocaleTimeString('ru-RU')}</span>
  )
}

function BathCard({ item, hangerMetaByNumber }: { item: BathForecastItem, hangerMetaByNumber: HangerMetaByNumber }) {
  const minutes = Math.floor(item.remainingTime / 60)
  const seconds = item.remainingTime % 60
  const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`

  const meta = hangerMetaByNumber[normalizeHangerKey(item.hangerNumber)]
  const profile = pickMetaValue(item.article, meta?.profile)
  const color = pickMetaValue(item.color, meta?.color)
  const colorHex = getColorHex(color)
  const colorAbbr = abbreviateColor(color)
  const profileDigits = extractProfileText(profile)
  const hangerLabel = item.hangerNumber > 0 ? `№${item.hangerNumber}` : '№—'
  const fillStyle = getCellStyle(colorHex)

  let timeColor = 'text-green-600'
  if (item.remainingTime < 60) {
    timeColor = 'text-red-600 animate-pulse'
  } else if (item.remainingTime < 300) {
    timeColor = 'text-orange-500'
  }

  return (
    <div className="flex flex-col justify-center px-1 py-0 shrink-0 rounded-sm border border-slate-300/80 dark:border-slate-700/80" style={fillStyle}>
      <div className="font-mono text-[18px] font-medium whitespace-nowrap leading-tight flex items-center gap-1">
        <span className="opacity-70">В{item.bathNum}</span>
        <span className="opacity-55">·</span>
        <span className={`font-bold ${timeColor}`}>{timeStr}</span>
      </div>
      <div className="font-mono text-[18px] whitespace-nowrap leading-tight">
        <span className="opacity-80">{hangerLabel}</span>
        <span className="opacity-55 mx-1">·</span>
        <span className="font-semibold">{profileDigits}</span>
        <span className="opacity-55 mx-1">·</span>
        <span className="font-black text-[18px] leading-[18px] text-black">{colorAbbr}</span>
      </div>
    </div>
  )
}

function UnloadCard({ item, hangerMetaByNumber, isCompact, unloadTimeStr }: { item: BathForecastItem, hangerMetaByNumber: HangerMetaByNumber, isCompact: boolean, unloadTimeStr: string }) {
  const meta = hangerMetaByNumber[normalizeHangerKey(item.hangerNumber)]
  const profile = pickMetaValue(item.article, meta?.profile)
  const color = pickMetaValue(item.color, meta?.color)
  const colorHex = getColorHex(color)
  const colorAbbr = abbreviateColor(color)
  const profileDigits = extractProfileText(profile)
  const hangerLabel = item.hangerNumber > 0 ? `№${item.hangerNumber}` : '№—'
  const fillStyle = getCellStyle(colorHex)

  return (
    <div className="flex items-center gap-1 px-1 py-0 border-l border-r border-slate-200 dark:border-slate-800 shrink-0">
      <span className="font-bold text-[18px] leading-[18px] text-foreground whitespace-nowrap">{isCompact ? 'Вышел:' : 'Уже вышел:'}</span>
      <div className="flex flex-col rounded-sm border border-slate-300/80 dark:border-slate-700/80 px-1 py-0" style={fillStyle}>
        <div className="font-mono text-[18px] font-medium whitespace-nowrap leading-tight flex items-center gap-1">
          <span className="opacity-70">В{item.bathNum}</span>
          <span className="opacity-55">·</span>
          <span className="font-bold text-red-600">{unloadTimeStr}</span>
        </div>
        <div className="font-mono text-[18px] whitespace-nowrap leading-tight">
          <span className="opacity-80">{hangerLabel}</span>
          <span className="opacity-55 mx-1">·</span>
          <span className="font-semibold">{profileDigits}</span>
          <span className="opacity-55 mx-1">·</span>
          <span className="font-black text-[18px] leading-[18px] text-black">{colorAbbr}</span>
        </div>
      </div>
    </div>
  )
}
