import { normalizeText } from "./textNormalize";

// Состояние фильтров колонок и его сохранение. Поля здесь — только примитивы:
// описание колонки (что читать и как подписывать) живёт в `columnSpecs`.
//
// Три вида состояния, потому что колонки фильтруются по-разному:
// - `filters` — выбранные значения из списка (длина, «с фото»);
// - `queries` — текст «содержит» (артикул, наименование, примечание);
// - `ranges` — границы «от/до» (количество, дата изменения).

export interface RangeFilter {
  /** Пустая строка — граница не задана. */
  from: string;
  to: string;
}

export const EMPTY_RANGE: RangeFilter = { from: "", to: "" };

type ColumnFilters<Field extends string> = Partial<Record<Field, Set<string>>>;
type ColumnSearchQueries<Field extends string> = Partial<Record<Field, string>>;
type ColumnRanges<Field extends string> = Partial<Record<Field, RangeFilter>>;

export interface ColumnFilterState<Field extends string> {
  filters: ColumnFilters<Field>;
  queries: ColumnSearchQueries<Field>;
  ranges: ColumnRanges<Field>;
}

export function emptyColumnFilterState<Field extends string>(): ColumnFilterState<Field> {
  return { filters: {}, queries: {}, ranges: {} };
}

/** Частичное совпадение без учёта регистра, диакритики и `ё`. */
export function matchesPartialSearch(haystack: string, query: string): boolean {
  const needle = normalizeText(query.trim());
  if (!needle) return true;
  return normalizeText(haystack).includes(needle);
}

/** Меньше — лучше: 0 для начала строки, дальше позиция вхождения. */
export function rankPartialSearchMatch(label: string, query: string): number {
  const needle = normalizeText(query.trim());
  if (!needle) return 0;
  const normalized = normalizeText(label);
  if (normalized.startsWith(needle)) return 0;
  const index = normalized.indexOf(needle);
  if (index === -1) return Number.POSITIVE_INFINITY;
  return 1 + index;
}

/**
 * Фильтрует и сортирует список значений поповера: совпадение в начале —
 * выше, затем вхождение, затем алфавит. Так ввод «40» в «Длина» поднимает
 * 400 мм над 1400 мм.
 */
export function sortByPartialSearchMatch<T>(
  values: readonly T[],
  query: string,
  getLabel: (value: T) => string,
): T[] {
  if (!query.trim()) return [...values];
  return values
    .filter((value) => matchesPartialSearch(getLabel(value), query))
    .sort((left, right) => {
      const rankDiff =
        rankPartialSearchMatch(getLabel(left), query) -
        rankPartialSearchMatch(getLabel(right), query);
      if (rankDiff !== 0) return rankDiff;
      return getLabel(left).localeCompare(getLabel(right), "ru");
    });
}

export function hasActiveRange(range: RangeFilter | undefined): boolean {
  return range !== undefined && (range.from.trim() !== "" || range.to.trim() !== "");
}

/** Есть ли хоть одно ограничение — для кнопки сброса и бейджа. */
export function hasActiveColumnFilters<Field extends string>(
  state: ColumnFilterState<Field>,
): boolean {
  return columnFilterCount(state) > 0;
}

/** Сколько колонок ограничено; несколько значений одной колонки — одно условие. */
export function columnFilterCount<Field extends string>(state: ColumnFilterState<Field>): number {
  const fields = new Set<string>();

  for (const [field, selected] of Object.entries(state.filters) as Array<
    [string, Set<string> | undefined]
  >) {
    if (selected && selected.size > 0) fields.add(field);
  }
  for (const [field, query] of Object.entries(state.queries) as Array<
    [string, string | undefined]
  >) {
    if (typeof query === "string" && query.trim() !== "") fields.add(field);
  }
  for (const [field, range] of Object.entries(state.ranges) as Array<
    [string, RangeFilter | undefined]
  >) {
    if (range && hasActiveRange(range)) fields.add(field);
  }

  return fields.size;
}

/** `Set` не переживает JSON — в хранилище уходит массивом. */
export function serializeColumnFilterState<Field extends string>(
  state: ColumnFilterState<Field>,
): string {
  const filters: Record<string, string[]> = {};
  for (const [field, selected] of Object.entries(state.filters) as Array<
    [string, Set<string> | undefined]
  >) {
    if (selected && selected.size > 0) filters[field] = [...selected];
  }

  const queries: Record<string, string> = {};
  for (const [field, query] of Object.entries(state.queries) as Array<
    [string, string | undefined]
  >) {
    if (typeof query === "string" && query.trim() !== "") queries[field] = query;
  }

  const ranges: Record<string, RangeFilter> = {};
  for (const [field, range] of Object.entries(state.ranges) as Array<
    [string, RangeFilter | undefined]
  >) {
    if (range && hasActiveRange(range)) ranges[field] = { from: range.from, to: range.to };
  }

  return JSON.stringify({ filters, queries, ranges });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function storedRecord(raw: string | null): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    return isRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function storedText(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

/**
 * Читает состояние фильтров из `localStorage`. Незнакомые поля и мусор
 * отбрасываются: старые записи без новых полей должны открываться, а не
 * ронять экран.
 */
export function parseColumnFilterState<Field extends string>(
  raw: string | null,
  fields: readonly Field[],
): ColumnFilterState<Field> {
  const stored = storedRecord(raw);
  const allowed = new Set<string>(fields);
  const state = emptyColumnFilterState<Field>();

  const rawFilters = stored.filters;
  if (isRecord(rawFilters)) {
    for (const [field, values] of Object.entries(rawFilters)) {
      if (!allowed.has(field) || !Array.isArray(values)) continue;
      const selected = new Set<string>();
      for (const value of values) {
        const text = storedText(value);
        if (text !== null) selected.add(text);
      }
      if (selected.size > 0) state.filters[field as Field] = selected;
    }
  }

  const rawQueries = stored.queries;
  if (isRecord(rawQueries)) {
    for (const [field, value] of Object.entries(rawQueries)) {
      if (!allowed.has(field)) continue;
      const text = storedText(value);
      if (text !== null && text.trim() !== "") state.queries[field as Field] = text;
    }
  }

  const rawRanges = stored.ranges;
  if (isRecord(rawRanges)) {
    for (const [field, value] of Object.entries(rawRanges)) {
      if (!allowed.has(field) || !isRecord(value)) continue;
      const from = storedText(value.from) ?? "";
      const to = storedText(value.to) ?? "";
      if (from.trim() !== "" || to.trim() !== "") {
        state.ranges[field as Field] = { from, to };
      }
    }
  }

  return state;
}
