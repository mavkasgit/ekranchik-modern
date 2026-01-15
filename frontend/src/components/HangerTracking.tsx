import { useEffect, useState } from 'react'
import { RefreshCw, CheckCircle, Clock, Zap, AlertCircle } from 'lucide-react'

interface Hanger {
  number: number;
  current_bath: number | string | null;
  baths_visited: (number | string)[];
}

interface OPCUAStatus {
  connected: boolean;
  endpoint: string;
}

export function HangerTracking() {
  const [hangers, setHangers] = useState<Hanger[]>([])
  const [activeHangers, setActiveHangers] = useState<Hanger[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [opcuaStatus, setOpcuaStatus] = useState<OPCUAStatus | null>(null)

  const fetchOPCUAStatus = async () => {
    try {
      const res = await fetch('/api/opcua/status')
      if (res.ok) {
        const data = await res.json()
        setOpcuaStatus(data)
      }
    } catch (err) {
      console.error('Failed to fetch OPC UA status:', err)
    }
  }

  const fetchHangers = async () => {
    setLoading(true)
    try {
      const [allRes, activeRes] = await Promise.all([
        fetch('/api/opcua/hangers'),
        fetch('/api/opcua/hangers/active')
      ])
      
      if (!allRes.ok || !activeRes.ok) {
        const errorText = await allRes.text()
        throw new Error(`Failed to fetch hanger data: ${errorText}`)
      }
      
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

  const scanHangers = async () => {
    try {
      const response = await fetch('/api/opcua/hangers/scan', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to scan hangers')
      await fetchHangers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to scan')
    }
  }

  useEffect(() => {
    fetchOPCUAStatus()
    fetchHangers()
    
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchOPCUAStatus()
        fetchHangers()
      }, 10000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh])

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Hanger Tracking</h2>
          <p className="text-sm text-gray-600 mt-1">Track hangers through production line</p>
          {opcuaStatus && (
            <div className="flex items-center gap-2 mt-2">
              {opcuaStatus.connected ? (
                <>
                  <CheckCircle className="w-4 h-4 text-green-600" />
                  <span className="text-xs text-green-600 font-medium">OPC UA Connected</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-red-600" />
                  <span className="text-xs text-red-600 font-medium">OPC UA Disconnected</span>
                </>
              )}
              <span className="text-xs text-gray-500">({opcuaStatus.endpoint})</span>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={scanHangers}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Scan
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

      {/* Statistics */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium">Total Hangers</div>
          <div className="text-2xl font-bold text-blue-900">{hangers.length}</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium">Active Now</div>
          <div className="text-2xl font-bold text-green-900">{activeHangers.length}</div>
        </div>
        <div className="bg-purple-50 rounded-lg p-4">
          <div className="text-sm text-purple-600 font-medium">Avg Baths/Hanger</div>
          <div className="text-2xl font-bold text-purple-900">
            {hangers.length > 0 ? (hangers.reduce((sum, h) => sum + (h.baths_visited?.length || 0), 0) / hangers.length).toFixed(1) : '—'}
          </div>
        </div>
      </div>

      {/* Active Hangers */}
      {activeHangers.length > 0 && (
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 text-gray-900">Currently Active</h3>
          <div className="space-y-3">
            {activeHangers.filter(Boolean).map((hanger) => (
              <div key={hanger.number} className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-mono font-semibold text-gray-900">
                      Hanger #{String(hanger.number).padStart(3, '0')}
                    </div>
                    <div className="text-sm text-gray-600 mt-1">
                      Currently in Bath #{hanger.current_bath}
                    </div>
                  </div>
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                    <CheckCircle className="w-3 h-3" />
                    Active
                  </span>
                </div>
                <div className="text-xs text-gray-600">
                  Path: {hanger.baths_visited?.map(b => `Bath[${b}]`).join(' → ') || 'No path yet'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Hangers Table */}
      <div>
        <h3 className="text-lg font-semibold mb-3 text-gray-900">All Hangers</h3>
        {hangers.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
            <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600 font-medium mb-1">No hanger data available</p>
            <p className="text-sm text-gray-500">
              {opcuaStatus?.connected 
                ? 'Click "Scan" to detect hangers in the production line' 
                : 'OPC UA is not connected. Check connection settings.'}
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 px-3 font-medium text-gray-600">Hanger #</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">Path Through Baths</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">Total Baths</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {hangers.filter(Boolean).slice(0, 15).map((hanger) => (
                    <tr key={hanger.number} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-3 px-3 font-mono font-semibold text-gray-900">
                        {String(hanger.number).padStart(3, '0')}
                      </td>
                      <td className="py-3 px-3 text-xs text-gray-700 font-mono">
                        {hanger.baths_visited?.map(b => `[${b}]`).join(' → ') || 'No path yet'}
                      </td>
                      <td className="py-3 px-3 text-gray-700 font-semibold">
                        {hanger.baths_visited?.length || 0}
                      </td>
                      <td className="py-3 px-3">
                        {hanger.current_bath !== null ? (
                          <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                            <Zap className="w-3 h-3" />
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
            {hangers.length > 15 && (
              <p className="text-xs text-gray-500 mt-2">Showing 15 of {hangers.length} hangers</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

