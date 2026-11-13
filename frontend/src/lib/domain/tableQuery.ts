import { normalizeText } from "./textNormalize";

// Сортировка таблицы: несколько ключей по приоритету. Движок тот же, что в
// ktm2000, но без сервера — витрина держит весь каталог в памяти.

export type SortOrder = "asc" | "desc";

/** Значение, по которому колонка сортирует строку. `null` — «пусто». */
export type SortValue = string | number | null;

export interface SortConfig<Field extends string> {
  field: Field;
  order: SortOrder;
}

export interface TableQueryResult<T> {
  rows: T[];
  totalCount: number;
  filteredCount: number;
}

/**
 * Больше трёх ключей шапка не читается: бейджи приоритетов сливаются, а
 * четвёртый клик оператор уже не связывает с порядком строк. Четвёртая
 * сортировка вытесняет самую старую, а не игнорируется молча.
 */
export const MAX_SORT_FIELDS = 3;

/** Коллатор с числами: «ЮП-2» раньше «ЮП-10», кириллица по алфавиту. */
const STRING_COLLATOR = new Intl.Collator(["ru-RU", "en-US"], {
  sensitivity: "base",
  numeric: true,
});

/** Пустое значение всегда уезжает в конец, независимо от направления. */
function isEmptyValue(value: SortValue): boolean {
  return value === null || value === "" || (typeof value === "number" && Number.isNaN(value));
}

export function compareSortValues(left: SortValue, right: SortValue, order: SortOrder): number {
  const multiplier = order === "asc" ? 1 : -1;

  const leftEmpty = isEmptyValue(left);
  const rightEmpty = isEmptyValue(right);
  if (leftEmpty || rightEmpty) {
    if (leftEmpty && rightEmpty) return 0;
    return leftEmpty ? 1 : -1;
  }

  if (typeof left === "number" && typeof right === "number") {
    return (left - right) * multiplier;
  }

  return (
    STRING_COLLATOR.compare(normalizeText(String(left)), normalizeText(String(right))) * multiplier
  );
}

/** Сортирует копию списка: несколько ключей, набор ключей не мутируется. */
export function sortRows<T, Field extends string>(
  rows: readonly T[],
  sorts: readonly SortConfig<Field>[],
  sortDefs: ReadonlyMap<Field, (row: T) => SortValue>,
): T[] {
  if (sorts.length === 0) return [...rows];

  return [...rows].sort((left, right) => {
    for (const config of sorts) {
      const read = sortDefs.get(config.field);
      if (!read) continue;
      const cmp = compareSortValues(read(left), read(right), config.order);
      if (cmp !== 0) return cmp;
    }
    return 0;
  });
}

export interface TableQueryOptions<T, Field extends string> {
  rows: readonly T[];
  searchQuery: string;
  /** Строка, по которой ищет общий поиск. Нормализуется здесь. */
  searchText: (row: T) => string;
  filterPredicate: ((row: T) => boolean) | null;
  sorts: readonly SortConfig<Field>[];
  sortDefs: ReadonlyMap<Field, (row: T) => SortValue>;
}

/** Полный конвейер: поиск → фильтр колонок → сортировка. */
export function processTableRows<T, Field extends string>({
  rows,
  searchQuery,
  searchText,
  filterPredicate,
  sorts,
  sortDefs,
}: TableQueryOptions<T, Field>): TableQueryResult<T> {
  const totalCount = rows.length;
  const needle = normalizeText(searchQuery.trim());

  let result: readonly T[] = needle
    ? rows.filter((row) => normalizeText(searchText(row)).includes(needle))
    : rows;
  const filteredCount = result.length;

  if (filterPredicate) {
    result = result.filter(filterPredicate);
  }

  return {
    rows: sortRows(result, sorts, sortDefs),
    totalCount,
    filteredCount,
  };
}

/**
 * Цикл клика по сортируемой колонке: нет → по возрастанию → по убыванию →
 * снята. Новый ключ добавляется в конец списка приоритетов.
 */
export function nextSortConfigs<Field extends string>(
  prev: readonly SortConfig<Field>[],
  field: Field,
): SortConfig<Field>[] {
  const existing = prev.findIndex((config) => config.field === field);
  if (existing === -1) {
    return appendWithinLimit(prev, { field, order: "asc" });
  }

  const next = [...prev];
  if (next[existing].order === "asc") {
    next[existing] = { field, order: "desc" };
  } else {
    next.splice(existing, 1);
  }
  return next;
}

function appendWithinLimit<Field extends string>(
  prev: readonly SortConfig<Field>[],
  config: SortConfig<Field>,
): SortConfig<Field>[] {
  if (prev.length < MAX_SORT_FIELDS) return [...prev, config];
  return [...prev.slice(prev.length - MAX_SORT_FIELDS + 1), config];
}

/** Состояние сортировки колонки для `aria-sort` на `<th>`. */
export function getAriaSort<Field extends string>(
  sorts: readonly SortConfig<Field>[],
  field: Field,
): "none" | "ascending" | "descending" {
  const active = sorts.find((config) => config.field === field);
  if (!active) return "none";
  return active.order === "asc" ? "ascending" : "descending";
}

/** Совпадает ли текущий порядок с сортировкой по умолчанию. */
export function isDefaultSort<Field extends string>(
  current: readonly SortConfig<Field>[],
  defaultSort: readonly SortConfig<Field>[],
): boolean {
  if (current.length !== defaultSort.length) return false;
  return current.every((config, index) => {
    const expected = defaultSort[index];
    return (
      expected !== undefined && config.field === expected.field && config.order === expected.order
    );
  });
}
