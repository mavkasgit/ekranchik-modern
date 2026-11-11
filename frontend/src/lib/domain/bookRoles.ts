// Список книг в диалоге учёта: строки путей и их роли.
//
// Владелец ролей — сервер (ADR 0009). Здесь только черновик диалога: какие
// строки показать и как переносить роль с одной книги на другую. Ровно одна
// основная и не больше одной запасной — иначе на экране появилось бы два
// источника, и правило на сервере осталось бы без ответа.

export type BookRowRole = "main" | "reserve" | "none";

export interface BookRow {
  path: string;
  role: BookRowRole;
}

function pushUnique(
  rows: BookRow[],
  seen: Set<string>,
  path: string | null | undefined,
  role: BookRowRole,
) {
  const value = path?.trim();
  if (!value || seen.has(value)) return;
  seen.add(value);
  rows.push({ path: value, role });
}

/**
 * Черновик для диалога: основная и запасная книги + последние введённые пути.
 *
 * Дубли не показываются: один и тот же файл не может быть и основной, и
 * запасной, а список «последних» пересекается с текущими ролями.
 */
export function buildBookRows(
  mainPath: string | null | undefined,
  reservePath: string | null | undefined,
  remembered: readonly string[],
): BookRow[] {
  const rows: BookRow[] = [];
  const seen = new Set<string>();
  pushUnique(rows, seen, mainPath, "main");
  pushUnique(rows, seen, reservePath, "reserve");
  for (const path of remembered) pushUnique(rows, seen, path, "none");
  return rows;
}

/** Назначить роль пути; прежний носитель этой роли становится обычным путём. */
export function assignBookRole(
  rows: readonly BookRow[],
  path: string,
  role: BookRowRole,
): BookRow[] {
  return rows.map((row) => {
    if (row.path === path) return { ...row, role };
    if (role !== "none" && row.role === role) return { ...row, role: "none" };
    return row;
  });
}

/** Поправить путь на месте. Существующий путь не дублируется и не заменяется. */
export function renameBookPath(
  rows: readonly BookRow[],
  path: string,
  nextPath: string,
): BookRow[] {
  const value = nextPath.trim();
  if (!value) return [...rows];
  if (rows.some((row) => row.path === value && row.path !== path)) return [...rows];
  return rows.map((row) => (row.path === path ? { ...row, path: value } : row));
}
