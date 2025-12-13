import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// Pages will be implemented later
const Dashboard = () => <div className="p-8">Dashboard - Coming Soon</div>
const Catalog = () => <div className="p-8">Catalog - Coming Soon</div>
const Analysis = () => <div className="p-8">Analysis - Coming Soon</div>

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/catalog" element={<Catalog />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
