import { useState, useCallback } from 'react'
import { Search, Image, Camera, Copy } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
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
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { 
  useMissingPhotos, 
  useRecentProfiles, 
  useRecentMissing,
  useDuplicateSearch 
} from '@/hooks/useAnalysis'
import { useUploadPhoto } from '@/hooks/useCatalog'
import type { Profile, ProfileSearchResult } from '@/types/profile'
import type { RecentProfile } from '@/api/analysis'

type TabType = 'missing' | 'recent' | 'recentMissing' | 'duplicates'

function PhotoUploadDialog({
  profile,
  open,
  onOpenChange,
}: {
  profile: Profile | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const uploadPhoto = useUploadPhoto()
  
  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && profile) {
      await uploadPhoto.mutateAsync({ name: profile.name, file })
      onOpenChange(false)
    }
  }, [profile, uploadPhoto, onOpenChange])

  if (!profile) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Загрузить фото: {profile.name}</DialogTitle>
        </DialogHeader>
        
        <div className="space-y-4">
          <div className="aspect-video bg-muted rounded-lg flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <Camera className="w-16 h-16 mx-auto mb-2" />
              <p>Выберите фото для загрузки</p>
            </div>
          </div>
          
          <Button asChild className="w-full">
            <label className="cursor-pointer">
              <Camera className="w-4 h-4 mr-2" />
              Выбрать файл
              <input 
                type="file" 
                accept="image/*" 
                className="hidden"
                onChange={handleFileChange}
              />
            </label>
          </Button>

          <div className="text-sm text-muted-foreground">
            <p>Использований: {profile.usage_count}</p>
            {profile.notes && <p>Примечания: {profile.notes}</p>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function MissingPhotosTab() {
  const { data, isLoading } = useMissingPhotos()
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  if (isLoading) {
    return <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
  }

  if (!data?.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Image className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>Все профили имеют фото!</p>
      </div>
    )
  }

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Профиль</TableHead>
              <TableHead className="w-32">Использований</TableHead>
              <TableHead className="w-32">Действие</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((profile) => (
              <TableRow key={profile.id}>
                <TableCell>
                  <div>
                    <span className="font-medium">{profile.name}</span>
                    {profile.notes && (
                      <p className="text-sm text-muted-foreground truncate max-w-md">
                        {profile.notes}
                      </p>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{profile.usage_count}</Badge>
                </TableCell>
                <TableCell>
                  <Button 
                    size="sm" 
                    variant="outline"
                    onClick={() => { setSelectedProfile(profile); setDialogOpen(true) }}
                  >
                    <Camera className="w-4 h-4 mr-1" />
                    Фото
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      
      <PhotoUploadDialog
        profile={selectedProfile}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </>
  )
}

function RecentProfilesTab({ missingOnly = false }: { missingOnly?: boolean }) {
  const { data, isLoading } = missingOnly ? useRecentMissing() : useRecentProfiles()

  if (isLoading) {
    return <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
  }

  if (!data?.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>Нет данных</p>
      </div>
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-20">№</TableHead>
            <TableHead className="w-28">Дата</TableHead>
            <TableHead>Профиль</TableHead>
            <TableHead className="w-24">Фото</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((item: RecentProfile, idx: number) => (
            <TableRow key={`${item.number}-${idx}`}>
              <TableCell>{item.number}</TableCell>
              <TableCell>{item.date}</TableCell>
              <TableCell className="font-medium">{item.profile}</TableCell>
              <TableCell>
                {item.has_photo ? (
                  <Badge variant="default">Есть</Badge>
                ) : (
                  <Badge variant="destructive">Нет</Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function DuplicatesTab() {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const { data, isLoading } = useDuplicateSearch(debouncedQuery)

  const handleSearch = useCallback((value: string) => {
    setQuery(value)
    const timer = setTimeout(() => setDebouncedQuery(value), 300)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder="Введите название профиля..."
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      {!debouncedQuery && (
        <div className="text-center py-12 text-muted-foreground">
          <Copy className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>Введите название для поиска похожих профилей</p>
        </div>
      )}

      {isLoading && (
        <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
      )}

      {data && data.length === 0 && debouncedQuery && (
        <div className="text-center py-12 text-muted-foreground">
          <p>Похожих профилей не найдено</p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Профиль</TableHead>
                <TableHead className="w-28">Схожесть</TableHead>
                <TableHead className="w-24">Фото</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((profile: ProfileSearchResult) => (
                <TableRow key={profile.id}>
                  <TableCell className="font-medium">{profile.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {profile.similarity ? `${Math.round(profile.similarity * 100)}%` : '—'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {profile.photo_thumb ? (
                      <Badge variant="default">Есть</Badge>
                    ) : (
                      <Badge variant="secondary">Нет</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

export default function Analysis() {
  const [activeTab, setActiveTab] = useState<TabType>('missing')

  const tabs: { id: TabType; label: string }[] = [
    { id: 'missing', label: 'Без фото' },
    { id: 'recent', label: 'Недавние' },
    { id: 'recentMissing', label: 'Недавние без фото' },
    { id: 'duplicates', label: 'Дубликаты' },
  ]

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <h1 className="text-2xl font-bold mb-6">Анализ профилей</h1>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex gap-2 flex-wrap">
            {tabs.map((tab) => (
              <Button
                key={tab.id}
                variant={activeTab === tab.id ? 'default' : 'outline'}
                size="sm"
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {activeTab === 'missing' && <MissingPhotosTab />}
          {activeTab === 'recent' && <RecentProfilesTab />}
          {activeTab === 'recentMissing' && <RecentProfilesTab missingOnly />}
          {activeTab === 'duplicates' && <DuplicatesTab />}
        </CardContent>
      </Card>
    </div>
  )
}
