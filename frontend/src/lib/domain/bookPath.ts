// Подпись пути к книге для компактных списков.

/**
 * Последние два сегмента пути: у двух книг часто одинаковое имя файла, и в
 * списке «Учет КПЗ 2026.xlsm» из разных папок выглядит как один и тот же путь.
 */
export function pathHint(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.slice(-2).join("\\");
}
