import { useEffect, useState } from 'react'
import { Loader, AlertCircle, RefreshCw, Search, ChevronRight } from 'lucide-react'

interface GlobalVariable {
  id: string
  name: string
  depth: number
}

interface VariableValue {
  id: string
  value: string
  type: string
}

export function GlobalVariablesList() {
  const [variables, setVariables] = useState<GlobalVariable[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedValues, setExpandedValues] = useState<Record<string, VariableValue>>({})
  const [readingValue, setReadingValue] = useState<string | null>(null)

  const fetchVariables = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/opcua/global-variables')
      if (!response.ok) throw new Error('Failed to fetch global variables')
      const data = await response.json()
      setVariables(data.variables || [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchVariables()
  }, [])

  // Читаем значение переменной по требованию
  const handleReadValue = async (variable: GlobalVariable) => {
    if (expandedValues[variable.id]) {
      // Если уже прочитано, просто скрываем
      setExpandedValues(prev => {
        const newValues = { ...prev }
        delete newValues[variable.id]
        return newValues
      })
      return
    }

    setReadingValue(variable.id)
    try {
      const response = await fetch(`/api/opcua/read-variable?node_id=${encodeURIComponent(variable.id)}`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to read value')
      const data = await response.json()
      setExpandedValues(prev => ({
        ...prev,
        [variable.id]: data
      }))
    } catch (err) {
      setExpandedValues(prev => ({
        ...prev,
        [variable.id]: {
          id: variable.id,
          value: 'Error reading',
          type: 'error'
        }
      }))
    } finally {
      setReadingValue(null)
    }
  }

  // Фильтруем переменные по поисковому запросу
  const filteredVariables = variables.filter(v =>
    v.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    v.id.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Global Variables ({variables.length})</h3>
        <button
          onClick={fetchVariables}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Search */}
      <div className="mb-4 relative">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search variables..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-red-600 mb-4 p-3 bg-red-50 rounded">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <Loader className="w-6 h-6 animate-spin text-blue-600" />
        </div>
      )}

      {/* Variables List */}
      {!loading && filteredVariables.length > 0 && (
        <div className="space-y-1 max-h-96 overflow-y-auto">
          {filteredVariables.map((variable) => (
            <div key={variable.id}>
              <button
                onClick={() => handleReadValue(variable)}
                className="w-full text-left px-3 py-2 hover:bg-gray-50 rounded transition-colors flex items-center gap-2"
              >
                <ChevronRight
                  className={`w-4 h-4 text-gray-400 transition-transform ${
                    expandedValues[variable.id] ? 'rotate-90' : ''
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm text-gray-900 truncate">{variable.name}</div>
                  <div className="text-xs text-gray-500 truncate">{variable.id}</div>
                </div>
                {readingValue === variable.id && (
                  <Loader className="w-4 h-4 animate-spin text-blue-600" />
                )}
              </button>

              {/* Expanded Value */}
              {expandedValues[variable.id] && (
                <div className="ml-6 px-3 py-2 bg-gray-50 rounded text-xs">
                  <div className="mb-1">
                    <span className="text-gray-600">Value:</span>
                    <span className="ml-2 font-mono text-gray-900 break-all">
                      {expandedValues[variable.id].value}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">Type:</span>
                    <span className="ml-2 font-mono text-gray-900">
                      {expandedValues[variable.id].type}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* No results */}
      {!loading && filteredVariables.length === 0 && variables.length > 0 && (
        <div className="text-center py-8 text-gray-500">
          No variables match your search
        </div>
      )}

      {/* Empty state */}
      {!loading && variables.length === 0 && !error && (
        <div className="text-center py-8 text-gray-500">
          No global variables found
        </div>
      )}

      {/* Stats */}
      {!loading && variables.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200 text-xs text-gray-600">
          Showing {filteredVariables.length} of {variables.length} variables
        </div>
      )}
    </div>
  )
}
