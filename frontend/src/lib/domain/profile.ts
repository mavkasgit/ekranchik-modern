// Профиль подвеса → компактный текст для ячейки таблицы.

export function profileText(profile: string | null | undefined): string {
  if (!profile) return '—'
  const normalized = profile
    .replace(/\s+/g, '')
    .replace(/[^0-9()+*xхX×\/.,;]/g, '')
  return normalized || '—'
}
