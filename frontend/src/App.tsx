import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { LayoutDashboard, BookOpen, Gauge } from 'lucide-react'
import { useState, createContext, useContext, useEffect } from 'react'
import { Toaster } from '@/components/ui/toaster'
import Dashboard from '@/pages/Dashboard'
import Catalog from '@/pages/Catalog'
import { OPCUAPage } from '@/pages/OPCUAPage'
import { useRealtimeBridge } from '@/hooks/useRealtime'

// Fullscreen context
const FullscreenContext = createContext({
  isFullscreen: false,
  setIsFullscreen: (_: boolean) => {},
})

export const useFullscreen = () => useContext(FullscreenContext)

function Navigation() {
  const { isFullscreen } = useFullscreen()
  
  const links = [
    { to: '/', icon: LayoutDashboard, label: 'Дашборд' },
    { to: '/catalog', icon: BookOpen, label: 'Каталог' },
    { to: '/opcua', icon: Gauge, label: 'OPC UA' },
  ]

  // Hide navigation in fullscreen
  if (isFullscreen) return null

  return (
    <header className="border-b bg-card">
      <div className="container mx-auto px-6 h-14 flex items-center justify-between">
        <nav className="flex items-center gap-1">
          {links.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors
                ${isActive 
                  ? 'bg-primary text-primary-foreground' 
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
function Footer() {
  const { isFullscreen } = useFullscreen()
  const [backendVersion, setBackendVersion] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/version')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && typeof d.version === 'string') setBackendVersion(d.version)
      })
      .catch(() => {})
  }, [])

  // Hide footer in fullscreen
  if (isFullscreen) return null

  return (
    <footer className="border-t bg-card">
      <div className="container mx-auto px-6 h-10 flex items-center justify-end gap-2 text-xs text-muted-foreground">
        <span>v{__APP_VERSION__}</span>
        {backendVersion && <span>· API v{backendVersion}</span>}
      </div>
    </footer>
  )
}


function App() {
  const [isFullscreen, setIsFullscreen] = useState(false)
  useRealtimeBridge()

  return (
    <FullscreenContext.Provider value={{ isFullscreen, setIsFullscreen }}>
      <BrowserRouter>
        <div className="min-h-screen bg-background">
          <Navigation />
          <main>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route path="/opcua" element={<OPCUAPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <Footer />
        </div>
        <Toaster />
      </BrowserRouter>
    </FullscreenContext.Provider>
  )
}

export default App
