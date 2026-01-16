import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { 
  Search, Image, X, Upload, Grid, List, Plus, Pencil, Trash2,
  ArrowUpDown, ArrowUp, ArrowDown
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useToast } from '@/hooks/use-toast'
import { 
  useCatalogAll, 
  useCatalogSearch, 
  useUploadPhoto,
  useUpdateThumbnail,
  useCreateOrUpdateProfile,
  useUpdateProfile,
  useDeleteProfile,
} from '@/hooks/useCatalog'
import type { Profile, ProfileCreate } from '@/types/profile'

type ViewMode = 'grid' | 'table'
type SortField = 'name' | 'updated_at' | 'has_photo'
type SortDirection = 'asc' | 'desc'

const STORAGE_KEYS = {
  viewMode: 'catalog_view_mode',
  sortField: 'catalog_sort_field',
  sortDirection: 'catalog_sort_direction',
}

function getPhotoUrl(path: string | null, cacheBuster?: string | number): string | null {
  if (!path) return null
  const base = path.startsWith('/') ? path : `/static/${path}`
  // Use both updated_at and current timestamp to bust browser cache
  const bust = cacheBuster ? `${cacheBuster}_${Date.now()}` : Date.now()
  return `${base}?v=${bust}`
}

function ProfileCard({ 
  profile, 
  onSelect,
  onEdit,
  onDelete,
  isMobile,
}: { 
  profile: Profile
  onSelect: (profile: Profile) => void
  onEdit: (profile: Profile) => void
  onDelete: (profile: Profile) => void
  isMobile: boolean
}) {
  const photoUrl = getPhotoUrl(profile.photo_thumb, profile.updated_at)

  if (isMobile) {
    // Mobile layout - image on full height
    return (
      <Card className="cursor-pointer hover:shadow-md transition-shadow relative overflow-hidden">
        <CardContent className="p-0" onClick={() => onSelect(profile)}>
          <div className="flex h-32">
            {/* Image - full height */}
            <div className="w-32 h-32 bg-muted flex items-center justify-center overflow-hidden flex-shrink-0">
              {photoUrl ? (
                <img src={photoUrl} alt={profile.name} className="w-full h-full object-contain" />
              ) : (
                <Image className="w-8 h-8 text-muted-foreground" />
              )}
            </div>
            {/* Content */}
            <div className="flex-1 min-w-0 p-3 flex flex-col">
              <h3 className="font-medium truncate">{profile.name}</h3>
              <div className="flex gap-2 mt-1 flex-wrap">
                {profile.quantity_per_hanger && (
                  <Badge variant="secondary" className="text-xs">{profile.quantity_per_hanger} шт/подв</Badge>
                )}
                {profile.length && (
                  <Badge variant="outline" className="text-xs">{profile.length} мм</Badge>
                )}
              </div>
              {profile.notes && (
                <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{profile.notes}</p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Desktop layout - original
  return (
    <Card className="group cursor-pointer hover:shadow-md transition-shadow relative">
      <CardContent className="p-4" onClick={() => onSelect(profile)}>
        <div className="flex gap-4">
          <div className="w-20 h-20 bg-muted rounded-md flex items-center justify-center overflow-hidden flex-shrink-0">
            {photoUrl ? (
              <img src={photoUrl} alt={profile.name} className="max-w-full max-h-full object-contain" />
            ) : (
              <Image className="w-8 h-8 text-muted-foreground" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-medium truncate">{profile.name}</h3>
            <div className="flex gap-2 mt-1 flex-wrap">
              {profile.quantity_per_hanger && (
                <Badge variant="secondary">{profile.quantity_per_hanger} шт/подв</Badge>
              )}
              {profile.length && (
                <Badge variant="outline">{profile.length} мм</Badge>
              )}
            </div>
            {profile.notes && (
              <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{profile.notes}</p>
            )}
          </div>
        </div>
      </CardContent>
      {/* Edit/Delete buttons - desktop only */}
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={(e) => { e.stopPropagation(); onEdit(profile) }}>
          <Pencil className="h-4 w-4" />
        </Button>
        <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive" onClick={(e) => { e.stopPropagation(); onDelete(profile) }}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </Card>
  )
}


// Unified Profile Dialog - view, edit, create modes
function ProfileDialog({
  profile,
  open,
  onOpenChange,
  mode,
}: {
  profile: Profile | null
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'view' | 'create' | 'edit'
}) {
  const isViewMode = mode === 'view'
  const isEditMode = mode === 'edit' || mode === 'create'
  const { toast } = useToast()
  const createProfile = useCreateOrUpdateProfile()
  const updateProfile = useUpdateProfile()
  const uploadPhoto = useUploadPhoto()
  const updateThumbnail = useUpdateThumbnail()
  
  const [formData, setFormData] = useState<ProfileCreate>({
    name: '',
    quantity_per_hanger: null,
    length: null,
    notes: null,
  })
  const [photoMode, setPhotoMode] = useState<'view' | 'crop' | 'replace'>('view')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [cropArea, setCropArea] = useState({ x: 0, y: 0, width: 0, height: 0 })
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  // Separate thumbnail editing mode
  const [editingThumbnail, setEditingThumbnail] = useState(false)
  const [separateThumbnailFile, setSeparateThumbnailFile] = useState<File | null>(null)
  const [separateThumbnailUrl, setSeparateThumbnailUrl] = useState<string | null>(null)
  const [thumbnailCropArea, setThumbnailCropArea] = useState({ x: 0, y: 0, width: 0, height: 0 })

  useEffect(() => {
    if (profile && (mode === 'edit' || mode === 'view')) {
      setFormData({
        name: profile.name,
        quantity_per_hanger: profile.quantity_per_hanger,
        length: profile.length,
        notes: profile.notes,
      })
      const photoUrl = getPhotoUrl(profile.photo_full, profile.updated_at) || getPhotoUrl(profile.photo_thumb, profile.updated_at)
      setPreviewUrl(photoUrl)
    } else {
      setFormData({ name: '', quantity_per_hanger: null, length: null, notes: null })
      setPreviewUrl(null)
    }
    setPendingFile(null)
    setImageSize(null)
    // Show crop mode only in edit modes
    setPhotoMode(isEditMode ? 'crop' : 'view')
    // No crop area by default - user draws it
    setCropArea({ x: 0, y: 0, width: 0, height: 0 })
    // Reset separate thumbnail
    setSeparateThumbnailFile(null)
    setSeparateThumbnailUrl(null)
    setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
    setEditingThumbnail(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.id, mode, open])

  // Load image dimensions when previewUrl changes
  useEffect(() => {

    // Reset immediately to avoid stale dimensions
    setImageSize(null)
    
    if (!previewUrl) {
      return
    }
    
    const img = new window.Image()
    img.onload = () => {
      setImageSize({ width: img.naturalWidth, height: img.naturalHeight })
    }
    img.src = previewUrl
    
    return () => {
      img.onload = null // Cleanup to prevent setting state on unmounted component
    }
  }, [previewUrl])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setPendingFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setPhotoMode('crop')
      setCropArea({ x: 0, y: 0, width: 0, height: 0 })
      // Clear separate thumbnail when new main photo is uploaded
      setSeparateThumbnailFile(null)
      setSeparateThumbnailUrl(null)
    }
  }, [])

  const handleThumbnailFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSeparateThumbnailFile(file)
      setSeparateThumbnailUrl(URL.createObjectURL(file))
      setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
      // Clear main photo crop area since we're using separate thumbnail
      setCropArea({ x: 0, y: 0, width: 0, height: 0 })
    }
  }, [])

  // Paste from clipboard for thumbnail (called when in thumbnail editing mode)
  const handleThumbnailPaste = useCallback((file: File) => {
    setSeparateThumbnailFile(file)
    setSeparateThumbnailUrl(URL.createObjectURL(file))
    setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
    setCropArea({ x: 0, y: 0, width: 0, height: 0 })
  }, [])

  // Crop thumbnail image
  const cropThumbnailImage = useCallback(async (): Promise<File | null> => {
    if (!separateThumbnailUrl) return null
    
    // If no crop area, return original file
    if (thumbnailCropArea.width === 0 || thumbnailCropArea.height === 0) {
      return separateThumbnailFile
    }

    return new Promise((resolve) => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) { resolve(separateThumbnailFile); return }

      const image = new window.Image()
      image.crossOrigin = 'anonymous'
      image.onload = () => {
        const cropX = (thumbnailCropArea.x / 100) * image.naturalWidth
        const cropY = (thumbnailCropArea.y / 100) * image.naturalHeight
        const cropW = (thumbnailCropArea.width / 100) * image.naturalWidth
        const cropH = (thumbnailCropArea.height / 100) * image.naturalHeight

        canvas.width = cropW
        canvas.height = cropH
        ctx.drawImage(image, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH)
        
        canvas.toBlob((blob) => {
          if (blob) {
            resolve(new File([blob], 'thumbnail.jpg', { type: 'image/jpeg' }))
          } else {
            resolve(separateThumbnailFile)
          }
        }, 'image/jpeg', 0.9)
      }
      image.onerror = () => resolve(separateThumbnailFile)
      image.src = separateThumbnailUrl
    })
  }, [separateThumbnailUrl, thumbnailCropArea, separateThumbnailFile])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file?.type.startsWith('image/')) {
      // If in thumbnail editing mode, set thumbnail
      if (editingThumbnail) {
        setSeparateThumbnailFile(file)
        setSeparateThumbnailUrl(URL.createObjectURL(file))
        setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
        setCropArea({ x: 0, y: 0, width: 0, height: 0 })
      } else {
        setPendingFile(file)
        setPreviewUrl(URL.createObjectURL(file))
        setPhotoMode('crop')
        setCropArea({ x: 0, y: 0, width: 0, height: 0 })
      }
    }
  }, [editingThumbnail])

  // Handle paste - respects editingThumbnail mode
  useEffect(() => {
    if (!open) return
    const handlePaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (file) {
            if (editingThumbnail) {
              handleThumbnailPaste(file)
            } else {
              setPendingFile(file)
              const url = URL.createObjectURL(file)
              setPreviewUrl(url)
              setPhotoMode('crop')
              setCropArea({ x: 0, y: 0, width: 0, height: 0 })
            }
          }
        }
      }
    }
    window.addEventListener('paste', handlePaste)
    return () => window.removeEventListener('paste', handlePaste)
  }, [open, editingThumbnail, handleThumbnailPaste])

  // Crop the image using canvas
  // cropArea stores percentages (0-100), convert to actual pixels
  const cropImage = useCallback(async (): Promise<File | null> => {
    const img = imgRef.current
    if (!img || !previewUrl) return null

    return new Promise((resolve) => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) { resolve(null); return }

      const image = new window.Image()
      image.crossOrigin = 'anonymous'
      image.onload = () => {
        // Convert percentage to actual pixels on the original image
        const cropX = (cropArea.x / 100) * image.naturalWidth
        const cropY = (cropArea.y / 100) * image.naturalHeight
        const cropW = (cropArea.width / 100) * image.naturalWidth
        const cropH = (cropArea.height / 100) * image.naturalHeight

        canvas.width = cropW
        canvas.height = cropH
        ctx.drawImage(image, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH)
        
        canvas.toBlob((blob) => {
          if (blob) {
            resolve(new File([blob], 'thumbnail.jpg', { type: 'image/jpeg' }))
          } else {
            resolve(null)
          }
        }, 'image/jpeg', 0.9)
      }
      image.onerror = () => resolve(null)
      image.src = previewUrl
    })
  }, [previewUrl, cropArea])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.name.trim()) {
      toast({ title: 'Введите название', variant: 'destructive' })
      return
    }
    
    try {
      // Prepare files for upload
      let fullFile = pendingFile
      let thumbnailFile: File | undefined = undefined

      // If previewUrl is a blob but pendingFile is null, recreate file from blob
      if (!fullFile && previewUrl?.startsWith('blob:')) {
        try {
          const response = await fetch(previewUrl)
          const blob = await response.blob()
          fullFile = new File([blob], 'photo.jpg', { type: blob.type || 'image/jpeg' })
        } catch (err) {
          console.error('Failed to recreate file from blob:', err)
        }
      }

      // Priority: separate thumbnail file (with optional crop) > crop from main image
      if (separateThumbnailFile) {
        const croppedThumb = await cropThumbnailImage()
        if (croppedThumb) {
          thumbnailFile = croppedThumb
        }
      } else {
        // If crop area is drawn on main image, create thumbnail from crop
        const isCropped = cropArea.width > 0 && cropArea.height > 0
        if (isCropped && previewUrl) {
          const croppedFile = await cropImage()
          if (croppedFile) {
            thumbnailFile = croppedFile
          }
        }
      }

      if (mode === 'edit' && profile) {
        await updateProfile.mutateAsync({ id: profile.id, data: formData })
        if (fullFile) {
          // New photo uploaded - send both full and thumbnail
          await uploadPhoto.mutateAsync({ name: formData.name, file: fullFile, thumbnail: thumbnailFile })
        } else if (thumbnailFile && profile.photo_full) {
          // Only thumbnail changed on existing photo - update just thumbnail
          await updateThumbnail.mutateAsync({ name: formData.name, thumbnail: thumbnailFile })
        }
        toast({ title: 'Профиль обновлён' })
      } else {
        await createProfile.mutateAsync(formData)
        if (fullFile) {
          await uploadPhoto.mutateAsync({ name: formData.name, file: fullFile, thumbnail: thumbnailFile })
        }
        toast({ title: 'Профиль создан' })
      }
      onOpenChange(false)
    } catch (err) {
      console.error('[handleSubmit] Error:', err)
      toast({ title: 'Ошибка сохранения', variant: 'destructive' })
    }
  }

  const cancelCrop = () => {
    // Clear crop area - no custom thumbnail will be created
    setCropArea({ x: 0, y: 0, width: 0, height: 0 })
    // Also clear separate thumbnail
    setSeparateThumbnailFile(null)
    setSeparateThumbnailUrl(null)
    setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
    setEditingThumbnail(false)
  }

  const dialogTitle = mode === 'create' ? 'Новый профиль' : mode === 'edit' ? 'Редактирование' : profile?.name || 'Просмотр'

  // Calculate dialog size based on actual image pixels
  // Image should be shown at 1:1 scale or smaller, never stretched
  // Mobile: full screen layout
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768
  
  const dialogSize = useMemo(() => {
    // Mobile - fullscreen
    if (isMobile) {
      return { 
        width: typeof window !== 'undefined' ? window.innerWidth : 400, 
        height: typeof window !== 'undefined' ? window.innerHeight : 600,
        isMobile: true
      }
    }
    
    const rightPanelWidth = 320 // w-80
    const maxDialogHeight = typeof window !== 'undefined' ? window.innerHeight - 100 : 800 // 100px padding from edges
    const maxDialogWidth = typeof window !== 'undefined' ? window.innerWidth - 100 : 1200
    const minHeight = 400
    
    if (!imageSize) {
      return { width: Math.min(900, maxDialogWidth), height: minHeight, isMobile: false }
    }
    
    // Image area width = dialog width - right panel
    // We want image to fit at 1:1 or smaller
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
      height: Math.max(minHeight, imgDisplayHeight),
      isMobile: false
    }
  }, [imageSize, isMobile])

  const content = (
    <>
      {/* Photo area - left side on desktop, top on mobile */}
      <div 
        className={`bg-muted flex flex-col items-center justify-center overflow-auto relative ${
          isMobile ? 'h-[80vh] w-full' : 'flex-1'
        }`}
        onDrop={isEditMode && !editingThumbnail ? handleDrop : undefined}
        onDragOver={isEditMode ? (e) => e.preventDefault() : undefined}
      >
        {/* Label for thumbnail editing mode */}
        {editingThumbnail && isEditMode && (
          <div className="absolute top-2 left-2 z-10 bg-blue-500 text-white px-3 py-1 rounded-full text-sm font-medium">
            Редактирование превью
          </div>
        )}
        
        {/* Show thumbnail image when in thumbnail editing mode */}
        {editingThumbnail && isEditMode ? (
          separateThumbnailUrl ? (
            <div 
              className="relative w-full h-full flex items-center justify-center"
              onDrop={(e) => {
                e.preventDefault()
                const file = e.dataTransfer.files[0]
                if (file?.type.startsWith('image/')) {
                  setSeparateThumbnailFile(file)
                  setSeparateThumbnailUrl(URL.createObjectURL(file))
                  setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
                  setCropArea({ x: 0, y: 0, width: 0, height: 0 })
                }
              }}
              onDragOver={(e) => e.preventDefault()}
            >
              <div 
                className="relative select-none"
                style={{ maxWidth: '100%', maxHeight: '100%' }}
                onMouseDown={(e) => {
                  e.preventDefault()
                  const container = e.currentTarget
                  const rect = container.getBoundingClientRect()
                  const startX = ((e.clientX - rect.left) / rect.width) * 100
                  const startY = ((e.clientY - rect.top) / rect.height) * 100
                  
                  setThumbnailCropArea({ x: startX, y: startY, width: 0, height: 0 })
                  
                  const onMove = (moveE: MouseEvent) => {
                    const currentX = ((moveE.clientX - rect.left) / rect.width) * 100
                    const currentY = ((moveE.clientY - rect.top) / rect.height) * 100
                    
                    const newX = Math.min(startX, currentX)
                    const newY = Math.min(startY, currentY)
                    const newW = Math.abs(currentX - startX)
                    const newH = Math.abs(currentY - startY)
                    
                    setThumbnailCropArea({
                      x: Math.max(0, newX),
                      y: Math.max(0, newY),
                      width: Math.min(newW, 100 - Math.max(0, newX)),
                      height: Math.min(newH, 100 - Math.max(0, newY)),
                    })
                  }
                  const onUp = () => {
                    window.removeEventListener('mousemove', onMove)
                    window.removeEventListener('mouseup', onUp)
                  }
                  window.addEventListener('mousemove', onMove)
                  window.addEventListener('mouseup', onUp)
                }}
              >
                <img 
                  src={separateThumbnailUrl} 
                  alt="Thumbnail Preview" 
                  className="max-w-full max-h-full object-contain pointer-events-none block"
                  style={{ maxHeight: 'calc(80vh - 50px)' }}
                  crossOrigin="anonymous"
                />
                {/* Crop overlay for thumbnail */}
                {thumbnailCropArea.width > 0 && thumbnailCropArea.height > 0 && (
                  <div 
                    className="absolute border-2 border-blue-500 bg-blue-500/20 cursor-move shadow-lg"
                    style={{
                      left: `${thumbnailCropArea.x}%`,
                      top: `${thumbnailCropArea.y}%`,
                      width: `${thumbnailCropArea.width}%`,
                      height: `${thumbnailCropArea.height}%`,
                    }}
                    onMouseDown={(e) => {
                      e.stopPropagation()
                      e.preventDefault()
                      const startX = e.clientX
                      const startY = e.clientY
                      const startArea = { ...thumbnailCropArea }
                      const container = e.currentTarget.parentElement
                      if (!container) return

                      const onMove = (moveE: MouseEvent) => {
                        const rect = container.getBoundingClientRect()
                        const dx = ((moveE.clientX - startX) / rect.width) * 100
                        const dy = ((moveE.clientY - startY) / rect.height) * 100
                        setThumbnailCropArea({
                          ...startArea,
                          x: Math.max(0, Math.min(100 - startArea.width, startArea.x + dx)),
                          y: Math.max(0, Math.min(100 - startArea.height, startArea.y + dy)),
                        })
                      }
                      const onUp = () => {
                        window.removeEventListener('mousemove', onMove)
                        window.removeEventListener('mouseup', onUp)
                      }
                      window.addEventListener('mousemove', onMove)
                      window.addEventListener('mouseup', onUp)
                    }}
                  >
                    <div 
                      className="absolute bottom-0 right-0 w-4 h-4 bg-primary cursor-se-resize"
                      onMouseDown={(e) => {
                        e.stopPropagation()
                        e.preventDefault()
                        const startX = e.clientX
                        const startY = e.clientY
                        const startArea = { ...thumbnailCropArea }
                        const container = e.currentTarget.parentElement?.parentElement
                        if (!container) return

                        const onMove = (moveE: MouseEvent) => {
                          const rect = container.getBoundingClientRect()
                          const dw = ((moveE.clientX - startX) / rect.width) * 100
                          const dh = ((moveE.clientY - startY) / rect.height) * 100
                          setThumbnailCropArea({
                            ...startArea,
                            width: Math.max(10, Math.min(100 - startArea.x, startArea.width + dw)),
                            height: Math.max(10, Math.min(100 - startArea.y, startArea.height + dh)),
                          })
                        }
                        const onUp = () => {
                          window.removeEventListener('mousemove', onMove)
                          window.removeEventListener('mouseup', onUp)
                        }
                        window.addEventListener('mousemove', onMove)
                        window.addEventListener('mouseup', onUp)
                      }}
                    />
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div 
              className="text-center text-muted-foreground w-full h-full flex flex-col items-center justify-center"
              onClick={() => document.getElementById('thumbnail-input')?.click()}
              onDrop={(e) => {
                e.preventDefault()
                const file = e.dataTransfer.files[0]
                if (file?.type.startsWith('image/')) {
                  setSeparateThumbnailFile(file)
                  setSeparateThumbnailUrl(URL.createObjectURL(file))
                  setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
                  setCropArea({ x: 0, y: 0, width: 0, height: 0 })
                }
              }}
              onDragOver={(e) => e.preventDefault()}
              style={{ cursor: 'pointer' }}
            >
              <Upload className="w-16 h-16 mx-auto mb-4" />
              <p className="text-lg px-4">{isMobile ? 'Нажмите для загрузки превью' : 'Нажмите, перетащите или вставьте (Ctrl+V) превью'}</p>
            </div>
          )
        ) : previewUrl ? (
          <div 
            className="relative w-full h-full flex items-center justify-center select-none"
            onMouseDown={isEditMode && photoMode === 'crop' && !separateThumbnailUrl ? (e) => {
              e.preventDefault() // Prevent browser selection
              // Start drawing new crop area from click point
              const container = e.currentTarget
              const rect = container.getBoundingClientRect()
              const startX = ((e.clientX - rect.left) / rect.width) * 100
              const startY = ((e.clientY - rect.top) / rect.height) * 100
              
              setCropArea({ x: startX, y: startY, width: 0, height: 0 })
              
              const onMove = (moveE: MouseEvent) => {
                const currentX = ((moveE.clientX - rect.left) / rect.width) * 100
                const currentY = ((moveE.clientY - rect.top) / rect.height) * 100
                
                const newX = Math.min(startX, currentX)
                const newY = Math.min(startY, currentY)
                const newW = Math.abs(currentX - startX)
                const newH = Math.abs(currentY - startY)
                
                setCropArea({
                  x: Math.max(0, newX),
                  y: Math.max(0, newY),
                  width: Math.min(newW, 100 - Math.max(0, newX)),
                  height: Math.min(newH, 100 - Math.max(0, newY)),
                })
              }
              const onUp = () => {
                window.removeEventListener('mousemove', onMove)
                window.removeEventListener('mouseup', onUp)
              }
              window.addEventListener('mousemove', onMove)
              window.addEventListener('mouseup', onUp)
            } : undefined}
            // Touch support for mobile crop
            onTouchStart={isEditMode && photoMode === 'crop' && !separateThumbnailUrl ? (e) => {
              e.preventDefault()
              const touch = e.touches[0]
              const container = e.currentTarget
              const rect = container.getBoundingClientRect()
              const startX = ((touch.clientX - rect.left) / rect.width) * 100
              const startY = ((touch.clientY - rect.top) / rect.height) * 100
              
              setCropArea({ x: startX, y: startY, width: 0, height: 0 })
              
              const onMove = (moveE: TouchEvent) => {
                const moveTouch = moveE.touches[0]
                const currentX = ((moveTouch.clientX - rect.left) / rect.width) * 100
                const currentY = ((moveTouch.clientY - rect.top) / rect.height) * 100
                
                const newX = Math.min(startX, currentX)
                const newY = Math.min(startY, currentY)
                const newW = Math.abs(currentX - startX)
                const newH = Math.abs(currentY - startY)
                
                setCropArea({
                  x: Math.max(0, newX),
                  y: Math.max(0, newY),
                  width: Math.min(newW, 100 - Math.max(0, newX)),
                  height: Math.min(newH, 100 - Math.max(0, newY)),
                })
              }
              const onEnd = () => {
                window.removeEventListener('touchmove', onMove)
                window.removeEventListener('touchend', onEnd)
              }
              window.addEventListener('touchmove', onMove, { passive: false })
              window.addEventListener('touchend', onEnd)
            } : undefined}
          >
                <img 
                  ref={imgRef}
                  src={previewUrl} 
                  alt="Preview" 
                  className="max-w-full max-h-full object-contain pointer-events-none"
                  crossOrigin="anonymous"
                />
                {/* Crop overlay - only in edit mode and when no separate thumbnail */}
                {isEditMode && photoMode === 'crop' && !separateThumbnailUrl && cropArea.width > 0 && cropArea.height > 0 && (
                  <div 
                    className="absolute border-2 border-blue-500 bg-blue-500/20 cursor-move shadow-lg"
                    style={{
                      left: `${cropArea.x}%`,
                      top: `${cropArea.y}%`,
                      width: `${cropArea.width}%`,
                      height: `${cropArea.height}%`,
                    }}
                    onMouseDown={(e) => {
                      e.stopPropagation()
                      e.preventDefault()
                      const startX = e.clientX
                      const startY = e.clientY
                      const startArea = { ...cropArea }
                      const container = e.currentTarget.parentElement
                      if (!container) return

                      const onMove = (moveE: MouseEvent) => {
                        const rect = container.getBoundingClientRect()
                        const dx = ((moveE.clientX - startX) / rect.width) * 100
                        const dy = ((moveE.clientY - startY) / rect.height) * 100
                        setCropArea({
                          ...startArea,
                          x: Math.max(0, Math.min(100 - startArea.width, startArea.x + dx)),
                          y: Math.max(0, Math.min(100 - startArea.height, startArea.y + dy)),
                        })
                      }
                      const onUp = () => {
                        window.removeEventListener('mousemove', onMove)
                        window.removeEventListener('mouseup', onUp)
                      }
                      window.addEventListener('mousemove', onMove)
                      window.addEventListener('mouseup', onUp)
                    }}
                  >
                    {/* Resize handle */}
                    <div 
                      className="absolute bottom-0 right-0 w-4 h-4 bg-primary cursor-se-resize"
                      onMouseDown={(e) => {
                        e.stopPropagation()
                        e.preventDefault()
                        const startX = e.clientX
                        const startY = e.clientY
                        const startArea = { ...cropArea }
                        const container = e.currentTarget.parentElement?.parentElement
                        if (!container) return

                        const onMove = (moveE: MouseEvent) => {
                          const rect = container.getBoundingClientRect()
                          const dw = ((moveE.clientX - startX) / rect.width) * 100
                          const dh = ((moveE.clientY - startY) / rect.height) * 100
                          setCropArea({
                            ...startArea,
                            width: Math.max(10, Math.min(100 - startArea.x, startArea.width + dw)),
                            height: Math.max(10, Math.min(100 - startArea.y, startArea.height + dh)),
                          })
                        }
                        const onUp = () => {
                          window.removeEventListener('mousemove', onMove)
                          window.removeEventListener('mouseup', onUp)
                        }
                        window.addEventListener('mousemove', onMove)
                        window.addEventListener('mouseup', onUp)
                      }}
                    />
                  </div>
                )}
              </div>
            ) : (
              <div 
                className="text-center text-muted-foreground w-full h-full flex flex-col items-center justify-center"
                onClick={isEditMode ? () => document.getElementById('photo-input')?.click() : undefined}
                style={{ cursor: isEditMode ? 'pointer' : 'default' }}
              >
                {isEditMode ? (
                  <>
                    <Upload className="w-16 h-16 mx-auto mb-4" />
                    <p className="text-lg px-4">{isMobile ? 'Нажмите для загрузки' : 'Нажмите, перетащите или вставьте (Ctrl+V)'}</p>
                  </>
                ) : (
                  <>
                    <Image className="w-16 h-16 mx-auto mb-4" />
                    <p className="text-lg">Нет фото</p>
                  </>
                )}
              </div>
            )}
            {isEditMode && (
              <>
                <input 
                  id="photo-input"
                  type="file" 
                  accept="image/*" 
                  className="hidden" 
                  onChange={handleFileChange} 
                />
                <input 
                  id="thumbnail-input"
                  type="file" 
                  accept="image/*" 
                  className="hidden" 
                  onChange={handleThumbnailFileChange} 
                />
              </>
            )}
          </div>

          {/* Right panel - side on desktop, bottom on mobile */}
          <div className={`border-l bg-background p-4 flex flex-col ${
            isMobile ? 'flex-1 overflow-y-auto border-l-0 border-t' : 'w-80'
          }`}>
            <div className="flex-1 space-y-4 overflow-y-auto">
              {isViewMode ? (
                <>
                  {/* View mode - display info */}
                  <h2 className="text-xl font-semibold">{profile?.name}</h2>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Кол-во на подвесе:</span>
                      <span className="font-medium">{profile?.quantity_per_hanger ?? '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Длина:</span>
                      <span className="font-medium">{profile?.length ? `${profile.length} мм` : '—'}</span>
                    </div>
                  </div>
                  {profile?.notes && (
                    <div className="pt-2 border-t">
                      <span className="text-sm text-muted-foreground">Примечания:</span>
                      <p className="mt-1 text-sm">{profile.notes}</p>
                    </div>
                  )}
                </>
              ) : (
                <>
                  {/* Edit mode - form fields */}
                  <div className="space-y-2">
                    <Label htmlFor="name">Название *</Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                      placeholder="Например: АЛС-100"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="quantity">Кол-во на подвесе</Label>
                    <Input
                      id="quantity"
                      type="number"
                      value={formData.quantity_per_hanger ?? ''}
                      onChange={(e) => setFormData(prev => ({ 
                        ...prev, 
                        quantity_per_hanger: e.target.value ? parseInt(e.target.value) : null 
                      }))}
                      placeholder="шт"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="length">Длина (мм)</Label>
                    <Input
                      id="length"
                      type="number"
                      value={formData.length ?? ''}
                      onChange={(e) => setFormData(prev => ({ 
                        ...prev, 
                        length: e.target.value ? parseFloat(e.target.value) : null 
                      }))}
                      placeholder="мм"
                    />
                  </div>
              
                  <div className="space-y-2">
                    <Label htmlFor="notes">Примечания</Label>
                    <Textarea
                      id="notes"
                      value={formData.notes ?? ''}
                      onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value || null }))}
                      placeholder="Дополнительная информация..."
                      rows={isMobile ? 2 : 3}
                    />
                  </div>

                  {/* Photo buttons */}
                  {previewUrl && (
                    <div className="space-y-2 pt-2 border-t">
                      {editingThumbnail ? (
                        <>
                          <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => setEditingThumbnail(false)}>
                            ← Вернуться к фото
                          </Button>
                          {separateThumbnailUrl && (
                            <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => {
                              setSeparateThumbnailFile(null)
                              setSeparateThumbnailUrl(null)
                              setThumbnailCropArea({ x: 0, y: 0, width: 0, height: 0 })
                            }}>
                              Очистить превью
                            </Button>
                          )}
                          <p className="text-xs text-muted-foreground text-center">
                            {separateThumbnailUrl 
                              ? 'Выделите область для кропа или оставьте как есть' 
                              : 'Перетащите, вставьте (Ctrl+V) или нажмите для загрузки'}
                          </p>
                        </>
                      ) : (
                        <>
                          <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => document.getElementById('photo-input')?.click()}>
                            Заменить фото
                          </Button>
                          <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => setEditingThumbnail(true)}>
                            {separateThumbnailUrl ? 'Редактировать превью' : 'Загрузить превью отдельно'}
                          </Button>
                          <Button type="button" variant="outline" size="sm" className="w-full" onClick={cancelCrop}>
                            Сбросить превью
                          </Button>
                          {!isMobile && !separateThumbnailUrl && (
                            <p className="text-xs text-muted-foreground text-center">
                              Можно выделить область на фото или загрузить превью отдельно
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
            
            {/* Footer buttons - only in edit mode */}
            {isEditMode && (
              <div className="flex gap-2 pt-4 border-t mt-4">
                <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
                  Отмена
                </Button>
                <Button type="submit" className="flex-1" disabled={createProfile.isPending || updateProfile.isPending || uploadPhoto.isPending}>
                  {mode === 'create' ? 'Создать' : 'Сохранить'}
                </Button>
              </div>
            )}
          </div>
        </>
      )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent 
        className={`p-0 gap-0 ${
          isMobile 
            ? 'w-screen h-screen max-w-none max-h-none rounded-none top-0 left-0 translate-x-0 translate-y-0' 
            : 'top-[5%] translate-y-0'
        }`}
        style={isMobile ? undefined : { width: `${dialogSize.width}px`, height: `${dialogSize.height}px`, maxWidth: 'calc(100vw - 100px)' }}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{dialogTitle}</DialogTitle>
          <DialogDescription>Профиль</DialogDescription>
        </DialogHeader>
        
        {isEditMode ? (
          <form onSubmit={handleSubmit} className={`flex h-full ${isMobile ? 'flex-col' : ''}`}>
            {content}
          </form>
        ) : (
          <div className={`flex h-full ${isMobile ? 'flex-col' : ''}`}>
            {content}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}


// Delete Confirmation Dialog
function DeleteConfirmDialog({
  profile,
  open,
  onOpenChange,
}: {
  profile: Profile | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { toast } = useToast()
  const deleteProfile = useDeleteProfile()

  const handleDelete = async () => {
    if (!profile) return
    try {
      await deleteProfile.mutateAsync(profile.id)
      toast({ title: 'Профиль удалён' })
      onOpenChange(false)
    } catch {
      toast({ title: 'Ошибка удаления', variant: 'destructive' })
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить профиль?</AlertDialogTitle>
          <AlertDialogDescription>
            Профиль "{profile?.name}" будет удалён вместе с фотографиями. Это действие нельзя отменить.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">
            Удалить
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function SearchSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {[...Array(6)].map((_, i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex gap-4">
              <Skeleton className="w-20 h-20 rounded-md" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}


export default function Catalog() {
  // State
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>(() => 
    (localStorage.getItem(STORAGE_KEYS.viewMode) as ViewMode) || 'grid'
  )
  const [sortField, setSortField] = useState<SortField>(() => 
    (localStorage.getItem(STORAGE_KEYS.sortField) as SortField) || 'name'
  )
  const [sortDirection, setSortDirection] = useState<SortDirection>(() => 
    (localStorage.getItem(STORAGE_KEYS.sortDirection) as SortDirection) || 'asc'
  )
  
  // Dialog states
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null)
  const [photoDialogOpen, setPhotoDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editMode, setEditMode] = useState<'create' | 'edit'>('edit')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)

  // Mobile detection
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth < 768)
  
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      // Force grid view on mobile
      if (mobile && viewMode === 'table') {
        setViewMode('grid')
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [viewMode])

  // Data
  const { data: allProfiles, isLoading: loadingAll } = useCatalogAll()
  const { data: searchResults, isLoading: loadingSearch } = useCatalogSearch(debouncedQuery)

  // Persist settings
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.viewMode, viewMode)
  }, [viewMode])
  
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.sortField, sortField)
  }, [sortField])
  
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.sortDirection, sortDirection)
  }, [sortDirection])

  // ESC to close dialogs
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPhotoDialogOpen(false)
        setEditDialogOpen(false)
        setDeleteDialogOpen(false)
      }
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(timer)
  }, [query])

  // Sort and filter data
  const displayData = useMemo(() => {
    const data = debouncedQuery ? searchResults : allProfiles
    if (!data) return []
    
    return [...data].sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name':
          cmp = a.name.localeCompare(b.name, 'ru')
          break
        case 'updated_at':
          cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()
          break
        case 'has_photo':
          cmp = (a.photo_thumb ? 1 : 0) - (b.photo_thumb ? 1 : 0)
          break
      }
      return sortDirection === 'asc' ? cmp : -cmp
    })
  }, [allProfiles, searchResults, debouncedQuery, sortField, sortDirection])

  const isLoading = debouncedQuery ? loadingSearch : loadingAll

  // Handlers
  const handleSelectProfile = useCallback((profile: Profile) => {
    setSelectedProfile(profile)
    setPhotoDialogOpen(true)
  }, [])

  const handleEditProfile = useCallback((profile: Profile) => {
    setSelectedProfile(profile)
    setEditMode('edit')
    setEditDialogOpen(true)
  }, [])

  const handleDeleteProfile = useCallback((profile: Profile) => {
    setSelectedProfile(profile)
    setDeleteDialogOpen(true)
  }, [])

  const handleCreateNew = useCallback(() => {
    setSelectedProfile(null)
    setEditMode('create')
    setEditDialogOpen(true)
  }, [])

  const toggleSort = useCallback((field: SortField) => {
    if (sortField === field) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }, [sortField])

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-4 w-4 ml-1" />
    return sortDirection === 'asc' 
      ? <ArrowUp className="h-4 w-4 ml-1" /> 
      : <ArrowDown className="h-4 w-4 ml-1" />
  }

  return (
    <div className="container mx-auto p-4 md:p-6 max-w-6xl pb-20 md:pb-6">
      {/* Header */}
      <div className="mb-4 md:mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 md:gap-4">
            <h1 className="text-xl md:text-2xl font-bold">Каталог профилей</h1>
            {displayData.length > 0 && (
              <Badge variant="secondary" className="hidden sm:inline-flex">{displayData.length} профилей</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* View mode buttons - desktop only */}
            {!isMobile && (
              <>
                <Button variant="outline" size="icon" onClick={() => setViewMode('grid')} 
                  className={viewMode === 'grid' ? 'bg-accent' : ''}>
                  <Grid className="h-4 w-4" />
                </Button>
                <Button variant="outline" size="icon" onClick={() => setViewMode('table')}
                  className={viewMode === 'table' ? 'bg-accent' : ''}>
                  <List className="h-4 w-4" />
                </Button>
                <Button onClick={handleCreateNew}>
                  <Plus className="h-4 w-4 mr-2" />
                  Создать
                </Button>
              </>
            )}
          </div>
        </div>
        
        {/* Search & Sort */}
        <div className="flex gap-2 md:gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder={isMobile ? "Поиск..." : "Поиск по названию, примечаниям..."}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-10 pr-10"
            />
            {query && (
              <Button variant="ghost" size="sm" className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                onClick={() => setQuery('')}>
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
          
          <div className="flex">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="rounded-r-none border-r-0">
                  <ArrowUpDown className="h-4 w-4 md:mr-2" />
                  <span className="hidden md:inline">Сортировка</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => toggleSort('name')}>
                  По алфавиту
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => toggleSort('updated_at')}>
                  По дате изменения
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => toggleSort('has_photo')}>
                  С фото
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button 
              variant="outline" 
              size="icon"
              className="rounded-l-none"
              onClick={() => setSortDirection(d => d === 'asc' ? 'desc' : 'asc')}
              title={sortDirection === 'asc' ? 'По возрастанию' : 'По убыванию'}
            >
              {sortDirection === 'asc' ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Loading */}
      {isLoading && <SearchSkeleton />}

      {/* Empty state */}
      {!isLoading && displayData.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>{debouncedQuery ? `Ничего не найдено по запросу "${debouncedQuery}"` : 'Нет профилей'}</p>
        </div>
      )}

      {/* Grid View */}
      {!isLoading && (isMobile || viewMode === 'grid') && displayData.length > 0 && (
        <div className="grid gap-3 md:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {displayData.map((profile) => (
            <ProfileCard
              key={profile.id}
              profile={profile}
              onSelect={handleSelectProfile}
              onEdit={handleEditProfile}
              onDelete={handleDeleteProfile}
              isMobile={isMobile}
            />
          ))}
        </div>
      )}

      {/* Table View - desktop only */}
      {!isLoading && !isMobile && viewMode === 'table' && displayData.length > 0 && (
        <div className="border rounded-lg">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">Фото</TableHead>
                <TableHead className="cursor-pointer" onClick={() => toggleSort('name')}>
                  <div className="flex items-center">Название <SortIcon field="name" /></div>
                </TableHead>
                <TableHead>Кол-во</TableHead>
                <TableHead>Длина</TableHead>
                <TableHead>Примечания</TableHead>
                <TableHead className="cursor-pointer" onClick={() => toggleSort('updated_at')}>
                  <div className="flex items-center">Изменён <SortIcon field="updated_at" /></div>
                </TableHead>
                <TableHead className="w-24"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayData.map((profile) => (
                <TableRow key={profile.id} className="cursor-pointer" onClick={() => handleSelectProfile(profile)}>
                  <TableCell>
                    <div className="w-10 h-10 bg-muted rounded flex items-center justify-center overflow-hidden">
                      {profile.photo_thumb ? (
                        <img src={getPhotoUrl(profile.photo_thumb, profile.updated_at)!} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <Image className="w-4 h-4 text-muted-foreground" />
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="font-medium">{profile.name}</TableCell>
                  <TableCell>{profile.quantity_per_hanger ?? '—'}</TableCell>
                  <TableCell>{profile.length ? `${profile.length} мм` : '—'}</TableCell>
                  <TableCell className="max-w-xs truncate">{profile.notes ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {new Date(profile.updated_at).toLocaleDateString('ru')}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button size="icon" variant="ghost" className="h-8 w-8" 
                        onClick={(e) => { e.stopPropagation(); handleEditProfile(profile) }}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive"
                        onClick={(e) => { e.stopPropagation(); handleDeleteProfile(profile) }}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Floating Action Button - Mobile only */}
      {isMobile && (
        <Button 
          onClick={handleCreateNew}
          size="icon"
          className="fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-50"
        >
          <Plus className="h-6 w-6" />
        </Button>
      )}

      {/* Dialogs */}
      <ProfileDialog profile={selectedProfile} open={photoDialogOpen} onOpenChange={setPhotoDialogOpen} mode="view" />
      <ProfileDialog profile={selectedProfile} open={editDialogOpen} onOpenChange={setEditDialogOpen} mode={editMode} />
      <DeleteConfirmDialog profile={selectedProfile} open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen} />
    </div>
  )
}
