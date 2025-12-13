import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  RefreshCw, Wifi, WifiOff, FileSpreadsheet, Server,
  Image, Maximize2, Minimize2, X, ZoomIn, ZoomOut, Loader2
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
} from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { useToast } from '@/hooks/use-toast'

import { useDashboard, useFileStatus, useFTPStatus } from '@/hooks/useDashboard'
import { useRealtimeData } from '@/hooks/useRealtimeData'
import type { HangerData, ProfileInfo } from '@/types/dashboard'

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
  } catch { /* ignore */ }
  return defaultFilters
}

function saveFilters(filters: Filters) {
  localStorage.setItem(FILTERS_KEY, JSON.stringify(filters))
}

// Color mapping - top 15 most used colors
function getColorHex(colorName: string): string {
  const name = colorName.toLowerCase().trim()
  
  const colorMap: Record<string, string> = {
    // Top colors by usage
    'серебро': '#C0C0C0',      // 16147 uses
    'черный': '#1C1C1C',       // 8323 uses
    'золото': '#FFD700',       // 1758 uses
    'шампань': '#F7E7CE',      // 1605 uses
    'титан': '#878681',        // 1498 uses
    'бронза': '#8B5A2B',       // 360 uses - darker bronze
    'медь': '#CD5C5C',         // 335 uses - more red copper
    'растрав': '#D3D3D3',      // 127 uses
    'rosegold': '#B76E79',     // 126 uses
  }
  
  // Try exact match
  if (colorMap[name]) return colorMap[name]
  
  // Try partial match
  for (const [key, value] of Object.entries(colorMap)) {
    if (name.includes(key) || key.includes(name)) return value
  }
  
  // Default gray for unknown
  return '#9CA3AF'
}

// Photo Modal - same as Catalog ProfileDialog view mode
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
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)
  const [zoom, setZoom] = useState(1)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStart = useRef({ x: 0, y: 0 })

  // Load image dimensions
  useEffect(() => {
    setImageSize(null)
    if (!photoUrl) return
    
    const img = new window.Image()
    img.onload = () => {
      setImageSize({ width: img.naturalWidth, height: img.naturalHeight })
    }
    img.src = photoUrl
    
    return () => { img.onload = null }
  }, [photoUrl])

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

  const handleMouseUp = useCallback(() => setIsDragging(false), [])

  // Calculate dialog size based on image dimensions (like Catalog)
  const dialogSize = useMemo(() => {
    const maxDialogHeight = typeof window !== 'undefined' ? window.innerHeight - 100 : 800
    const maxDialogWidth = typeof window !== 'undefined' ? window.innerWidth - 100 : 1200
    const minHeight = 400
    const minWidth = 500
    
    if (!imageSize) {
      return { width: minWidth, height: minHeight }
    }
    
    let imgDisplayWidth = imageSize.width
    let imgDisplayHeight = imageSize.height
    
    // Scale down if image is too tall
    if (imgDisplayHeight > maxDialogHeight - 80) { // 80px for controls
      const scale = (maxDialogHeight - 80) / imgDisplayHeight
      imgDisplayWidth = imgDisplayWidth * scale
      imgDisplayHeight = imgDisplayHeight * scale
    }
    
    // Scale down if too wide
    if (imgDisplayWidth > maxDialogWidth - 40) { // 40px padding
      const scale = (maxDialogWidth - 40) / imgDisplayWidth
      imgDisplayWidth = imgDisplayWidth * scale
      imgDisplayHeight = imgDisplayHeight * scale
    }
    
    return {
      width: Math.max(minWidth, imgDisplayWidth + 40),
      height: Math.max(minHeight, imgDisplayHeight + 100) // 100px for controls
    }
  }, [imageSize])

  if (!photoUrl) return null

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent 
        className="p-0 gap-0 top-[5%] translate-y-0 bg-background/95 backdrop-blur"
        style={{ width: `${dialogSize.width}px`, height: `${dialogSize.height}px`, maxWidth: 'calc(100vw - 100px)' }}
      >
        <div
          className="relative flex flex-col items-center justify-center h-full p-4"
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <div className="flex-1 flex items-center justify-center overflow-hidden w-full">
            <img
              src={photoUrl}
              alt={profileName}
              className="max-w-full max-h-full object-contain select-none"
              style={{
                transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
                cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'zoom-in',
                transition: isDragging ? 'none' : 'transform 0.15s ease-out',
              }}
              onDoubleClick={handleDoubleClick}
              draggable={false}
            />
          </div>
          <div className="flex items-center justify-between w-full pt-4 border-t mt-4">
            <span className="text-lg font-medium">{profileName}</span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => setZoom(z => Math.max(0.5, z - 0.5))}>
                <ZoomOut className="w-4 h-4" />
              </Button>
              <span className="text-sm w-12 text-center">{Math.round(zoom * 100)}%</span>
              <Button size="sm" variant="outline" onClick={() => setZoom(z => Math.min(5, z + 0.5))}>
                <ZoomIn className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// Helper to build photo URL (paths in DB already include /static/)
