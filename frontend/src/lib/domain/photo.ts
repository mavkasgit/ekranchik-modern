// Фото профиля: путь из БД → URL для <img>.
// Пути в БД бывают как «/static/images/...», так и «images/...».
// Версия файла приходит с бэкенда (mtime+size) и уходит в `?v=`: так замена
// фото мимо API — синк каталога, ручное копирование — тоже сбрасывает кэш
// `/static/`, который nginx отдаёт с долгим `immutable`.

export function photoUrl(path: string | null | undefined, version?: string | null): string | null {
  if (!path) return null;
  if (path.startsWith("http")) return path;

  const normalized = path.replace(/\\/g, "/");
  const base = normalized.startsWith("/") ? normalized : `/static/${normalized}`;
  if (!version) return base;
  // Не Date.now(): новый URL на каждый рендер заставлял киоск заново качать
  // все превью по кругу, хотя файлы не менялись.
  return `${base}?v=${encodeURIComponent(version)}`;
}
