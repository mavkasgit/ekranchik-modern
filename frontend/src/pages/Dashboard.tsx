import { useState, useEffect, useCallback, useRef } from 'react'
import { 
  RefreshCw, Wifi, WifiOff, FileSpreadsheet, Server, 
  Image, Maximize2, Minimize2, X, ZoomIn, ZoomOut 
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import { useDashboard, useFileStatus, useFTPStatus } from '@/hooks/useDashboard'
import { useRealtimeData } from '@/hooks/useRealtimeData'
import type { HangerData, ProfileInfo } from '@/types/dashboard'

// localStorage keys
const FILTERS_KEY = 'ekranchik_filters'

interface Filters {
  loadingLimit: number
  unloadingLimit: number
  realtimeLimit: number
  showLoading: boolean
  showUnloading: boolean
  showRealtime: boolean
}

const defaultFilters: Filters = {
  loadingLimit: 10,
  unloadingLimit: 10,
  realtimeLimit: 10,
  showLoading: true,
  showUnloading: false,
  showRealtime: true,
}

function loadFilters(): Filters {
  try {
    const saved = localStorage.getItem(FILTERS_KEY)
    if (saved) return { ...defaultFilters, ...JSON.parse(saved) }
  } catch {}
  return defaultFilters
}

function saveFilters(filters: Filters) {
  localStorage.setItem(FILTERS_KEY, JSON.stringify(filters))
}

// Photo Modal with zoom/pan
function PhotoModal({
  open,
  onClose,
  photoUrl,
  profileName,
}: {
  open: boolean
  onClose: () => void
  photoUrl: string | null
  profileName: string
}) {
  const [zoom, setZoom] = useState(1)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    if (open) {
      setZoom(1)
      setPosition({ x: 0, y: 0 })
    }
  }, [open])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.2 : 0.2
    setZoom(z => Math.max(0.5, Math.min(5, z + delta)))
  }, [])

  const handleDoubleClick = useCallback(() => {
    if (zoom === 1) {
      setZoom(2.5)
    } else {
      setZoom(1)
      setPosition({ x: 0, y: 0 })
    }
  }, [zoom])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (zoom > 1) {
      setIsDragging(true)
      dragStart.current = { x: e.clientX - position.x, y: e.clientY - position.y }
    }
  }, [zoom, position])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setPosition({
        x: e.clientX - dragStart.current.x,
        y: e.clientY - dragStart.current.y,
      })
    }
  }, [isDragging])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open || !photoUrl) return null

  return (
    <div 
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      <div 
        className="relative max-w-[90vw] max-h-[90vh]"
        onClick={e => e.stopPropagation()}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <button 
          className="absolute -top-10 right-0 text-white text-4xl hover:text-red-400"
          onClick={onClose}
        >
          <X />
        </button>
        <img
          ref={imgRef}
          src={photoUrl}
          alt={profileName}
          className="max-w-full max-h-[85vh] rounded-lg select-none"
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
            cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'zoom-in',
            transition: isDragging ? 'none' : 'transform 0.15s ease-out',
          }}
          onDoubleClick={handleDoubleClick}
          draggable={false}
        />
        <div className="absolute -bottom-10 left-0 text-white text-lg">
          {profileName}
        </div>
        <div className="absolute -bottom-10 right-0 flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => setZoom(z => Math.max(0.5, z - 0.5))}>
            <ZoomOut className="w-4 h-4" />
          </Button>
          <span className="text-white px-2">{Math.round(zoom * 100)}%</span>
          <Button size="sm" variant="secondary" onClick={() => setZoom(z => Math.min(5, z + 0.5))}>
            <ZoomIn className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

// Profile photos cell with multiple photos support
function PhotoCell({ 
  hanger, 
  onPhotoClick 
}: { 
  hanger: HangerData
  onPhotoClick: (url: string, name: string) => void 
}) {
  const profilesInfo = hanger.profiles_info || []
  
  if (profilesInfo.length > 0) {
    return (
      <div className="flex flex-wrap gap-2 justify-center">
        {profilesInfo.map((prof, idx) => (
          <ProfilePhoto 
            key={idx} 
            profile={prof} 
            onPhotoClick={onPhotoClick} 
          />
        ))}
      </div>
    )
  }

  // Fallback to single photo
  if (hanger.profile_photo_thumb) {
    return (
      <img
        src={`/static/${hanger.profile_photo_thumb}`}
        alt={hanger.profile}
        className="w-20 h-20 object-contain rounded cursor-pointer hover:scale-105 transition-transform border-2 border-gray-200 hover:border-blue-500"
        onClick={() => onPhotoClick(
          `/static/${hanger.profile_photo_full || hanger.profile_photo_thumb}`,
          hanger.profile
        )}
      />
    )
  }

  return (
    <div className="w-20 h-20 bg-muted rounded flex items-center justify-center">
      <Image className="w-8 h-8 text-muted-foreground" />
    </div>
  )
}

