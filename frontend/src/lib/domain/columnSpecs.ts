import {
  type ColumnFilterState,
  type RangeFilter,
  hasActiveColumnFilters,
  hasActiveRange,
  matchesPartialSearch,
} from "./columnFilters";
import type { SortValue } from "./tableQuery";

// Описание колонки — единственное место, где объявлено, как она фильтруется,
// сортируется и что читает из строки. Шапка, поповер значений и предикат
// берут одно и то же объявление, поэтому «показываю одно, фильтрую другое»
// перестаёт быть возможным.

export type ColumnFilterKind = "values" | "range" | "dateRange";
type RangeKind = "number" | "day";

export interface ColumnSpec<Field extends string, SortField extends string = Field, Row = unknown> {
  /** Поле фильтра. Нет — колонка не фильтруется. */
  filterField?: Field;
  /** Поле сортировки. Нет — колонка не сортируется. */
  sortField?: SortField;
  label: string;
  /** Подпись в поповере, если она длиннее заголовка («Кол-во» → «Количество»). */
  filterTitle?: string;
  /** Значения из списка (по умолчанию), диапазон чисел или дат. */
  filterKind?: ColumnFilterKind;
  /** Подпись значения в списке: `400` → `400 мм`. */
  valueLabel?: (value: string) => string;
  /** Колонка выбирает точное значение, а поиск сужает только список. */
  exactMatch?: boolean;
  /** Можно ли выбрать несколько значений (все колонки витрины — да). */
  multiSelect?: boolean;
  /** Готовый домен значений, не зависящий от строк («С фото»/«Без фото»). */
  filterValues?: readonly string[];
  /** Значение колонки в строке. */
  cellValue?: (row: Row) => string;
  /** Несколько значений в строке: строка проходит, если совпало любое. */
  filterValuesFrom?: (row: Row) => readonly string[];
  sortValues?: (left: string, right: string) => number;
  /** Пустое значение в список не попадает: пустая кнопка неотличима от «снято». */
  skipEmptyValues?: boolean;
  /** Числовое значение для фильтра «от/до». */
  rangeValue?: (row: Row) => number | null;
  rangeKind?: RangeKind;
  /** Значение для сортировки. `null` — пусто (уезжает в конец). */
  getSortValue?: (row: Row) => SortValue;
  /** Ширина колонки в таблице. */
  headerClassName?: string;
}

/** Список значений для поповера — из описания, а не из карты на экране. */
export function buildColumnFilterValues<T, Field extends string, SortField extends string>(
  rows: readonly T[],
  columns: ReadonlyArray<ColumnSpec<Field, SortField, T>>,
): Partial<Record<Field, string[]>> {
  const values: Partial<Record<Field, string[]>> = {};

  for (const column of columns) {
    if (!column.filterField) continue;
    if ((column.filterKind ?? "values") !== "values") continue;

    const read = column.filterValuesFrom ?? column.cellValue;
    if (!column.filterValues && !read) continue;

    const unique = new Set<string>();
    const add = (value: string) => {
      if (column.skipEmptyValues && value === "") return;
      unique.add(value);
    };

    if (column.filterValues) {
      for (const value of column.filterValues) add(value);
    } else if (read) {
      for (const row of rows) {
        const value = read(row);
        if (typeof value === "string") {
          add(value);
          continue;
        }
        for (const candidate of value) add(candidate);
      }
    }

    const list = [...unique];
    values[column.filterField] = column.sortValues ? list.sort(column.sortValues) : list;
  }

  return values;
}

function dayBoundary(value: string, endOfDay: boolean): number | null {
  if (value.trim() === "") return null;
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return null;
  return endOfDay
    ? new Date(year, month - 1, day, 23, 59, 59, 999).getTime()
    : new Date(year, month - 1, day, 0, 0, 0, 0).getTime();
}

function rangeBounds(
  range: RangeFilter,
  kind: RangeKind,
): { from: number | null; to: number | null } {
  if (kind === "day") {
    return { from: dayBoundary(range.from, false), to: dayBoundary(range.to, true) };
  }

  const parse = (value: string): number | null => {
    if (value.trim() === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  return { from: parse(range.from), to: parse(range.to) };
}

/**
 * Клиентский предикат всех фильтров колонок: выбранные значения, текст
 * «содержит» и диапазоны. Возвращает `null`, когда ограничений нет, — тогда
 * конвейер не фильтрует строки вовсе.
 */
export function buildColumnFilterPredicate<T, Field extends string, SortField extends string>(
  state: ColumnFilterState<Field>,
  columns: ReadonlyArray<ColumnSpec<Field, SortField, T>>,
): ((row: T) => boolean) | null {
  if (!hasActiveColumnFilters(state)) return null;

  const byField = new Map<Field, ColumnSpec<Field, SortField, T>>();
  for (const column of columns) {
    if (column.filterField) byField.set(column.filterField, column);
  }

  return (row: T) => {
    for (const [field, column] of byField) {
      const kind = column.filterKind ?? "values";
      const query = state.queries[field]?.trim();
      const selected = state.filters[field];
      const range = state.ranges[field];

      if (kind === "values") {
        const read = column.filterValuesFrom ?? column.cellValue;
        if (!read) continue;
        const value = read(row);

        if (query) {
          const matches =
            typeof value === "string"
              ? matchesPartialSearch(value, query)
              : value.some((candidate) => matchesPartialSearch(candidate, query));
          if (!matches) return false;
          continue;
        }

        if (selected && selected.size > 0) {
          const matches =
            typeof value === "string"
              ? selected.has(value)
              : value.some((candidate) => selected.has(candidate));
          if (!matches) return false;
        }
        continue;
      }

      if (!column.rangeValue || !hasActiveRange(range)) continue;

      const target = column.rangeValue(row);
      if (target === null || Number.isNaN(target)) return false;

      const bounds = rangeBounds(range ?? { from: "", to: "" }, column.rangeKind ?? "number");
      if (bounds.from !== null && target < bounds.from) return false;
      if (bounds.to !== null && target > bounds.to) return false;
    }

    return true;
  };
}

/** Читатели значений для сортировки: колонка объявляет и поле, и значение. */
export function buildSortDefs<T, Field extends string, SortField extends string>(
  columns: ReadonlyArray<ColumnSpec<Field, SortField, T>>,
): Map<SortField, (row: T) => SortValue> {
  const defs = new Map<SortField, (row: T) => SortValue>();
  for (const column of columns) {
    if (column.sortField && column.getSortValue) {
      defs.set(column.sortField, column.getSortValue);
    }
  }
  return defs;
}
