import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, AlertCircle, Wifi, WifiOff } from 'lucide-react'
import { useLineStatus } from '@/hooks/useLineStatus'
import { useRealtimeConnection, useRealtimeEvent } from '@/hooks/useRealtime'
import { lineApi } from '@/api/line'
import { formatDuration, formatLocalized } from '@/lib/domain/time'
import { WS_UPDATE_INTERVAL_SEC } from '@/config/intervals'
import type { BathStatus, CompletedCycle } from '@/types/line'

// Bath layout configuration - baths 3-34 (excluding 1-2 and 35-39)
const BATH_LAYOUT = {
  // Top row: baths 18-3 (right to left, reversed)
  topRow: Array.from({ length: 16 }, (_, i) => 18 - i),
  // Bottom row: baths 19-34 (left to right)
  bottomRow: Array.from({ length: 16 }, (_, i) => i + 19),
  // Control point (exit)
  controlPoint: 34,
}

export function LineVisualization() {
  const { data: lineData, isFetching, error: lineError, refetch } = useLineStatus()
  const [cycles, setCycles] = useState<CompletedCycle[]>([])
  const { isConnected } = useRealtimeConnection()

  const fetchCycles = useCallback(async () => {
    try {
      setCycles(await lineApi.getCycles(10))
    } catch {
      // Ошибка загрузки циклов не мешает показу линии
    }
  }, [])

  // Начальная загрузка циклов; дальше — по событию выгрузки
  useEffect(() => {
    void fetchCycles()
  }, [fetchCycles])

  useRealtimeEvent('unload_event', fetchCycles)

  const getBathData = (bathNumber: number): BathStatus | undefined => {
    return lineData?.baths.find(b => b.bath_number === bathNumber)
  }

  const getBathColor = (bath: BathStatus | undefined, bathNumber: number): string => {
    if (!bath) return 'bg-gray-200'

    // Control point (exit) - special color
    if (bathNumber === BATH_LAYOUT.controlPoint) {
      return bath.in_use ? 'bg-orange-500' : 'bg-orange-200'
    }

    // Simple: occupied or free
    if (bath.in_use) {
      return 'bg-green-500'
    }

    return 'bg-gray-200'
  }

  const BathCell = ({ bathNumber }: { bathNumber: number }) => {
    const bath = getBathData(bathNumber)
    const isControlPoint = bathNumber === BATH_LAYOUT.controlPoint
    
    return (
      <div className="flex flex-col items-center">
        {/* Ячейка ванны */}
        <div
          className={`
            relative w-14 h-14 rounded-lg border-2 flex flex-col items-center justify-center
            transition-all duration-300 cursor-pointer hover:scale-105
            ${getBathColor(bath, bathNumber)}
            ${isControlPoint ? 'border-orange-600 ring-2 ring-orange-300' : 'border-gray-400'}
            ${bath?.in_use ? 'shadow-lg' : ''}
          `}
          title={bath ? `Ванна ${bathNumber}\nПодвес: ${bath.pallete}` : `Ванна ${bathNumber}`}
        >
          {/* Номер подвеса сверху (если занята) */}
          {bath?.in_use && bath.pallete > 0 ? (
            <span className="text-sm font-bold text-white">
              {bath.pallete}
            </span>
          ) : (
            <span className="text-xs text-gray-400">—</span>
          )}
          
          {/* Номер ванны снизу */}
          <span className={`text-[10px] ${bath?.in_use ? 'text-white/70' : 'text-gray-500'}`}>
            [{bathNumber}]
          </span>
          
          {isControlPoint && (
            <div className="absolute -top-2 -right-2 w-4 h-4 bg-orange-600 rounded-full flex items-center justify-center">
              <span className="text-[8px] text-white font-bold">!</span>
            </div>
          )}
        </div>
        
        {/* Время под ванной */}
        {bath?.in_use && (
          <div className="text-[9px] text-gray-600 mt-1 text-center font-mono">
            {formatDuration(bath.in_time)}/{formatDuration(bath.out_time)}
          </div>
        )}
      </div>
    )
  }

  const activeBaths = lineData?.baths.filter(b => b.in_use).length || 0
  const totalBaths = lineData?.baths.length || 39

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Production Line</h2>
          <p className="text-sm text-gray-600 mt-1">
            Real-time bath status • Control point: Bath[{BATH_LAYOUT.controlPoint}]
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* WebSocket статус */}
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
            isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}>
            {isConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
            <span className="text-sm font-medium">
              {isConnected ? `Live (${WS_UPDATE_INTERVAL_SEC}s)` : 'Offline'}
            </span>
          </div>
          <button
            onClick={() => void refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {lineError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-600" />
          <span className="text-red-700">{lineError.message}</span>
        </div>
      )}

      {/* Statistics */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium">Active Baths</div>
          <div className="text-2xl font-bold text-blue-900">{activeBaths} / {totalBaths}</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium">Pallets in Line</div>
          <div className="text-2xl font-bold text-green-900">
            {lineData?.active_hangers ?? lineData?.baths.filter(b => b.pallete > 0).length ?? 0}
          </div>
        </div>
        <div className="bg-purple-50 rounded-lg p-4">
          <div className="text-sm text-purple-600 font-medium">Cycles Today</div>
          <div className="text-2xl font-bold text-purple-900">{cycles.length}</div>
        </div>
        <div className="bg-orange-50 rounded-lg p-4">
          <div className="text-sm text-orange-600 font-medium">Last Update</div>
          <div className="text-lg font-mono text-orange-900">
            {formatLocalized(lineData?.timestamp)}
          </div>
        </div>
      </div>

      {/* Line Visualization */}
      <div className="bg-gray-50 rounded-lg p-6 mb-6">
        <div className="flex flex-col gap-6">
          {/* Top row: Baths 18-3 (reversed) */}
          <div className="flex items-center gap-1">
            <div className="w-16 text-right text-xs text-gray-500 mr-2">Ванны 18-3</div>
            <div className="flex gap-1 flex-wrap">
              {BATH_LAYOUT.topRow.map(num => (
                <BathCell key={num} bathNumber={num} />
              ))}
            </div>
          </div>
          
          {/* Bottom row: Baths 19-34 */}
          <div className="flex items-center gap-1">
            <div className="w-16 text-right text-xs text-gray-500 mr-2">Ванны 19-34</div>
            <div className="flex gap-1 flex-wrap">
              {BATH_LAYOUT.bottomRow.map(num => (
                <BathCell key={num} bathNumber={num} />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 mb-6 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-green-500 rounded"></div>
          <span>Занята</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-gray-200 rounded border border-gray-300"></div>
          <span>Свободна</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-orange-500 rounded border-2 border-orange-600"></div>
          <span>Выгрузка (Bath 34)</span>
        </div>
      </div>

      {/* Recent Cycles */}
      {cycles.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 text-gray-900">Recent Completed Cycles</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Cycle</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Pallete</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">First seen</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Entry bath</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Exited</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Duration</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Baths Visited</th>
                </tr>
              </thead>
              <tbody>
                {cycles.slice(0, 5).map((cycle, idx) => {
                  const durationSec =
                    cycle.first_seen_at && cycle.exit_at
                      ? (Date.parse(cycle.exit_at) - Date.parse(cycle.first_seen_at)) / 1000
                      : null
                  return (
                    <tr key={cycle.cycle_id ?? idx} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-3 px-3 font-mono text-gray-500">{cycle.cycle_id ?? '—'}</td>
                      <td className="py-3 px-3 font-mono font-semibold text-gray-900">
                        P{cycle.hanger}
                      </td>
                      <td className="py-3 px-3 text-gray-700">
                        {cycle.first_seen_at ? formatLocalized(cycle.first_seen_at) : '—'}
                      </td>
                      <td className="py-3 px-3 font-mono text-gray-700">{cycle.entry_bath ?? '—'}</td>
                      <td className="py-3 px-3 text-gray-700">
                        {cycle.exit_at ? formatLocalized(cycle.exit_at) : '—'}
                      </td>
                      <td className="py-3 px-3 text-gray-700">
                        {durationSec === null ? '—' : formatDuration(durationSec)}
                      </td>
                      <td className="py-3 px-3 text-xs text-gray-600 font-mono">
                        {cycle.baths_visited?.join(' → ') ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