function getPhotoUrl(path: string | null | undefined): string | null {
  if (!path) return null
  // Paths in DB are like "/static/images/..." or "images/..."
  return path.startsWith('/') ? path : `/${path}`
}

// Photo cell - wrapping layout, max 700px width, photos wrap to new rows
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
      <div className="flex flex-wrap gap-2 items-center justify-center" style={{ maxWidth: '800px' }}>
        {profilesInfo.map((prof, idx) => (
          <ProfilePhoto key={idx} profile={prof} onPhotoClick={onPhotoClick} />
        ))}
      </div>
    )
  }

  const thumbUrl = getPhotoUrl(hanger.profile_photo_thumb)
  if (thumbUrl) {
    return (
      <div className="flex items-center justify-center" style={{ maxWidth: '800px' }}>
        <img
          src={thumbUrl}
          alt={hanger.profile}
          className="w-20 h-20 object-contain rounded cursor-pointer hover:scale-105 transition-transform border border-border hover:border-primary"
          onClick={() => onPhotoClick(
            getPhotoUrl(hanger.profile_photo_full || hanger.profile_photo_thumb) || '',
            hanger.profile
          )}
        />
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center" style={{ maxWidth: '800px' }}>
      <div className="w-20 h-20 bg-muted rounded flex items-center justify-center">
        <Image className="w-8 h-8 text-muted-foreground" />
      </div>
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
  const thumbUrl = getPhotoUrl(profile.photo_thumb)
  const fullUrl = getPhotoUrl(profile.photo_full || profile.photo_thumb)
  const hasPhoto = profile.has_photo && thumbUrl

  return (
    <div className="flex items-center gap-2">
      {hasPhoto ? (
        <img
          src={thumbUrl}
          alt={profile.name}
          className="w-auto max-h-[80px] max-w-[140px] object-contain rounded cursor-pointer hover:scale-105 transition-transform border border-border hover:border-primary flex-shrink-0"
          onClick={() => onPhotoClick(fullUrl || '', profile.canonical_name || profile.name)}
        />
      ) : (
        <div className="w-12 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
          <Image className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
      <div className="flex flex-col justify-center min-w-0">
        <p className="text-xs text-muted-foreground truncate max-w-[100px]">
          {profile.canonical_name || profile.name}
        </p>
        {profile.processing && profile.processing.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {profile.processing.map((proc, i) => (
              <Badge key={i} className="text-[10px] px-1 py-0 bg-yellow-400 text-yellow-900 hover:bg-yellow-500">
                {proc}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Status bar
function StatusBar() {
  const { data: fileStatus } = useFileStatus()
  const { data: ftpStatus } = useFTPStatus()
  const { isConnected } = useRealtimeData()

  const fileIsOpen = fileStatus?.is_open
  const statusColor = fileStatus?.error 
    ? 'bg-yellow-500' 
    : fileIsOpen 
      ? 'bg-green-500' 
      : 'bg-destructive'

  return (
    <Card>
      <CardContent className="py-3">
        <div className="flex flex-wrap items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-muted-foreground" />
            <div className={`w-2 h-2 rounded-full ${statusColor}`} />
            <span className="font-medium">{fileStatus?.status_text || '—'}</span>
            <span className="text-muted-foreground truncate max-w-[200px]">
              {fileStatus?.file_name || ''}
            </span>
            {fileStatus?.last_modified && (
              <span className="text-muted-foreground text-xs">
                {new Date(fileStatus.last_modified).toLocaleString('ru')}
              </span>
            )}
          </div>

          <div className="w-px h-4 bg-border" />

          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-muted-foreground" />
            <div className={`w-2 h-2 rounded-full ${ftpStatus?.connected ? 'bg-green-500' : 'bg-destructive'}`} />
            <span>FTP: {ftpStatus?.connected ? 'OK' : 'Откл'}</span>
          </div>

          <div className="w-px h-4 bg-border" />

          <div className="flex items-center gap-2">
            {isConnected ? (
              <Wifi className="w-4 h-4 text-green-500" />
            ) : (
              <WifiOff className="w-4 h-4 text-destructive" />
            )}
            <span>WS: {isConnected ? 'Онлайн' : 'Офлайн'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Update row with progress bar
function UpdateRow({ progress }: { progress: number }) {
  return (
    <TableRow className="bg-blue-500/10 border-blue-500/30">
      <TableCell colSpan={10} className="py-2">
        <div className="flex items-center justify-center gap-3">
          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
          <span className="text-sm font-medium text-blue-500">Обновление данных...</span>
          <div className="w-[200px] h-2 bg-muted rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-500 transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-10">{Math.round(progress)}%</span>
        </div>
      </TableCell>
    </TableRow>
  )
}

// Data table
function DataTable({
  data,
  onPhotoClick,
  highlightNew = false,
  newIds = new Set<string>(),
  isUpdating = false,
  isFullscreen = false,
}: {
  data: HangerData[]
  onPhotoClick: (url: string, name: string) => void
  highlightNew?: boolean
  newIds?: Set<string>
  isUpdating?: boolean
  isFullscreen?: boolean
}) {
  const [progress, setProgress] = useState(0)
  
  // Fake progress animation
  useEffect(() => {
    if (isUpdating) {
      setProgress(0)
      const interval = setInterval(() => {
        setProgress(p => {
          if (p >= 90) return p // Stop at 90%, wait for real completion
          return p + Math.random() * 15
        })
      }, 200)
      return () => clearInterval(interval)
    } else {
      // Complete to 100% when done
      if (progress > 0 && progress < 100) {
        setProgress(100)
        setTimeout(() => setProgress(0), 500)
      }
    }
  }, [isUpdating])

  return (
    <div className={`overflow-auto text-xs ${isFullscreen ? 'max-h-screen' : 'rounded-md border max-h-[500px]'}`}>
      <Table>
        <TableHeader className="sticky top-0 bg-muted z-10">
          <TableRow>
            <TableHead className="w-20 text-center py-1">Дата</TableHead>
            <TableHead className="w-16 text-center py-1">Время</TableHead>
            <TableHead className="w-16 text-center py-1">№ Подв.</TableHead>
            <TableHead className="w-16 text-center py-1">Тип</TableHead>
            <TableHead className="w-20 text-center py-1">№ КПЗ</TableHead>
            <TableHead className="text-center py-1">Клиент</TableHead>
            <TableHead className="max-w-[180px] text-center py-1">Профиль</TableHead>
            <TableHead className="text-center py-1" style={{ maxWidth: '800px' }}>Фото</TableHead>
            <TableHead className="w-16 text-center py-1">Ламели</TableHead>
            <TableHead className="text-center py-1">Цвет</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isUpdating && <UpdateRow progress={progress} />}
          {data.map((hanger, idx) => {
            const rowId = `${hanger.number}-${hanger.date}-${hanger.time}`
            const isNew = highlightNew && newIds.has(rowId)

            return (
              <TableRow
                key={`${hanger.number}-${idx}`}
                className={isNew ? 'bg-yellow-500/20 animate-pulse' : idx % 2 === 0 ? 'bg-slate-200 dark:bg-slate-700' : ''}
              >
                <TableCell className="text-center py-1">{hanger.date}</TableCell>
                <TableCell className="text-center py-1">{hanger.time}</TableCell>
                <TableCell className="text-center font-bold py-1">{hanger.number}</TableCell>
                <TableCell className="text-center py-1">{hanger.material_type}</TableCell>
                <TableCell className="text-center py-1">{hanger.kpz_number}</TableCell>
                <TableCell className="text-center truncate max-w-[120px] py-1">{hanger.client}</TableCell>
                <TableCell className="text-center max-w-[180px] py-1">
                  <span className="break-words">{hanger.profile?.replace(/\+/g, '+ ') || '—'}</span>
                </TableCell>
                <TableCell className="py-1" style={{ maxWidth: '800px' }}>
                  <PhotoCell hanger={hanger} onPhotoClick={onPhotoClick} />
                </TableCell>
                <TableCell className="text-center font-bold py-1">{hanger.lamels_qty}</TableCell>
                <TableCell className="text-center py-1">
                  <div className="inline-flex flex-col items-center max-w-[80px]">
                    <span className="text-sm leading-tight text-center break-words">{hanger.color}</span>
                    <div 
                      className="w-full h-1.5 rounded-full mt-0.5" 
                      style={{ backgroundColor: getColorHex(hanger.color), minWidth: '50px' }}
                    />
                  </div>
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
    <div className="space-y-2 p-4">
      {[...Array(5)].map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  )
}

// Filters
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
    <Card>
      <CardContent className="py-4">
        <div className="flex flex-wrap gap-4 items-center">
          {/* Loading */}
          <div className="flex items-center gap-3 border rounded-lg px-3 py-2 border-blue-500/50 bg-blue-500/10">
            <Checkbox
              id="show-loading"
              checked={filters.showLoading}
              onCheckedChange={(c) => onChange({ ...filters, showLoading: !!c })}
            />
            <Label htmlFor="show-loading" className="cursor-pointer">Загрузка:</Label>
            <Input
              type="number"
              value={filters.loadingLimit}
              onChange={e => onChange({ ...filters, loadingLimit: Number(e.target.value) })}
              className="w-20 h-8"
              min={1}
              max={500}
            />
          </div>

          {/* Realtime */}
          <div className="flex items-center gap-3 border rounded-lg px-3 py-2 border-green-500/50 bg-green-500/10">
            <Checkbox
              id="show-realtime"
              checked={filters.showRealtime}
              onCheckedChange={(c) => onChange({ ...filters, showRealtime: !!c })}
            />
            <Label htmlFor="show-realtime" className="cursor-pointer">Выгрузка:</Label>
            <Input
              type="number"
              value={filters.realtimeLimit}
              onChange={e => onChange({ ...filters, realtimeLimit: Number(e.target.value) })}
              className="w-20 h-8"
              min={1}
              max={500}
            />
          </div>

          {/* Unloading old */}
          <div className="flex items-center gap-3 border rounded-lg px-3 py-2 border-pink-500/50 bg-pink-500/10">
            <Checkbox
              id="show-unloading"
              checked={filters.showUnloading}
              onCheckedChange={(c) => onChange({ ...filters, showUnloading: !!c })}
            />
            <Label htmlFor="show-unloading" className="cursor-pointer">Выгрузка старая:</Label>
            <Input
              type="number"
              value={filters.unloadingLimit}
              onChange={e => onChange({ ...filters, unloadingLimit: Number(e.target.value) })}
              className="w-20 h-8"
              min={1}
              max={500}
            />
          </div>

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
            <Button variant="outline" onClick={onReset}>Сбросить</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Main
export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>(loadFilters)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [photoModal, setPhotoModal] = useState<{ url: string; name: string } | null>(null)
  const [realtimeData, setRealtimeData] = useState<HangerData[]>([])
  const [newRowIds, setNewRowIds] = useState<Set<string>>(new Set())
  const [isFileUpdating, setIsFileUpdating] = useState(false)
  const lastModifiedRef = useRef<string | null>(null)

  const { toast } = useToast()
  const { data, isLoading, refetch, isFetching } = useDashboard(7, filters.loadingLimit)
  const { data: fileStatus } = useFileStatus()

  // Track file changes and auto-refresh
  useEffect(() => {
    if (fileStatus?.last_modified) {
      const newModified = fileStatus.last_modified
      if (lastModifiedRef.current && lastModifiedRef.current !== newModified) {
        // File was modified - show updating state
        setIsFileUpdating(true)
        toast({
          title: '📄 Файл обновлён',
          description: 'Загрузка новых данных...',
        })
        
        // Refetch data
        refetch().then(() => {
          setIsFileUpdating(false)
          toast({
            title: '✅ Данные обновлены',
            description: `Загружено ${data?.total ?? 0} записей`,
          })
        })
      }
      lastModifiedRef.current = newModified
    }
  }, [fileStatus?.last_modified])

  useRealtimeData({
    onMessage: (msg) => {
      if (msg.type === 'unload_event' && msg.payload) {
        const newHanger = msg.payload as unknown as HangerData
        const rowId = `${newHanger.number}-${newHanger.date}-${newHanger.time}`

        setRealtimeData(prev => [newHanger, ...prev].slice(0, filters.realtimeLimit))

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

  useEffect(() => { saveFilters(filters) }, [filters])

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
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  const handlePhotoClick = useCallback((url: string, name: string) => {
    setPhotoModal({ url, name })
  }, [])

  return (
    <div className={`${isFullscreen ? 'p-0' : 'container mx-auto p-6 space-y-4'}`}>
      {/* Header */}
      {!isFullscreen && (
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">📊 Учет КПЗ - Подвесы</h1>
          <div className="flex items-center gap-4">
            <Badge variant="secondary">Всего: {data?.total_all ?? '—'}</Badge>
            <Badge variant="outline">Показано: {data?.total ?? '—'}</Badge>
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

      {isFullscreen && (
        <div className="fixed top-2 right-2 z-50">
          <Button variant="secondary" size="sm" onClick={toggleFullscreen}>
            <X className="w-4 h-4 mr-1" /> Выход
          </Button>
        </div>
      )}

      {!isFullscreen && <StatusBar />}

      {!isFullscreen && (
        <FiltersPanel
          filters={filters}
          onChange={setFilters}
          onApply={() => refetch()}
          onReset={() => { setFilters(defaultFilters); refetch() }}
        />
      )}

      <div className="space-y-4">
        {filters.showLoading && (
          <Card className="border-l-4 border-l-blue-500">
            <CardContent className="p-0">
              {isLoading ? <TableSkeleton /> : data?.products?.length ? (
                <DataTable 
                  data={data.products} 
                  onPhotoClick={handlePhotoClick} 
                  isUpdating={isFetching || isFileUpdating}
                  isFullscreen={isFullscreen}
                />
              ) : (
                <div className="p-8 text-center text-muted-foreground">Нет записей</div>
              )}
            </CardContent>
          </Card>
        )}

        {filters.showRealtime && (
          <Card className="border-l-4 border-l-green-500">
            <CardContent className="p-0">
              {realtimeData.length > 0 ? (
                <DataTable data={realtimeData} onPhotoClick={handlePhotoClick} highlightNew newIds={newRowIds} isFullscreen={isFullscreen} />
              ) : (
                <div className="p-8 text-center text-muted-foreground">Ожидание событий...</div>
              )}
            </CardContent>
          </Card>
        )}

        {filters.showUnloading && (
          <Card className="border-l-4 border-l-pink-500">
            <CardContent className="p-0">
              {data?.unloading_products?.length ? (
                <DataTable data={data.unloading_products} onPhotoClick={handlePhotoClick} isFullscreen={isFullscreen} />
              ) : (
                <div className="p-8 text-center text-muted-foreground">Нет записей</div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <PhotoModal
        open={!!photoModal}
        onClose={() => setPhotoModal(null)}
        photoUrl={photoModal?.url || null}
        profileName={photoModal?.name || ''}
      />
    </div>
  )
}
