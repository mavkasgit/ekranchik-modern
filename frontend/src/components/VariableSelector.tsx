import { useEffect, useState } from 'react'
import { ChevronDown, Loader, AlertCircle } from 'lucide-react'

interface Variable {
  id: string
  name: string
  description: string
  category: string
}

interface VariableValue {
  node_id: string
  value: string
  type: string
}

export function VariableSelector() {
  const [variables, setVariables] = useState<Variable[]>([])
  const [selectedVar, setSelectedVar] = useState<Variable | null>(null)
  const [value, setValue] = useState<VariableValue | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  // Загружаем список переменных при монтировании
  useEffect(() => {
    const fetchVariables = async () => {
      try {
        const response = await fetch('/api/opcua/variables')
        if (!response.ok) throw new Error('Failed to fetch variables')
        const data = await response.json()
        setVariables(data.variables)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }

    fetchVariables()
  }, [])

  // Читаем значение выбранной переменной
  const handleSelectVariable = async (variable: Variable) => {
    setSelectedVar(variable)
    setIsOpen(false)
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`/api/opcua/read-variable?node_id=${encodeURIComponent(variable.id)}`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to read variable')
      const data = await response.json()
      setValue(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setValue(null)
    } finally {
      setLoading(false)
    }
  }

  // Группируем переменные по категориям
  const groupedVariables = variables.reduce((acc, variable) => {
    const category = variable.category
    if (!acc[category]) {
      acc[category] = []
    }
    acc[category].push(variable)
    return acc
  }, {} as Record<string, Variable[]>)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <h3 className="text-lg font-semibold mb-4">Read Variable</h3>

      {/* Dropdown */}
      <div className="relative mb-4">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full px-4 py-2 text-left bg-white border border-gray-300 rounded-lg hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 flex items-center justify-between"
        >
          <span className={selectedVar ? 'text-gray-900' : 'text-gray-500'}>
            {selectedVar ? selectedVar.name : 'Select a variable...'}
          </span>
          <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {/* Dropdown Menu */}
        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-300 rounded-lg shadow-lg z-10 max-h-96 overflow-y-auto">
            {Object.entries(groupedVariables).map(([category, vars]) => (
              <div key={category}>
                <div className="px-4 py-2 bg-gray-100 font-semibold text-sm text-gray-700 sticky top-0">
                  {category}
                </div>
                {vars.map((variable) => (
                  <button
                    key={variable.id}
                    onClick={() => handleSelectVariable(variable)}
                    className="w-full text-left px-4 py-2 hover:bg-blue-50 border-b border-gray-100 last:border-0 transition-colors"
                  >
                    <div className="font-medium text-gray-900">{variable.name}</div>
                    <div className="text-xs text-gray-600">{variable.description}</div>
                    <div className="text-xs text-gray-500 font-mono mt-1">{variable.id}</div>
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-2 text-blue-600 mb-4">
          <Loader className="w-4 h-4 animate-spin" />
          <span className="text-sm">Reading variable...</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-red-600 mb-4 p-3 bg-red-50 rounded">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Value Display */}
      {value && (
        <div className="space-y-3 p-4 bg-gray-50 rounded-lg">
          <div>
            <div className="text-xs text-gray-600 uppercase tracking-wide">Variable</div>
            <div className="font-mono text-sm text-gray-900">{value.node_id}</div>
          </div>

          <div>
            <div className="text-xs text-gray-600 uppercase tracking-wide">Value</div>
            <div className="font-mono text-sm text-gray-900 break-all max-h-32 overflow-y-auto">
              {value.value}
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-600 uppercase tracking-wide">Type</div>
            <div className="font-mono text-sm text-gray-900">{value.type}</div>
          </div>
        </div>
      )}

      {!value && !loading && selectedVar && (
        <div className="p-4 bg-gray-50 rounded-lg text-center text-gray-500 text-sm">
          No value loaded
        </div>
      )}
    </div>
  )
}
