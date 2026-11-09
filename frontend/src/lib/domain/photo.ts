// Фото профиля: путь из БД → URL для <img>.
// Пути в БД бывают как «/static/images/...», так и «images/...».

export function photoUrl(
  path: string | null | undefined,
  cacheBuster?: string | number,
): string | null {
  if (!path) return null;
  const base = path.startsWith("/") ? path : `/static/${path}`;
  // Сбрасываем кэш только при смене фото: updated_at меняется при загрузке и
  // удалении. Date.now() здесь означал новый URL на каждый рендер — киоск
  // заново скачивал все превью по кругу, хотя файлы не менялись.
  return cacheBuster ? `${base}?v=${cacheBuster}` : base;
}
