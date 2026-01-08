import { useEffect, useState } from 'react'
import { RefreshCw, CheckCircle, Clock } from 'lucide-react'

interface BathRecord {
  bath_number: number
  in_time: string | null
  out_time: string | null
  duration: string | null
}

interface HangerEvent {
  hanger_number: number
  pallete_data: string | null
  baths_history: BathRecord[]
  first_seen: string
  last_updated: string
  total_baths: number
  current_bath: number | null
}

export function HangerTracker() {
  const [hangers, setHangers] = useState<HangerEvent[]>([])
  const [activeHangers, setActiveHangers] = useState<HangerEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchHangers = async () => {
    setLoading(true)
    try {
      const [allRes, activeRes] = await Promise.all([
        fetch('/api/opcua/baths'),
        fetch('/api/opcua/baths/active')
      ])
      
      if (!allRes.ok || !activeRes.ok) throw new Error('Failed to fetch bath data')
      
      const allData = await allRes.json()
      const activeData = await activeRes.json()
      
      setHangers(allData.hangers || [])
      setActiveHangers(activeData.hangers || [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const updateAllHangers = async () => {
    try {
      const response = await fetch('/api/opcua/baths/update', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to update baths')
      await fetchHangers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update')
    }
  }

  useEffect(() => {
    fetchHangers()
    
    if (autoRefresh) {
      const interval = setInterval(fetchHangers, 10000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh])

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return '—'
    try {
      const date = new Date(timeStr)
      return date.toLocaleTimeString()
    } catch {
      return timeStr
    }
  }

  const formatBathPath = (baths: BathRecord[]) => {
    return baths.map(b => `[${b.bath_number}]`).join(' → ')
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Hanger Tracking</h2>
          <p className="text-sm text-gray-600 mt-1">Real-time monitoring of production hangers</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={updateAllHangers}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Update
          </button>
        </div>
      </div>

      {/* Auto-refresh toggle */}
      <div className="mb-4 flex items-center gap-2">
        <input
          type="checkbox"
          id="hangerAutoRefresh"
          checked={autoRefresh}
          onChange={(e) => setAutoRefresh(e.target.checked)}
          className="w-4 h-4 rounded border-gray-300"
        />
        <label htmlFor="hangerAutoRefresh" className="text-sm text-gray-600">
          Auto-refresh every 10 seconds
        </label>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm mb-4">
          {error}
        </div>
      )}

      {/* Active Hangers Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium">Total Hangers</div>
          <div className="text-2xl font-bold text-blue-900">{hangers.length}</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium">Active</div>
          <div className="text-2xl font-bold text-green-900">{activeHangers.length}</div>
        </div>
        <div className="bg-purple-50 rounded-lg p-4">
          <div className="text-sm text-purple-600 font-medium">Completed</div>
          <div className="text-2xl font-bold text-purple-900">
            {hangers.filter(h => !h.current_bath).length}
          </div>
        </div>
      </div>

      {/* Active Hangers Table */}
      {activeHangers.length > 0 && (
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 text-gray-900">Currently Active</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Hanger #</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Current Bath</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Path</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Pallete</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Entry Time</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody>
                {activeHangers.map((hanger) => (
                  <tr key={hanger.hanger_number} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-3 font-mono font-semibold text-gray-900">
                      {String(hanger.hanger_number).padStart(3, '0')}
                    </td>
                    <td className="py-3 px-3 font-mono font-semibold text-blue-600">
                      {hanger.current_bath !== null ? `Bath[${hanger.current_bath}]` : '—'}
                    </td>
                    <td className="py-3 px-3 text-gray-700 text-xs font-mono">
                      {formatBathPath(hanger.baths_history)}
                    </td>
                    <td className="py-3 px-3 text-gray-700 text-xs font-mono truncate max-w-xs">
                      {hanger.pallete_data || '—'}
                    </td>
                    <td className="py-3 px-3 text-gray-700">
                      {hanger.baths_history.length > 0 ? formatTime(hanger.baths_history[0].in_time) : '—'}
                    </td>
                    <td className="py-3 px-3">
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                        <CheckCircle className="w-3 h-3" />
                        In Progress
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* All Hangers Table */}
      <div>
        <h3 className="text-lg font-semibold mb-3 text-gray-900">All Hangers</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-2 px-3 font-medium text-gray-600">Hanger #</th>
                <th className="text-left py-2 px-3 font-medium text-gray-600">Path Through Baths</th>
                <th className="text-left py-2 px-3 font-medium text-gray-600">Total Baths</th>
                <th className="text-left py-2 px-3 font-medium text-gray-600">Pallete</th>
                <th className="text-left py-2 px-3 font-medium text-gray-600">First Seen</th>
                <th className="text-left py-2 px-3 font-medium text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody>
              {hangers.slice(0, 20).map((hanger) => (
                <tr key={hanger.hanger_number} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 px-3 font-mono font-semibold text-gray-900">
                    {String(hanger.hanger_number).padStart(3, '0')}
                  </td>
                  <td className="py-3 px-3 text-gray-700 text-xs font-mono">
                    {formatBathPath(hanger.baths_history)}
                  </td>
                  <td className="py-3 px-3 text-gray-700 font-semibold">
                    {hanger.total_baths}
                  </td>
                  <td className="py-3 px-3 text-gray-700 text-xs font-mono truncate max-w-xs">
                    {hanger.pallete_data || '—'}
                  </td>
                  <td className="py-3 px-3 text-gray-700 text-xs">
                    {formatTime(hanger.first_seen)}
                  </td>
                  <td className="py-3 px-3">
                    {hanger.current_bath !== null ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                        <CheckCircle className="w-3 h-3" />
                        In Bath {hanger.current_bath}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs font-medium">
                        <Clock className="w-3 h-3" />
                        Completed
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hangers.length > 20 && (
          <p className="text-xs text-gray-500 mt-2">Showing 20 of {hangers.length} hangers</p>
        )}
      </div>
    </div>
  )
}
