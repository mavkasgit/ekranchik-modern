// Память последних путей к книге учёта: путь на сетевом диске длинный, и
// оператору проще поправить прошлый путь на месте, чем набирать его заново.

export const RECENT_PATHS_LIMIT = 3;

/**
 * Новый путь встаёт первым, дубли не копятся, длина ограничена.
 * Пустой путь память не меняет: «Отмена» не должна стирать историю.
 */
export function rememberRecentPath(
  paths: readonly string[],
  path: string,
  limit: number = RECENT_PATHS_LIMIT,
): string[] {
  const trimmed = path.trim();
  const result: string[] = [];
  const source = trimmed ? [trimmed, ...paths] : [...paths];

  for (const item of source) {
    const value = item.trim();
    if (!value || result.includes(value)) continue;
    result.push(value);
    if (result.length >= limit) break;
  }
  return result;
}

/** Разбор того, что лежит в localStorage: мусор и дубли наружу не отдаём. */
export function parseRecentPaths(raw: string | null, limit: number = RECENT_PATHS_LIMIT): string[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return rememberRecentPath(
      parsed.filter((item): item is string => typeof item === "string"),
      "",
      limit,
    );
  } catch {
    return [];
  }
}
