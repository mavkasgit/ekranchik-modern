import { useEffect, useMemo, useRef, useState } from 'react'
import { useLineStatus } from '@/hooks/useLineStatus'
import { colorAbbreviation, colorCellStyle, colorHex, colorName } from '@/lib/domain/color'
import { dwellChainToExit } from '@/lib/domain/time'
import { hangerKey } from '@/lib/domain/hanger'
import { profileText } from '@/lib/domain/profile'
import { CONTROL_BATH, FORECAST_BATHS, LINE_SECONDS, type RunHanger, type RunState } from '@/lib/domain/testRun'
import { FORECAST_MAX_ELAPSED_MS } from '@/config/intervals'
import type { LineStatus } from '@/types/line'

interface BathForecastItem {
  bathNum: number
  hangerNumber: number
  article: string
  color: string
  inTime: number
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
  elapsedSeconds: number,
): Map<number, BathForecastItem> {
  const forecast: Map<number, BathForecastItem> = new Map()

  const baths = lineStatus?.baths ?? []

  for (const bath of baths) {
    const isForecastBath = FORECAST_BATHS.includes(bath.bath_number)
    const isControlBath = bath.bath_number === CONTROL_BATH
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
      const inTimeNow = isControlBath ? inTime + elapsedSeconds : inTime
      forecast.set(bath.bath_number, {
        bathNum: bath.bath_number,
        hangerNumber: palletNumber,
        article: normalizeMetaValue(bath.article),
        color: normalizeMetaValue(bath.color),
        inTime: inTimeNow,
        // 34-я — сам сход: там остаток времени в этой ванне. Ванны
        // прогноза показывают время до схода, то есть сумму по цепочке
        // от своей ванны до 34-й, иначе выход получался одновременным.
        // `elapsedSeconds` — секунды с последнего сообщения линии: счётчики
        // ванн тикают сами, а приходят раз в 2 с, поэтому карточка ведёт
        // секунды ровно и не ждёт следующего сообщения.
        remainingTime: isControlBath
          ? Math.max(0, outTime - inTimeNow)
          : dwellChainToExit(baths, bath.bath_number, CONTROL_BATH, elapsedSeconds),
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
    inTime: LINE_SECONDS - hanger.remainingTime,
    remainingTime: hanger.remainingTime,
  })

  FORECAST_BATHS.forEach((bathNum, bathIndex) => {
    const hanger = run.line[bathIndex]
    if (hanger) forecast.set(bathNum, toItem(bathNum, hanger))
  })

  if (run.atExit) {
    forecast.set(CONTROL_BATH, {
      ...toItem(CONTROL_BATH, run.atExit),
      inTime: run.atExit.stoodSeconds,
      remainingTime: 0,
    })
  }

  return forecast
}

export function BathForecast({ hangerMetaByNumber = {}, testRun }: BathForecastProps) {
  const { data: lineStatus, dataUpdatedAt } = useLineStatus()
  const lastKnownHangerByBathRef = useRef<Map<number, number>>(new Map())

  // Секунды в карточках идут ровно: данные линии приходят раз в 2 с
  // (`line_update`), между ними остаток домеривается на клиенте — отсюда
  // тик раз в секунду. Домеривание ограничено FORECAST_MAX_ELAPSED_MS: за
  // это время данные уже считаются устаревшими, и цифры замирают вместо
  // того, чтобы уйти в ноль мимо линии.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const elapsedSeconds = Math.min(FORECAST_MAX_ELAPSED_MS, now - dataUpdatedAt) / 1000

  // В тестовом режиме карточки строятся только из прогона: живые ванны сюда не подмешиваются.
  // Прогон тикает раз в секунду сам, домеривать ему нечего.
  const bathData = useMemo(
    () => (testRun
      ? buildRunForecast(testRun)
      : buildBathForecast(lineStatus, lastKnownHangerByBathRef.current, elapsedSeconds)),
    [lineStatus, testRun, elapsedSeconds],
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

  const unloadTimeStr = cardTime(bath34Item ? bath34Item.inTime : 0)

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

/**
 * Время карточки `мм:сс` целыми секундами. Между сообщениями линии остаток
 * домеривается дробью секунды, и без округления на экране появлялось «00:1.93».
 */
function cardTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(whole / 60).toString().padStart(2, '0')
  return `${minutes}:${(whole % 60).toString().padStart(2, '0')}`
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
  const timeStr = cardTime(item.remainingTime)

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
