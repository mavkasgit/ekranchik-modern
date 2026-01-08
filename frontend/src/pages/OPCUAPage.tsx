import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle, Loader, RefreshCw, Activity, Zap, Clock, Settings } from 'lucide-react'
import { LineVisualization } from '@/components/LineVisualization'
import { HangerTracking } from '@/components/HangerTracking'

interface PLCData {
  status: string
  server_time: string
  num_vars?: number
  num_values?: number
  device_status?: string
  connected: boolean
}

interface OPCUAStatus {
  available: boolean
  enabled: boolean
  connected: boolean
  state: string
  endpoint?: string
  stats: {
    reads: number
    errors: number
    reconnects: number
  }
}

export function OPCUAPage() {
  const [data, setData] = useState<PLCData | null>(null)
  const [status, setStatus] = useState<OPCUAStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'line' | 'hangers' | 'settings'>('line')

  const fetchData = async () => {
    try {
      const [dataRes, statusRes] = await Promise.all([
        fetch('/api/opcua/data'),
        fetch('/api/opcua/status')
      ])
      
      if (dataRes.ok) {
        const plcData = await dataRes.json()
        setData(plcData)
      }
      
      if (statusRes.ok) {
        const statusData = await statusRes.json()
        setStatus(statusData)
      }
      
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleConnect = async () => {
    try {
      const response = await fetch('/api/opcua/connect', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to connect')
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed')
    }
  }

  const handleDisconnect = async () => {
    try {
      await fetch('/api/opcua/disconnect', { method: 'POST' })
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Disconnect failed')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">OPC UA Monitor</h1>
            <p className="text-gray-600 mt-1">Galvanic Line Real-time Monitoring</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Connection Status */}
            <div className={`flex items-center gap-2 px-4 py-2 rounded-lg ${
              status?.connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}>
              {loading ? (
                <Loader className="w-4 h-4 animate-spin" />
              ) : status?.connected ? (
                <CheckCircle className="w-4 h-4" />
              ) : (
                <AlertCircle className="w-4 h-4" />
              )}
              <span className="font-medium">
                {status?.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            
            {/* Connect/Disconnect Button */}
            {status?.connected ? (
              <button
                onClick={handleDisconnect}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
              >
                Disconnect
              </button>
            ) : (
              <button
                onClick={handleConnect}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Connect
              </button>
            )}
            
            <button
              onClick={fetchData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600" />
            <span className="text-red-700">{error}</span>
          </div>
        )}

        {/* Quick Stats */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600">Server Time</span>
              <Clock className="w-4 h-4 text-gray-400" />
            </div>
            <div className="text-lg font-mono text-gray-900">
              {data?.server_time ? new Date(data.server_time).toLocaleTimeString() : '—'}
            </div>
          </div>
          
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600">Total Variables</span>
              <Zap className="w-4 h-4 text-blue-500" />
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {data?.num_vars ?? '—'}
            </div>
          </div>
          
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600">Active Values</span>
              <Activity className="w-4 h-4 text-green-500" />
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {data?.num_values ?? '—'}
            </div>
          </div>
          
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600">Read Operations</span>
              <Activity className="w-4 h-4 text-purple-500" />
            </div>
            <div className="text-2xl font-bold text-gray-900">
              {status?.stats?.reads ?? '—'}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('line')}
            className={`px-6 py-3 rounded-lg font-medium transition-colors ${
              activeTab === 'line'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            Production Line
          </button>
          <button
            onClick={() => setActiveTab('hangers')}
            className={`px-6 py-3 rounded-lg font-medium transition-colors ${
              activeTab === 'hangers'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            Hanger Tracking
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`px-6 py-3 rounded-lg font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'settings'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            <Settings className="w-4 h-4" />
            Settings
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'line' && <LineVisualization />}
        
        {activeTab === 'hangers' && <HangerTracking />}
        
        {activeTab === 'settings' && (
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-6">OPC UA Settings</h2>
            
            <div className="space-y-6">
              {/* Connection Info */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Connection</h3>
                <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Endpoint:</span>
                    <span className="font-mono text-sm">{status?.endpoint || 'opc.tcp://172.17.11.131:4840'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">State:</span>
                    <span className={`font-medium ${status?.connected ? 'text-green-600' : 'text-red-600'}`}>
                      {status?.state || 'Unknown'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Available:</span>
                    <span>{status?.available ? 'Yes' : 'No'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Enabled:</span>
                    <span>{status?.enabled ? 'Yes' : 'No'}</span>
                  </div>
                </div>
              </div>
              
              {/* Statistics */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Statistics</h3>
                <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Reads:</span>
                    <span className="font-mono">{status?.stats?.reads ?? 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Errors:</span>
                    <span className="font-mono text-red-600">{status?.stats?.errors ?? 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Reconnects:</span>
                    <span className="font-mono">{status?.stats?.reconnects ?? 0}</span>
                  </div>
                </div>
              </div>
              
              {/* Line Configuration */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Line Configuration</h3>
                <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Baths:</span>
                    <span className="font-mono">39 (Bath[1] - Bath[39])</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Control Point (Exit):</span>
                    <span className="font-mono text-orange-600">Bath[34]</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Power Supply:</span>
                    <span className="font-mono">S8VK_X</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Info Card */}
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="font-semibold text-blue-900 mb-2">About Line Monitoring</h3>
          <p className="text-sm text-blue-800">
            This page displays real-time data from the galvanic production line via OPC UA.
            The line consists of 39 baths. Pallets enter at Bath[1] and exit at Bath[34] (control point).
            Colors indicate bath status: green (active, normal), yellow (70-90% time), red (90%+ time).
          </p>
        </div>
      </div>
    </div>
  )
}
