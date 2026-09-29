import { useMemo, useRef } from 'react'
import { useLineStatus } from '@/hooks/useLineStatus'
import { colorAbbreviation, colorCellStyle, colorHex, colorName } from '@/lib/domain/color'
import { hangerKey } from '@/lib/domain/hanger'
import { profileText } from '@/lib/domain/profile'
import { CONTROL_BATH, DWELL_SECONDS, FORECAST_BATHS, type RunHanger, type RunState } from '@/lib/domain/testRun'
import type { LineStatus } from '@/types/line'

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
  /** Прогон витрины вместо состояния линии: на стенде симулятора нет. */
  testRun?: RunState
}



interface HangerMeta {
  profile?: string | null
  color?: string | null
}

type HangerMetaByNumber = Record<string, HangerMeta>

function normalizeMetaValue(value: string | null | undefined): string {
  const text = (value ?? '').trim()
  return text || '—'
}

function pickMetaValue(primary: string | null | undefined, fallback: string | null | undefined): string {
  const primaryNormalized = normalizeMetaValue(primary)
  if (primaryNormalized !== '—') return primaryNormalized
  return normalizeMetaValue(fallback)
}

/** Ванны прогноза (30–33) и контрольная ванна (34) из состояния линии. */
function buildBathForecast(
  lineStatus: LineStatus | undefined,
  lastKnownHangerByBath: Map<number, number>,
): Map<number, BathForecastItem> {
  const forecast: Map<number, BathForecastItem> = new Map()

  for (const bath of lineStatus?.baths ?? []) {
    const isForecastBath = [30, 31, 32, 33].includes(bath.bath_number)
    const isControlBath = bath.bath_number === 34
    const inTime = bath.in_time || 0
    const outTime = bath.out_time || 0

    const rawPalletNumber = bath.pallete || 0
    if (rawPalletNumber > 0) {
      lastKnownHangerByBath.set(bath.bath_number, rawPalletNumber)
    }
    if (isControlBath && inTime <= 0 && rawPalletNumber <= 0) {
      lastKnownHangerByBath.delete(34)
    }

    const fallbackPalletNumber = lastKnownHangerByBath.get(bath.bath_number) || 0
    const palletNumber = rawPalletNumber > 0 ? rawPalletNumber : fallbackPalletNumber
    const hasUnloadSignal = isControlBath && (inTime > 0 || rawPalletNumber > 0 || fallbackPalletNumber > 0)

    if ((isForecastBath && rawPalletNumber > 0) || hasUnloadSignal) {
      forecast.set(bath.bath_number, {
        bathNum: bath.bath_number,
        hangerNumber: palletNumber,
        article: normalizeMetaValue(bath.article),
        color: normalizeMetaValue(bath.color),
        inTime,
        outTime,
        remainingTime: Math.max(0, outTime - inTime),
      })
    }
  }

  return forecast
}

/** Карточки прогноза по подвесам тестового прогона: ванны прогноза плюс ванна схода. */
function buildRunForecast(run: RunState): Map<number, BathForecastItem> {
  const forecast: Map<number, BathForecastItem> = new Map()

  const toItem = (bathNum: number, hanger: RunHanger): BathForecastItem => ({
    bathNum,
    hangerNumber: hanger.number,
    article: normalizeMetaValue(hanger.row.profile),
    color: normalizeMetaValue(hanger.row.color),
    inTime: DWELL_SECONDS - hanger.remainingTime,
    outTime: hanger.remainingTime,
    remainingTime: hanger.remainingTime,
  })

  run.inBaths.forEach((hanger, index) => {
    const bathNum = FORECAST_BATHS[index]
    if (bathNum !== undefined) forecast.set(bathNum, toItem(bathNum, hanger))
  })

  if (run.atExit) forecast.set(CONTROL_BATH, toItem(CONTROL_BATH, run.atExit))

  return forecast
}

export function BathForecast({ hangerMetaByNumber = {}, testRun }: BathForecastProps) {
  const { data: lineStatus } = useLineStatus()
  const lastKnownHangerByBathRef = useRef<Map<number, number>>(new Map())

  // В тестовом режиме карточки строятся только из прогона: живые ванны сюда не подмешиваются.
  const bathData = useMemo(
    () => (testRun
      ? buildRunForecast(testRun)
      : buildBathForecast(lineStatus, lastKnownHangerByBathRef.current)),
    [lineStatus, testRun],
  )
  const runMetaByNumber = testRun ? undefined : hangerMetaByNumber

  const sortedBaths = Array.from(bathData.values())
    .filter(b => b.bathNum !== CONTROL_BATH)
    .sort((a, b) => a.remainingTime - b.remainingTime)

  const bath34Item = bathData.get(CONTROL_BATH)

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
          hangerMetaByNumber={runMetaByNumber}
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
              hangerMetaByNumber={runMetaByNumber}
            />
          ))
        ) : null}
      </div>
    </div>
  )
}

/** Общие поля карточки ванны: подпись подвеса, профиль, цвет, стиль ячейки. */
function bathCardFields(item: BathForecastItem, hangerMetaByNumber: HangerMetaByNumber | undefined) {
  const meta = hangerMetaByNumber?.[hangerKey(item.hangerNumber)]
  const profile = pickMetaValue(item.article, meta?.profile)
  const color = pickMetaValue(item.color, meta?.color)

  return {
    hangerLabel: item.hangerNumber > 0 ? `№${item.hangerNumber}` : '№—',
    profileDigits: profileText(profile),
    colorAbbr: colorAbbreviation(color),
    colorTitle: colorName(color),
    fillStyle: colorCellStyle(colorHex(color)),
  }
}

function BathCard({ item, hangerMetaByNumber }: { item: BathForecastItem, hangerMetaByNumber: HangerMetaByNumber | undefined }) {
  const minutes = Math.floor(item.remainingTime / 60)
  const seconds = item.remainingTime % 60
  const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`

  const { hangerLabel, profileDigits, colorAbbr, colorTitle, fillStyle } = bathCardFields(item, hangerMetaByNumber)

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
        <span className="font-black text-[18px] leading-[18px] text-black" title={colorTitle}>{colorAbbr}</span>
      </div>
    </div>
  )
}

function UnloadCard({ item, hangerMetaByNumber, isCompact, unloadTimeStr }: { item: BathForecastItem, hangerMetaByNumber: HangerMetaByNumber | undefined, isCompact: boolean, unloadTimeStr: string }) {
  const { hangerLabel, profileDigits, colorAbbr, colorTitle, fillStyle } = bathCardFields(item, hangerMetaByNumber)

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
          <span className="font-black text-[18px] leading-[18px] text-black" title={colorTitle}>{colorAbbr}</span>
        </div>
      </div>
    </div>
  )
}
