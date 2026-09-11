// Фото профиля: путь из БД → URL для <img>.
// Пути в БД бывают как «/static/images/...», так и «images/...».

export function photoUrl(path: string | null | undefined, cacheBuster?: string | number): string | null {
  if (!path) return null
  const base = path.startsWith('/') ? path : `/static/${path}`
  // Сбрасываем кэш браузера и по updated_at, и по текущему времени
  const bust = cacheBuster ? `${cacheBuster}_${Date.now()}` : Date.now()
  return `${base}?v=${bust}`
}
