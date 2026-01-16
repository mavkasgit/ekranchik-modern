import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  RefreshCw, Wifi, WifiOff, FileSpreadsheet, Server,
  Image, Maximize2, Minimize2, X, Loader2
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

import { useDashboard, useFileStatus, useOPCUAStatus, useOPCUAMatchedUnloadEvents } from '@/hooks/useDashboard'
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
    if (saved) {
      const parsed = JSON.parse(saved)
      return {
        ...defaultFilters,
        ...parsed,
        // Ensure limits are valid (min 1)
        loadingLimit: Math.max(1, parsed.loadingLimit || defaultFilters.loadingLimit),
        unloadingLimit: Math.max(1, parsed.unloadingLimit || defaultFilters.unloadingLimit),
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

// Format date with year 2025 (DD.MM.YY -> DD.MM.2025)
function formatDate(date: string | undefined): string {
  if (!date) return '—'
  // Handle formats like "28.10.25" or "29.11.2025"
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

// Photo Modal - exact copy of Catalog ProfileDialog view mode
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

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent 
        className="p-0 gap-0 top-[5%] translate-y-0"
        style={{ width: `${dialogSize.width}px`, height: `${dialogSize.height}px`, maxWidth: 'calc(100vw - 100px)' }}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <div className="flex h-full">
          {/* Photo area - left side */}
          <div className="flex-1 bg-muted flex items-center justify-center overflow-auto relative">
            <div className="relative w-full h-full flex items-center justify-center select-none">
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
  showEntryExit = false,
}: {
  data: HangerData[]
  onPhotoClick: (url: string, name: string) => void
  highlightNew?: boolean
  newIds?: Set<string>
  isUpdating?: boolean
  isFullscreen?: boolean
  showEntryExit?: boolean
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
            const rowId = showEntryExit 
              ? `${hanger.number}-${hanger.exit_date}-${hanger.exit_time}`
              : `${hanger.number}-${hanger.date}-${hanger.time}`
            const isNew = highlightNew && newIds.has(rowId)

            return (
              <TableRow
                key={`${hanger.number}-${idx}`}
                className={isNew ? 'bg-yellow-500/20 animate-pulse' : idx % 2 === 0 ? 'bg-slate-200' : ''}
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

          {/* Unloading old */}
          <div className={`flex items-center gap-3 border rounded-lg px-3 py-2 ${otherFiltersDisabled ? 'opacity-50' : 'border-pink-500/50 bg-pink-500/10'}`}>
            <Checkbox
              id="show-unloading"
              checked={filters.showUnloading}
              onCheckedChange={(c) => onChange({ ...filters, showUnloading: !!c })}
              disabled={otherFiltersDisabled}
            />
            <Label htmlFor="show-unloading" className={`cursor-pointer ${otherFiltersDisabled ? 'cursor-not-allowed' : ''}`}>Выгрузка старая:</Label>
            <Input
              type="number"
              value={filters.unloadingLimit}
              onChange={e => {
                const val = e.target.value
                onChange({ ...filters, unloadingLimit: val === '' ? '' as any : Number(val) })
              }}
              onBlur={e => {
                const val = e.target.value
                if (val === '' || Number(val) < 1) {
                  onChange({ ...filters, unloadingLimit: 1 })
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
  const [isFileUpdating, setIsFileUpdating] = useState(false)
  const lastModifiedRef = useRef<string | null>(null)
  
  // State for "Последние 100" toggle
  const [isLast100Mode, setIsLast100Mode] = useState(false);
  const [preLast100Filters, setPreLast100Filters] = useState<Filters | null>(null);

  // Determine if the API should filter for loading_only rows
  const loadingOnly = !isLast100Mode;

  const { toast } = useToast()
  const { data, isLoading, refetch, isFetching } = useDashboard(7, filters.loadingLimit, filters.unloadingLimit, loadingOnly)
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
                  }))} 
                  onPhotoClick={handlePhotoClick} 
                  isFullscreen={isFullscreen}
                  showEntryExit
                />
              ) : (
                <div className="p-8 text-center text-muted-foreground">Нет событий выгрузки</div>
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
