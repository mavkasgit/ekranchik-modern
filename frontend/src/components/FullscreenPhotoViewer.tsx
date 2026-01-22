import { useEffect, useState } from 'react'
import { X, Maximize2, Minimize2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface FullscreenPhotoViewerProps {
  open: boolean
  onClose: () => void
  photoUrl: string | null
  title?: string
}

export function FullscreenPhotoViewer({
  open,
  onClose,
  photoUrl,
  title = 'Фото',
}: FullscreenPhotoViewerProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  useEffect(() => {
    if (!open) {
      setIsFullscreen(false)
    }
  }, [open])

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

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen)
  }

  if (!photoUrl) return null

  if (isFullscreen) {
    return (
      <div 
        className="fixed inset-0 z-[100] bg-black flex items-center justify-center"
        onClick={() => setIsFullscreen(false)}
      >
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
          alt={title}
          className="max-w-full max-h-full object-contain cursor-pointer"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-[90vw] max-h-[90vh] p-0">
        <DialogHeader className="sr-only">
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="relative w-full h-full flex items-center justify-center bg-muted">
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-12 z-10"
            onClick={toggleFullscreen}
            title="Развернуть на весь экран"
          >
            <Maximize2 className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 z-10"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
          <img
            src={photoUrl}
            alt={title}
            className="max-w-full max-h-[90vh] object-contain cursor-pointer"
            onClick={toggleFullscreen}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
