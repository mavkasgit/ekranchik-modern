import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle, Loader } from 'lucide-react'

interface OPCUAData {
  available: boolean
  enabled: boolean
  connected: boolean
  state: string
  endpoint?: string
  stats: {
    connections: number
    reads: number
    errors: number
    cache_hits: number
  }
}

export function OPCUAStatus() {
  const [data, setData] = useState<OPCUAData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('/api/opcua/status')
        if (!response.ok) throw new Error('Failed to fetch OPC UA status')
        const data = await response.json()
        setData(data)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-600">
        <Loader className="w-4 h-4 animate-spin" />
        <span>Loading OPC UA status...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-red-600">
        <AlertCircle className="w-4 h-4" />
        <span>{error}</span>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">OPC UA Connection</h3>
        <div className="flex items-center gap-2">
          {data.connected ? (
            <>
              <CheckCircle className="w-5 h-5 text-green-600" />
              <span className="text-green-600 font-medium">Connected</span>
            </>
          ) : (
            <>
              <AlertCircle className="w-5 h-5 text-red-600" />
              <span className="text-red-600 font-medium">Disconnected</span>
            </>
          )}
        </div>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-600">Status:</span>
          <span className="font-medium capitalize">{data.state}</span>
        </div>
        
        {data.endpoint && (
          <div className="flex justify-between">
            <span className="text-gray-600">Endpoint:</span>
            <span className="font-mono text-xs">{data.endpoint}</span>
          </div>
        )}

        <div className="pt-2 border-t border-gray-200 mt-2">
          <div className="text-gray-600 font-medium mb-2">Statistics</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-gray-600">Connections:</span>
              <span className="ml-2 font-medium">{data.stats.connections}</span>
            </div>
            <div>
              <span className="text-gray-600">Reads:</span>
              <span className="ml-2 font-medium">{data.stats.reads}</span>
            </div>
            <div>
              <span className="text-gray-600">Cache Hits:</span>
              <span className="ml-2 font-medium">{data.stats.cache_hits}</span>
            </div>
            <div>
              <span className="text-gray-600">Errors:</span>
              <span className="ml-2 font-medium text-red-600">{data.stats.errors}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