function ProfilePhoto({ 
  profile, 
  onPhotoClick 
}: { 
  profile: ProfileInfo
  onPhotoClick: (url: string, name: string) => void 
}) {
  if (!profile.has_photo || !profile.photo_thumb) {
    return null
  }

  return (
    <div className="text-center">
      <img
        src={`/static/${profile.photo_thumb}`}
        alt={profile.name}
        className="w-24 h-24 object-contain rounded cursor-pointer hover:scale-105 transition-transform border-2 border-gray-200 hover:border-blue-500"
        onClick={() => onPhotoClick(
          `/static/${profile.photo_full || profile.photo_thumb}`,
          profile.canonical_name || profile.name
        )}
      />
      <p className="text-xs text-muted-foreground mt-1 max-w-24 truncate">
        {profile.canonical_name || profile.name}
      </p>
      {profile.processing && profile.processing.length > 0 && (
        <div className="flex gap-1 justify-center mt-1 flex-wrap">
          {profile.processing.map((proc, i) => (
            <Badge key={i} className="text-[10px] px-1 py-0 bg-yellow-400 text-yellow-900">
              {proc}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

// Compact status bar - Excel → FTP → WebSocket
function StatusBar() {
  const { data: fileStatus } = useFileStatus()
  const { data: ftpStatus } = useFTPStatus()
  const { isConnected } = useRealtimeData()

  const fileIsOpen = fileStatus?.is_open
  
  return (
    <div className="bg-card rounded-lg p-3 shadow-sm border flex flex-wrap items-center gap-4 text-sm">
      {/* Excel file */}
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="w-4 h-4 text-muted-foreground" />
        <div className={`w-2 h-2 rounded-full animate-pulse ${fileStatus?.error ? 'bg-yellow-500' : fileIsOpen ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className="truncate max-w-[200px]">{fileStatus?.file_name || '—'}</span>
        {fileStatus?.last_modified && (
          <span className="text-muted-foreground text-xs">
            {new Date(fileStatus.last_modified).toLocaleString('ru')}
          </span>
        )}
      </div>

      <div className="w-px h-4 bg-border" />

      {/* FTP */}
      <div className="flex items-center gap-2">
        <Server className="w-4 h-4 text-muted-foreground" />
        <div className={`w-2 h-2 rounded-full ${ftpStatus?.connected ? 'bg-green-500' : 'bg-red-500'}`} />
        <span>FTP: {ftpStatus?.connected ? 'OK' : 'Откл'}</span>
      </div>

      <div className="w-px h-4 bg-border" />

      {/* WebSocket */}
      <div className="flex items-center gap-2">
        {isConnected ? (
          <Wifi className="w-4 h-4 text-green-500" />
        ) : (
          <WifiOff className="w-4 h-4 text-red-500" />
        )}
        <span className={isConnected ? 'text-green-600' : 'text-muted-foreground'}>
          WS: {isConnected ? 'Онлайн' : 'Офлайн'}
        </span>
      </div>
    </div>
  )
}

// Data table component
function DataTable({ 
  data, 
  onPhotoClick,
  highlightNew = false,
  newIds = new Set<string>(),
}: { 
  data: HangerData[]
  onPhotoClick: (url: string, name: string) => void
  highlightNew?: boolean
  newIds?: Set<string>
}) {
  return (
    <div className="rounded-md border overflow-auto max-h-[500px]">
      <Table>
        <TableHeader className="sticky top-0 bg-muted z-10">
          <TableRow>
            <TableHead className="w-24">Дата</TableHead>
            <TableHead className="w-20">Время</TableHead>
            <TableHead className="w-20">№ Подв.</TableHead>
            <TableHead className="w-20">Тип</TableHead>
            <TableHead className="w-24">№ КПЗ</TableHead>
            <TableHead>Клиент</TableHead>
            <TableHead className="max-w-[200px]">Профиль</TableHead>
            <TableHead className="w-32">Фото</TableHead>
            <TableHead className="w-20 text-right">Ламели</TableHead>
            <TableHead>Цвет</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((hanger, idx) => {
            const rowId = `${hanger.number}-${hanger.date}-${hanger.time}`
            const isNew = highlightNew && newIds.has(rowId)
            
            return (
              <TableRow 
                key={`${hanger.number}-${idx}`}
                className={`
                  ${idx % 2 === 0 ? 'bg-slate-50' : 'bg-white'}
                  hover:bg-blue-50 transition-colors
                  ${isNew ? 'bg-yellow-100 animate-pulse' : ''}
                `}
              >
                <TableCell>{hanger.date}</TableCell>
                <TableCell>{hanger.time}</TableCell>
                <TableCell className="font-bold">{hanger.number}</TableCell>
                <TableCell>{hanger.material_type}</TableCell>
                <TableCell>{hanger.kpz_number}</TableCell>
                <TableCell className="truncate max-w-[150px]">{hanger.client}</TableCell>
                <TableCell className="max-w-[200px]">
                  <span className="break-words">{hanger.profile?.replace(/\+/g, '+ ') || '—'}</span>
                </TableCell>
                <TableCell>
                  <PhotoCell hanger={hanger} onPhotoClick={onPhotoClick} />
                </TableCell>
                <TableCell className="text-right font-bold">{hanger.lamels_qty}</TableCell>
                <TableCell>
                  <Badge variant="outline">{hanger.color}</Badge>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[...Array(5)].map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  )
}

// Filters component
function FiltersPanel({
  filters,
  onChange,
  onApply,
  onReset,
}: {
  filters: Filters
  onChange: (filters: Filters) => void
  onApply: () => void
  onReset: () => void
}) {
  return (
    <Card className="mb-4">
      <CardContent className="pt-4">
        <div className="flex flex-wrap gap-4 items-center">
          {/* Loading filter */}
          <div className="flex items-center gap-2 bg-blue-50 border-2 border-blue-300 rounded-lg px-3 py-2">
            <input
              type="checkbox"
              id="show-loading"
              checked={filters.showLoading}
              onChange={e => onChange({ ...filters, showLoading: e.target.checked })}
              className="w-4 h-4"
            />
            <label htmlFor="show-loading" className="text-sm font-medium cursor-pointer">
              Загрузка:
            </label>
            <Input
              type="number"
              value={filters.loadingLimit}
              onChange={e => onChange({ ...filters, loadingLimit: Number(e.target.value) })}
              className="w-20 h-8"
              min={1}
              max={500}
            />
          </div>

          {/* Realtime filter */}
          <div className="flex items-center gap-2 bg-green-50 border-2 border-green-300 rounded-lg px-3 py-2">
            <input
              type="checkbox"
              id="show-realtime"
              checked={filters.showRealtime}
              onChange={e => onChange({ ...filters, showRealtime: e.target.checked })}
              className="w-4 h-4"
            />
            <label htmlFor="show-realtime" className="text-sm font-medium cursor-pointer">
              Выгрузка:
            </label>
            <Input
              type="number"
              value={filters.realtimeLimit}
              onChange={e => onChange({ ...filters, realtimeLimit: Number(e.target.value) })}
              className="w-20 h-8"
              min={1}
              max={500}
            />
          </div>

          {/* Unloading filter */}
          <div className="flex items-center gap-2 bg-pink-50 border-2 border-pink-300 rounded-lg px-3 py-2">
            <input
              type="checkbox"
              id="show-unloading"
              checked={filters.showUnloading}
              onChange={e => onChange({ ...filters, showUnloading: e.target.checked })}
              className="w-4 h-4"
            />
            <label htmlFor="show-unloading" className="text-sm font-medium cursor-pointer">
              Выгрузка старая:
            </label>
            <Input
              type="number"
              value={filters.unloadingLimit}
              onChange={e => onChange({ ...filters, unloadingLimit: Number(e.target.value) })}
              className="w-20 h-8"
              min={1}
              max={500}
            />
          </div>

          {/* Quick show last 100 button */}
          <Button 
            variant="outline"
            onClick={() => onChange({ 
              ...filters, 
              showLoading: true,
              showRealtime: false,
              showUnloading: false,
              loadingLimit: 100
            })}
          >
            Последние 100
          </Button>

          <div className="flex gap-2 ml-auto">
            <Button onClick={onApply}>Применить</Button>
            <Button variant="secondary" onClick={onReset}>Сбросить</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Main Dashboard component
export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>(loadFilters)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [photoModal, setPhotoModal] = useState<{ url: string; name: string } | null>(null)
  const [realtimeData, setRealtimeData] = useState<HangerData[]>([])
  const [newRowIds, setNewRowIds] = useState<Set<string>>(new Set())
  
  const { data, isLoading, refetch, isFetching } = useDashboard(7, filters.loadingLimit)
  
  // WebSocket for realtime updates
  useRealtimeData({
    onMessage: (msg) => {
      if (msg.type === 'unload_event' && msg.payload) {
        const newHanger = msg.payload as unknown as HangerData
        const rowId = `${newHanger.number}-${newHanger.date}-${newHanger.time}`
        
        setRealtimeData(prev => {
          const updated = [newHanger, ...prev].slice(0, filters.realtimeLimit)
          return updated
        })
        
        // Highlight new row
        setNewRowIds(prev => new Set([...prev, rowId]))
        setTimeout(() => {
          setNewRowIds(prev => {
            const next = new Set(prev)
            next.delete(rowId)
            return next
          })
        }, 5000)
      }
    }
  })

  // Save filters on change
  useEffect(() => {
    saveFilters(filters)
  }, [filters])

  // Fullscreen handling
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }, [])

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  const handlePhotoClick = useCallback((url: string, name: string) => {
    setPhotoModal({ url, name })
  }, [])

  const handleApplyFilters = useCallback(() => {
    refetch()
  }, [refetch])

  const handleResetFilters = useCallback(() => {
    setFilters(defaultFilters)
    refetch()
  }, [refetch])

  return (
    <div className={`${isFullscreen ? 'p-2' : 'container mx-auto p-6'} space-y-4`}>
      {/* Header */}
      {!isFullscreen && (
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">📊 Учет КПЗ - Подвесы</h1>
          <div className="flex items-center gap-4">
            <div className="flex gap-2 text-sm">
              <Badge variant="secondary">
                📦 Всего: <strong>{data?.total_all ?? '—'}</strong>
              </Badge>
              <Badge variant="outline" className="bg-yellow-50">
                🔍 Показано: <strong>{data?.total ?? '—'}</strong>
              </Badge>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`w-4 h-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
            <Button variant="outline" size="sm" onClick={toggleFullscreen}>
              {isFullscreen ? <Minimize2 className="w-4 h-4 mr-1" /> : <Maximize2 className="w-4 h-4 mr-1" />}
              {isFullscreen ? 'Свернуть' : 'На весь экран'}
            </Button>
          </div>
        </div>
      )}

      {/* Fullscreen exit button */}
      {isFullscreen && (
        <div className="fixed top-2 right-2 z-50">
          <Button variant="secondary" size="sm" onClick={toggleFullscreen}>
            <X className="w-4 h-4 mr-1" /> Выход
          </Button>
        </div>
      )}

      {/* Status bar */}
      {!isFullscreen && <StatusBar />}

      {/* Filters */}
      {!isFullscreen && (
        <FiltersPanel
          filters={filters}
          onChange={setFilters}
          onApply={handleApplyFilters}
          onReset={handleResetFilters}
        />
      )}

      {/* Tables */}
      <div className="space-y-4">
        {/* Loading table */}
        {filters.showLoading && (
          <Card className="border-l-4 border-l-blue-500">
            <CardHeader className="py-3 bg-slate-50">
              <CardTitle className="text-base">ЗАГРУЗКА</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-4"><TableSkeleton /></div>
              ) : data?.products && data.products.length > 0 ? (
                <DataTable data={data.products} onPhotoClick={handlePhotoClick} />
              ) : (
                <div className="p-8 text-center text-muted-foreground">Нет записей</div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Realtime unloading table */}
        {filters.showRealtime && (
          <Card className="border-l-4 border-l-green-500">
            <CardHeader className="py-3 bg-green-50">
              <CardTitle className="text-base">ВЫГРУЗКА (реальное время)</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {realtimeData.length > 0 ? (
                <DataTable 
                  data={realtimeData} 
                  onPhotoClick={handlePhotoClick}
                  highlightNew
                  newIds={newRowIds}
                />
              ) : (
                <div className="p-8 text-center text-muted-foreground">
                  Ожидание событий выгрузки...
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Old unloading table */}
        {filters.showUnloading && (
          <Card className="border-l-4 border-l-pink-500">
            <CardHeader className="py-3 bg-pink-50">
              <CardTitle className="text-base">ВЫГРУЗКА СТАРАЯ</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {data?.unloading_products && data.unloading_products.length > 0 ? (
                <DataTable data={data.unloading_products} onPhotoClick={handlePhotoClick} />
              ) : (
                <div className="p-8 text-center text-muted-foreground">Нет записей</div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Photo modal */}
      <PhotoModal
        open={!!photoModal}
        onClose={() => setPhotoModal(null)}
        photoUrl={photoModal?.url || null}
        profileName={photoModal?.name || ''}
      />
    </div>
  )
}
