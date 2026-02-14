import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  RefreshCw, Wifi, WifiOff, FileSpreadsheet, Server,
  Image, Maximize2, Minimize2, X
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

import { useDashboard, useFileStatus, useOPCUAStatus, useOPCUAMatchedUnloadEvents } from '@/hooks/useDashboard'
import { useRealtimeData } from '@/hooks/useRealtimeData'
import { BathForecast } from '@/components/BathForecastTable'
import type { HangerData, ProfileInfo } from '@/types/dashboard'

const FILTERS_KEY = 'ekranchik_filters'

interface Filters {
  loadingLimit: number
  realtimeLimit: number
  showLoading: boolean
  showRealtime: boolean
  showForecast: boolean
  showTime: boolean
}

const defaultFilters: Filters = {
  loadingLimit: 10,
  realtimeLimit: 10,
  showLoading: true,
  showRealtime: true,
  showForecast: true,
  showTime: true,
}

function loadFilters(): Filters {
  try {
    const saved = localStorage.getItem(FILTERS_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      return {
        ...defaultFilters,
        ...parsed,
        // Ensure limits are valid (min 1)
        loadingLimit: Math.max(1, parsed.loadingLimit || defaultFilters.loadingLimit),
        realtimeLimit: Math.max(1, parsed.realtimeLimit || defaultFilters.realtimeLimit),
      }
    }
  } catch { /* ignore */ }
  return defaultFilters
}

function saveFilters(filters: Filters) {
  localStorage.setItem(FILTERS_KEY, JSON.stringify(filters))
}

// Format time without seconds (HH:MM:SS -> HH:MM)
function formatTime(time: string | undefined): string {
  if (!time) return '—'
  const parts = time.split(':')
  if (parts.length >= 2) return `${parts[0]}:${parts[1]}`
  return time
}

// Format date with year 2026 (DD.MM.YY -> DD.MM.2026)
function formatDate(date: string | undefined): string {
  if (!date) return '—'
  // Handle formats like "28.10.26" or "29.11.2026"
  const parts = date.split('.')
  if (parts.length === 3) {
    const year = parts[2].length === 2 ? `20${parts[2]}` : parts[2]
    return `${parts[0]}.${parts[1]}.${year}`
  }
  return date
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

// Profile data type from catalog
interface ProfileData {
  id: number
  name: string
  quantity_per_hanger: number | null
  length: number | null
  notes: string | null
}

// Photo Modal - with fullscreen support
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
  const [profileData, setProfileData] = useState<ProfileData | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

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

  // Load profile data from catalog API
  useEffect(() => {
    setProfileData(null)
    if (!open || !profileName) return

    fetch(`/api/catalog/${encodeURIComponent(profileName)}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => setProfileData(data))
      .catch(() => setProfileData(null))
  }, [open, profileName])

  // Reset fullscreen when dialog closes
  useEffect(() => {
    if (!open) {
      setIsFullscreen(false)
    }
  }, [open])

  // Handle ESC key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isFullscreen) {
          setIsFullscreen(false)
        } else {
          onClose()
        }
      }
    }

    if (open) {
      window.addEventListener('keydown', handleEsc)
      return () => window.removeEventListener('keydown', handleEsc)
    }
  }, [open, isFullscreen, onClose])

  // Fullscreen API management
  useEffect(() => {
    if (!isFullscreen) return

    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setIsFullscreen(false)
      }
    }

    const handleEscFullscreen = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsFullscreen(false)
      }
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange)
    window.addEventListener('keydown', handleEscFullscreen)

    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
      window.removeEventListener('keydown', handleEscFullscreen)
    }
  }, [isFullscreen])

  // Request fullscreen when isFullscreen becomes true
  useEffect(() => {
    if (!isFullscreen) return

    const fullscreenElement = document.getElementById('fullscreen-photo-container')
    if (fullscreenElement && !document.fullscreenElement) {
      fullscreenElement.requestFullscreen().catch(() => {
        console.log('Fullscreen not supported')
      })
    }
  }, [isFullscreen])

  // Calculate dialog size based on actual image pixels (like Catalog)
  const dialogSize = useMemo(() => {
    const rightPanelWidth = 280
    const maxDialogHeight = typeof window !== 'undefined' ? window.innerHeight - 100 : 800
    const maxDialogWidth = typeof window !== 'undefined' ? window.innerWidth - 100 : 1200
    const minHeight = 400

    if (!imageSize) {
      return { width: Math.min(900, maxDialogWidth), height: minHeight }
    }

    let imgDisplayWidth = imageSize.width
    let imgDisplayHeight = imageSize.height

    // Scale down if image is too tall
    if (imgDisplayHeight > maxDialogHeight) {
      const scale = maxDialogHeight / imgDisplayHeight
      imgDisplayWidth = imgDisplayWidth * scale
      imgDisplayHeight = maxDialogHeight
    }

    // Scale down if dialog would be too wide
    const dialogWidth = imgDisplayWidth + rightPanelWidth
    if (dialogWidth > maxDialogWidth) {
      const scale = (maxDialogWidth - rightPanelWidth) / imgDisplayWidth
      imgDisplayWidth = imgDisplayWidth * scale
      imgDisplayHeight = imgDisplayHeight * scale
    }

    return {
      width: Math.max(600, imgDisplayWidth + rightPanelWidth),
      height: Math.max(minHeight, imgDisplayHeight)
    }
  }, [imageSize])

  if (!photoUrl) return null

  // Fullscreen mode - using browser fullscreen API (rendered at end of component)

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent
          className="p-0 gap-0 top-[5%] translate-y-0"
          style={{ width: `${dialogSize.width}px`, height: `${dialogSize.height}px`, maxWidth: 'calc(100vw - 100px)' }}
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div className="flex h-full">
            {/* Photo area - left side */}
            <div className="flex-1 bg-muted flex items-center justify-center overflow-auto relative">
              <Button
                variant="ghost"
                size="icon"
                className="absolute top-2 right-2 z-10"
                onClick={() => setIsFullscreen(true)}
                title="Развернуть на весь экран"
              >
                <Maximize2 className="h-5 w-5" />
              </Button>
              <div
                className="relative w-full h-full flex items-center justify-center select-none cursor-pointer"
                onClick={() => setIsFullscreen(true)}
              >
                <img
                  src={photoUrl}
                  alt={profileName}
                  className="max-w-full max-h-full object-contain pointer-events-none"
                />
              </div>
            </div>

            {/* Right panel - info (like Catalog view mode) */}
            <div className="border-l bg-background p-4 flex flex-col" style={{ width: '280px' }}>
              <div className="flex-1 space-y-4 overflow-y-auto">
                <h2 className="text-xl font-semibold">{profileName}</h2>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Кол-во на подвесе:</span>
                    <span className="font-medium">{profileData?.quantity_per_hanger ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Длина:</span>
                    <span className="font-medium">{profileData?.length ? `${profileData.length} мм` : '—'}</span>
                  </div>
                </div>
                {profileData?.notes && (
                  <div className="pt-2 border-t">
                    <span className="text-sm text-muted-foreground">Примечания:</span>
                    <p className="mt-1 text-sm">{profileData.notes}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Fullscreen overlay - desktop only */}
      {isFullscreen && photoUrl && typeof window !== 'undefined' && window.innerWidth >= 768 && (
        <div
          id="fullscreen-photo-container"
          className="fixed inset-0 z-[100] bg-black flex items-center justify-center"
          onClick={() => setIsFullscreen(false)}
        >
          {/* Large close area for mobile - top-left corner */}
          {typeof window !== 'undefined' && window.innerWidth < 768 && (
            <div
              className="absolute top-0 left-0 w-16 h-16 z-20 cursor-pointer"
              onClick={(e) => {
                e.stopPropagation()
                setIsFullscreen(false)
              }}
            />
          )}

          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-4 text-white hover:bg-white/20 z-10"
            onClick={(e) => {
              e.stopPropagation()
              setIsFullscreen(false)
            }}
          >
            <Minimize2 className="h-6 w-6" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-16 text-white hover:bg-white/20 z-10"
            onClick={(e) => {
              e.stopPropagation()
              onClose()
              setIsFullscreen(false)
            }}
          >
            <X className="h-6 w-6" />
          </Button>
          <img
            src={photoUrl}
            alt={profileName}
            className="max-w-full max-h-full object-contain cursor-pointer"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  )
}

// Helper to build photo URL (paths in DB already include /static/)
function getPhotoUrl(path: string | null | undefined, cacheBuster?: string): string | null {
  if (!path) return null
  // Paths in DB can be like "/static/images/..." or "images/..."
  const base = path.startsWith('/') ? path : `/static/${path}`
  return cacheBuster ? `${base}?v=${cacheBuster}` : base
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
        {hanger.is_defect && (
          <span className="text-red-600 font-bold text-lg px-2 py-1 bg-red-100 rounded">БРАК</span>
        )}
        {profilesInfo.map((prof, idx) => (
          <ProfilePhoto key={idx} profile={prof} onPhotoClick={onPhotoClick} />
        ))}
      </div>
    )
  }

  const thumbUrl = getPhotoUrl(hanger.profile_photo_thumb)
  if (thumbUrl) {
    return (
      <div className="flex items-center justify-center gap-2" style={{ maxWidth: '800px' }}>
        {hanger.is_defect && (
          <span className="text-red-600 font-bold text-lg px-2 py-1 bg-red-100 rounded">БРАК</span>
        )}
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
    <div className="flex items-center justify-center gap-2" style={{ maxWidth: '800px' }}>
      {hanger.is_defect && (
        <span className="text-red-600 font-bold text-lg px-2 py-1 bg-red-100 rounded">БРАК</span>
      )}
      <div className="w-10 h-10 bg-muted rounded flex items-center justify-center">
        <Image className="w-5 h-5 text-muted-foreground" />
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
  const thumbUrl = getPhotoUrl(profile.photo_thumb, profile.updated_at)
  const fullUrl = getPhotoUrl(profile.photo_full || profile.photo_thumb, profile.updated_at)
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

function StatusBar() {
  const { data: fileStatus } = useFileStatus()
  const { data: opcuaStatus } = useOPCUAStatus()
  const { isConnected, lastMessage } = useRealtimeData()

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
                ({new Date(fileStatus.last_modified).toLocaleString('ru')})
              </span>
            )}
          </div>

          <div className="w-px h-4 bg-border" />

          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-muted-foreground" />
            <div className={`w-2 h-2 rounded-full ${opcuaStatus?.is_open ? 'bg-green-500' : 'bg-destructive'}`} />
            <span>OPC UA: {opcuaStatus?.is_open ? 'OK' : 'Откл'}</span>
            {opcuaStatus?.last_modified && (
              <span className="text-muted-foreground text-xs">
                ({new Date(opcuaStatus.last_modified).toLocaleTimeString('ru')})
              </span>
            )}
          </div>

          <div className="w-px h-4 bg-border" />

          <div className="flex items-center gap-2">
            {isConnected ? (
              <Wifi className="w-4 h-4 text-green-500" />
            ) : (
              <WifiOff className="w-4 h-4 text-destructive" />
            )}
            <span>WS: {isConnected ? 'Онлайн' : 'Офлайн'}</span>
            {lastMessage?.timestamp && (
              <span className="text-muted-foreground text-xs">
                ({new Date(lastMessage.timestamp).toLocaleTimeString('ru')})
              </span>
            )}
          </div>

        </div>
      </CardContent>
    </Card>
  )
}




// Data table
function DataTable({
  data,
  onPhotoClick,
  isFullscreen = false,
  showEntryExit = false,
  headerChildren,
}: {
  data: HangerData[]
  onPhotoClick: (url: string, name: string) => void
  isFullscreen?: boolean
  showEntryExit?: boolean
  headerChildren?: React.ReactNode
}) {
  return (
    <div className={`overflow-auto text-xs ${isFullscreen ? 'max-h-screen' : 'rounded-md border max-h-[500px]'}`}>
      <Table>
        <TableHeader className="sticky top-0 bg-muted z-10">
          {headerChildren && (
            <TableRow className="bg-background border-b hover:bg-background">
              <TableCell colSpan={10} className="p-0">
                {headerChildren}
              </TableCell>
            </TableRow>
          )}
          <TableRow>
            <TableHead className="w-20 text-center py-1">Дата</TableHead>
            <TableHead className="w-16 text-center py-1">Время</TableHead>
            <TableHead className="w-16 text-center py-1">№</TableHead>
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
          {data.map((hanger, idx) => {
            return (
              <TableRow
                key={`${hanger.number}-${idx}`}
                className={idx % 2 === 0 ? 'bg-slate-200' : ''}
              >
                {showEntryExit ? (
                  <>
                    <TableCell className="text-center py-1 text-xs">
                      {formatDate(hanger.entry_date) === formatDate(hanger.exit_date) ? (
                        <span>{formatDate(hanger.entry_date)}</span>
                      ) : (
                        <div className="flex flex-col">
                          <span className="text-blue-600">{formatDate(hanger.entry_date)}</span>
                          <span className="text-green-600">{formatDate(hanger.exit_date)}</span>
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-center py-1 text-xs">
                      <div className="flex flex-col">
                        <span className="text-blue-600">{formatTime(hanger.entry_time)}</span>
                        <span className="text-green-600">{formatTime(hanger.exit_time)}</span>
                      </div>
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="text-center py-1">{hanger.date}</TableCell>
                    <TableCell className="text-center py-1">{hanger.time}</TableCell>
                  </>
                )}
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
  onToggleLast100,
  isLast100Mode,
}: {
  filters: Filters
  onChange: (filters: Filters) => void
  onApply: () => void
  onReset: () => void
  onToggleLast100: () => void
  isLast100Mode: boolean
}) {
  const otherFiltersDisabled = isLast100Mode;

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex flex-wrap gap-4 items-center">
          {/* Loading */}
          <div className={`flex items-center gap-3 border rounded-lg px-3 py-2 ${otherFiltersDisabled ? 'opacity-50' : 'border-blue-500/50 bg-blue-500/10'}`}>
            <Checkbox
              id="show-loading"
              checked={filters.showLoading}
              onCheckedChange={(c) => onChange({ ...filters, showLoading: !!c })}
              disabled={otherFiltersDisabled}
            />
            <Label htmlFor="show-loading" className={`cursor-pointer ${otherFiltersDisabled ? 'cursor-not-allowed' : ''}`}>Загрузка:</Label>
            <Input
              type="number"
              value={filters.loadingLimit}
              onChange={e => {
                const val = e.target.value
                // Allow empty string during editing
                onChange({ ...filters, loadingLimit: val === '' ? '' as any : Number(val) })
              }}
              onBlur={e => {
                // Validate on blur - ensure minimum value of 1
                const val = e.target.value
                if (val === '' || Number(val) < 1) {
                  onChange({ ...filters, loadingLimit: 1 })
                }
              }}
              className="w-20 h-8"
              min={1}
              max={500}
              disabled={otherFiltersDisabled}
            />
          </div>

          {/* Realtime */}
          <div className={`flex items-center gap-3 border rounded-lg px-3 py-2 ${otherFiltersDisabled ? 'opacity-50' : 'border-green-500/50 bg-green-500/10'}`}>
            <Checkbox
              id="show-realtime"
              checked={filters.showRealtime}
              onCheckedChange={(c) => onChange({ ...filters, showRealtime: !!c })}
              disabled={otherFiltersDisabled}
            />
            <Label htmlFor="show-realtime" className={`cursor-pointer ${otherFiltersDisabled ? 'cursor-not-allowed' : ''}`}>Выгрузка:</Label>
            <Input
              type="number"
              value={filters.realtimeLimit}
              onChange={e => {
                const val = e.target.value
                onChange({ ...filters, realtimeLimit: val === '' ? '' as any : Number(val) })
              }}
              onBlur={e => {
                const val = e.target.value
                if (val === '' || Number(val) < 1) {
                  onChange({ ...filters, realtimeLimit: 1 })
                }
              }}
              className="w-20 h-8"
              min={1}
              max={500}
              disabled={otherFiltersDisabled}
            />
          </div>

          <Button
            variant={isLast100Mode ? "default" : "outline"}
            onClick={onToggleLast100}
          >
            Последние 100
          </Button>

          {/* Forecast */}
          <div className="flex items-center gap-2 border rounded-lg px-3 py-2 border-purple-500/50 bg-purple-500/10">
            <Checkbox
              id="show-forecast"
              checked={filters.showForecast}
              onCheckedChange={(c) => onChange({ ...filters, showForecast: !!c })}
            />
            <Label htmlFor="show-forecast" className="cursor-pointer">Прогноз выхода</Label>
          </div>



          <div className="flex gap-2 ml-auto">
            <Button onClick={onApply} disabled={otherFiltersDisabled}>Применить</Button>
            <Button variant="outline" onClick={onReset} disabled={otherFiltersDisabled}>Сбросить</Button>
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
  const [hasNewRows, setHasNewRows] = useState(false)
  const [hasNewUnloadEvents, setHasNewUnloadEvents] = useState(false)
  const lastModifiedRef = useRef<string | null>(null)
  const prevDataRef = useRef<HangerData[]>([])
  const prevUnloadDataRef = useRef<any[]>([])

  // State for "Последние 100" toggle
  const [isLast100Mode, setIsLast100Mode] = useState(false);
  const [preLast100Filters, setPreLast100Filters] = useState<Filters | null>(null);

  // Determine if the API should filter for loading_only rows
  const loadingOnly = !isLast100Mode;

  const { data, isLoading, refetch, isFetching } = useDashboard(7, filters.loadingLimit, loadingOnly)
  const { data: fileStatus } = useFileStatus()
  const { data: matchedEvents, refetch: refetchMatched } = useOPCUAMatchedUnloadEvents(filters.realtimeLimit)

  const handleToggleLast100 = () => {
    if (isLast100Mode) {
      // Turn OFF: Restore previous filters
      if (preLast100Filters) {
        setFilters(preLast100Filters);
      }
      setIsLast100Mode(false);
      setPreLast100Filters(null);
    } else {
      // Turn ON: Save current filters and apply "Last 100"
      setPreLast100Filters(filters);
      setFilters({
        ...defaultFilters,
        showLoading: true,
        loadingLimit: 100,
      });
      setIsLast100Mode(true);
    }
  };


  // Track file changes and auto-refresh
  useEffect(() => {
    if (fileStatus?.last_modified) {
      const newModified = fileStatus.last_modified
      if (lastModifiedRef.current && lastModifiedRef.current !== newModified) {
        // File was modified - refetch data
        refetch().then((result) => {
          const newData = result.data?.products ?? []
          const prevData = prevDataRef.current

          // Deep compare function for rows
          const rowsEqual = (r1: HangerData, r2: HangerData): boolean => {
            return (
              r1.number === r2.number &&
              r1.date === r2.date &&
              r1.time === r2.time &&
              r1.profile === r2.profile &&
              r1.color === r2.color &&
              r1.client === r2.client &&
              r1.kpz_number === r2.kpz_number &&
              r1.material_type === r2.material_type &&
              r1.lamels_qty === r2.lamels_qty
            )
          }

          // Check if there are actual changes in rows
          const hasActualChanges =
            newData.length !== prevData.length ||
            newData.some((newRow, idx) => {
              const prevRow = prevData[idx]
              return !prevRow || !rowsEqual(newRow, prevRow)
            })

          if (hasActualChanges) {
            // Show blue highlight only if there are actual changes
            setHasNewRows(true)
            prevDataRef.current = newData
            // Auto-hide highlight after 3 seconds
            setTimeout(() => setHasNewRows(false), 3000)
          }
        })
      }
      lastModifiedRef.current = newModified
    }
  }, [fileStatus?.last_modified, refetch])

  // Track unload events changes
  useEffect(() => {
    if (matchedEvents && matchedEvents.length > 0) {
      const prevUnloadData = prevUnloadDataRef.current

      // Deep compare function for unload events
      const eventsEqual = (e1: any, e2: any): boolean => {
        return (
          e1.hanger === e2.hanger &&
          e1.exit_date === e2.exit_date &&
          e1.exit_time === e2.exit_time &&
          e1.entry_date === e2.entry_date &&
          e1.entry_time === e2.entry_time &&
          e1.profile === e2.profile &&
          e1.color === e2.color &&
          e1.client === e2.client
        )
      }

      // Check if there are actual changes
      const hasActualChanges =
        matchedEvents.length !== prevUnloadData.length ||
        matchedEvents.some((newEvent, idx) => {
          const prevEvent = prevUnloadData[idx]
          return !prevEvent || !eventsEqual(newEvent, prevEvent)
        })

      if (hasActualChanges) {
        setHasNewUnloadEvents(true)
        prevUnloadDataRef.current = matchedEvents
        // Auto-hide highlight after 3 seconds
        setTimeout(() => setHasNewUnloadEvents(false), 3000)
      }
    }
  }, [matchedEvents])

  // Handle Escape key to exit kiosk mode
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Close the browser window (works in kiosk mode)
        window.close()
      }
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [])

  // Auto-fullscreen if opened from kiosk mode (check URL parameter or window size)
  useEffect(() => {
    // Проверяем если это открыто на весь экран (вероятно из киоска)
    const isKioskMode = window.innerHeight === screen.height && window.innerWidth === screen.width

    if (isKioskMode && !isFullscreen) {
      // Автоматически переходим в fullscreen
      setTimeout(() => {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen().catch(() => {
            // Если fullscreen не сработал, это нормально
          })
        }
      }, 500)
    }
  }, [])

  // Refetch matched events when new unload event arrives
  useRealtimeData({
    onMessage: (msg) => {
      if (msg.type === 'unload_event') {
        // New unload event - refetch matched data
        refetchMatched()
      } else if (msg.type === 'line_update') {
        // Line update - данные обновляются каждую секунду
        // Можно использовать для обновления статуса OPC UA
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
          onApply={refetch}
          onReset={() => setFilters(defaultFilters)}
          onToggleLast100={handleToggleLast100}
          isLast100Mode={isLast100Mode}
        />
      )}

      <div className="space-y-1 relative">
        {filters.showLoading && (
          <Card className="border-8 border-blue-500 relative">
            {hasNewRows && (
              <div className="absolute inset-0 bg-blue-500 z-50 rounded-md flex items-center justify-center">
                <span className="text-white text-3xl font-bold">Обновление</span>
              </div>
            )}
            <CardContent className="p-0">
              {isLoading ? <TableSkeleton /> : data?.products?.length ? (
                <DataTable
                  data={data.products}
                  onPhotoClick={handlePhotoClick}
                  isFullscreen={isFullscreen}
                />
              ) : (
                <div className="w-full py-8 text-center text-muted-foreground font-mono text-lg">
                  :( {'='.repeat(12)} :( {'='.repeat(12)} :( {'='.repeat(12)} :( {'='.repeat(12)} :(
                </div>
              )}
            </CardContent>
          </Card>
        )}



        {filters.showRealtime && (
          <>
            {console.log('[Dashboard] matchedEvents:', matchedEvents)}
            {matchedEvents && matchedEvents.length > 0 && (
              <>
                {console.log('[Dashboard] First event:', matchedEvents[0])}
                {console.log('[Dashboard] Rendering table with', matchedEvents.length, 'events')}
              </>
            )}

            {/* Forecast Row - Outside the green border */}
            {filters.showForecast && <BathForecast />}

            <Card className="border-8 border-green-500 relative">
              {hasNewUnloadEvents && (
                <div className="absolute inset-0 bg-green-500 z-50 rounded-md flex items-center justify-center">
                  <span className="text-white text-3xl font-bold">Обновление</span>
                </div>
              )}
              <CardContent className="p-0">
                {matchedEvents && matchedEvents.length > 0 ? (
                  <DataTable
                    data={matchedEvents.map(e => ({
                      number: String(e.hanger),
                      date: e.exit_date,
                      time: e.exit_time,
                      client: e.client,
                      profile: e.profile,
                      profiles_info: e.profiles_info,
                      color: e.color,
                      lamels_qty: e.lamels_qty,
                      kpz_number: e.kpz_number,
                      material_type: e.material_type,
                      entry_date: e.entry_date,
                      entry_time: e.entry_time,
                      exit_date: e.exit_date,
                      exit_time: e.exit_time,
                      current_bath: e.current_bath,
                      bath_entry_time: e.bath_entry_time,
                      bath_processing_time: e.bath_processing_time,
                    }))}
                    onPhotoClick={handlePhotoClick}
                    isFullscreen={isFullscreen}
                    showEntryExit
                  />
                ) : (
                  <div className="w-full py-8 text-center text-muted-foreground font-mono text-lg">
                    :) {'='.repeat(12)} :) {'='.repeat(12)} :) {'='.repeat(12)} :) {'='.repeat(12)} :)
                  </div>
                )}
              </CardContent>
            </Card>
          </>
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
