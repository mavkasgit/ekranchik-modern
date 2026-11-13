import type { Profile } from "@/types/profile";
import { MAX_SORT_FIELDS, type SortConfig, processTableRows } from "./tableQuery";
import {
  type ColumnFilterState,
  emptyColumnFilterState,
  parseColumnFilterState,
} from "./columnFilters";
import {
  type ColumnSpec,
  buildColumnFilterPredicate,
  buildColumnFilterValues,
  buildSortDefs,
} from "./columnSpecs";

// Витрина держит весь каталог в памяти: поиск, фильтры и сортировка — чистые
// функции над уже загруженным списком. Колонки описаны один раз, поэтому
// шапка, поповер фильтра и предикат строк берут одно значение.

const CATALOG_FILTER_FIELDS = [
  "name",
  "description",
  "quantity",
  "length",
  "notes",
  "has_photo",
  "updated_at",
] as const;

export type CatalogFilterField = (typeof CATALOG_FILTER_FIELDS)[number];

export const CATALOG_SORT_FIELDS = [
  "name",
  "description",
  "quantity_per_hanger",
  "length",
  "notes",
  "updated_at",
  "has_photo",
] as const;

export type CatalogSortField = (typeof CATALOG_SORT_FIELDS)[number];

export type CatalogColumn = ColumnSpec<CatalogFilterField, CatalogSortField, Profile>;
export type CatalogColumnFilterState = ColumnFilterState<CatalogFilterField>;

const SORT_FIELD_SET = new Set<string>(CATALOG_SORT_FIELDS);

/** Фото есть, если каталог-источник отдал превью или полное фото. */
function hasPhoto(profile: Profile): boolean {
  return Boolean(profile.photo_thumb || profile.photo_full);
}

function updatedTime(profile: Profile): number | null {
  const time = Date.parse(profile.updated_at);
  return Number.isNaN(time) ? null : time;
}

/**
 * Все колонки таблицы. Фильтр и сортировка объявлены в одном месте:
 * «Кол-во» фильтруется диапазоном по `quantity`, а сортируется по
 * `quantity_per_hanger` — это разные поля, и объявлены они рядом.
 */
export const CATALOG_COLUMNS: readonly CatalogColumn[] = [
  {
    filterField: "has_photo",
    sortField: "has_photo",
    label: "Фото",
    headerClassName: "w-16",
    filterKind: "values",
    filterValues: ["1", "0"],
    valueLabel: (value) => (value === "1" ? "С фото" : "Без фото"),
    cellValue: (profile) => (hasPhoto(profile) ? "1" : "0"),
    getSortValue: (profile) => (hasPhoto(profile) ? 1 : 0),
  },
  {
    filterField: "name",
    sortField: "name",
    label: "Артикул",
    headerClassName: "w-24",
    cellValue: (profile) => profile.name,
    getSortValue: (profile) => profile.name,
  },
  {
    filterField: "description",
    sortField: "description",
    label: "Наименование",
    cellValue: (profile) => profile.description ?? "",
    skipEmptyValues: true,
    getSortValue: (profile) => profile.description,
  },
  {
    filterField: "quantity",
    sortField: "quantity_per_hanger",
    label: "Кол-во",
    filterTitle: "Количество на подвесе",
    headerClassName: "w-24",
    filterKind: "range",
    rangeValue: (profile) => profile.quantity_per_hanger,
    getSortValue: (profile) => profile.quantity_per_hanger,
  },
  {
    filterField: "length",
    sortField: "length",
    label: "Длина",
    filterKind: "values",
    exactMatch: true,
    headerClassName: "w-28",
    cellValue: (profile) => (profile.length === null ? "" : String(profile.length)),
    valueLabel: (value) => `${value} мм`,
    sortValues: (left, right) => Number(left) - Number(right),
    skipEmptyValues: true,
    getSortValue: (profile) => profile.length,
  },
  {
    filterField: "notes",
    sortField: "notes",
    label: "Примечание",
    headerClassName: "w-28",
    cellValue: (profile) => profile.notes ?? "",
    skipEmptyValues: true,
    getSortValue: (profile) => profile.notes,
  },
  {
    filterField: "updated_at",
    sortField: "updated_at",
    label: "Изменён",
    headerClassName: "w-28",
    filterKind: "dateRange",
    rangeKind: "day",
    rangeValue: updatedTime,
    getSortValue: updatedTime,
  },
];

const CATALOG_SORT_DEFS = buildSortDefs(CATALOG_COLUMNS);

export const DEFAULT_SORTS: readonly SortConfig<CatalogSortField>[] = [
  { field: "name", order: "asc" },
];

/** Строка общего поиска: артикул, наименование и примечание. */
export function catalogSearchText(profile: Profile): string {
  return [profile.name, profile.description ?? "", profile.notes ?? ""].join(" ");
}

/** Пересчёт витрины: поиск → фильтры колонок → сортировка. */
export function filterCatalog(
  profiles: readonly Profile[],
  query: string,
  state: CatalogColumnFilterState,
  sorts: readonly SortConfig<CatalogSortField>[],
): Profile[] {
  return processTableRows({
    rows: profiles,
    searchQuery: query,
    searchText: catalogSearchText,
    filterPredicate: buildColumnFilterPredicate(state, CATALOG_COLUMNS),
    sorts,
    sortDefs: CATALOG_SORT_DEFS,
  }).rows;
}

export function catalogFilterValues(
  profiles: readonly Profile[],
): Partial<Record<CatalogFilterField, string[]>> {
  return buildColumnFilterValues(profiles, CATALOG_COLUMNS);
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

function storedNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function storedDay(value: unknown): string | null {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

/**
 * Сортировка из хранилища. Новый формат — массив ключей с приоритетами;
 * старый (один объект `{field, direction}`) читается как один ключ.
 */
export function parseStoredSorts(
  raw: string | null,
  legacyRaw: string | null,
): SortConfig<CatalogSortField>[] {
  const stored = storedRecord(raw);
  const parsed: SortConfig<CatalogSortField>[] = [];
  const seen = new Set<string>();

  // Пустой массив — это выбор оператора «без сортировки», а не отсутствие
  // записи: иначе снятая сортировка возвращалась бы после перезагрузки.
  if (Array.isArray(stored.sorts)) {
    for (const item of stored.sorts) {
      if (!isRecord(item)) continue;
      const field = typeof item.field === "string" ? item.field : null;
      const order = item.order === "asc" || item.order === "desc" ? item.order : null;
      if (!field || !order || !SORT_FIELD_SET.has(field) || seen.has(field)) continue;
      parsed.push({ field: field as CatalogSortField, order });
      seen.add(field);
      if (parsed.length === MAX_SORT_FIELDS) break;
    }
    return parsed;
  }

  const legacy = storedRecord(legacyRaw);
  const field = typeof legacy.field === "string" ? legacy.field : null;
  const direction =
    legacy.direction === "asc" || legacy.direction === "desc"
      ? legacy.direction
      : legacy.order === "asc" || legacy.order === "desc"
        ? legacy.order
        : "asc";
  if (field && SORT_FIELD_SET.has(field)) {
    parsed.push({ field: field as CatalogSortField, order: direction });
  }

  return parsed.length > 0 ? parsed : [...DEFAULT_SORTS];
}

export function serializeSorts(sorts: readonly SortConfig<CatalogSortField>[]): string {
  return JSON.stringify({ sorts });
}

/**
 * Фильтры из хранилища. Новый формат читает общий парсер; старый
 * (`catalog_filters` с полями `name`, `lengths`, `hasPhoto`, …) переводится
 * в те же три карты, чтобы обновление не теряло настройки оператора.
 */
export function parseStoredColumnState(raw: string | null): CatalogColumnFilterState {
  const stored = storedRecord(raw);
  const isNewFormat =
    isRecord(stored.filters) || isRecord(stored.queries) || isRecord(stored.ranges);
  if (isNewFormat) {
    return parseColumnFilterState(raw, CATALOG_FILTER_FIELDS);
  }

  const state = emptyColumnFilterState<CatalogFilterField>();

  const name = storedText(stored.name);
  if (name && name.trim() !== "") state.queries.name = name;

  const description = storedText(stored.description);
  if (description && description.trim() !== "") state.queries.description = description;

  const notes = storedText(stored.notes);
  if (notes && notes.trim() !== "") state.queries.notes = notes;

  if (Array.isArray(stored.lengths)) {
    const lengths = new Set<string>();
    for (const value of stored.lengths) {
      const parsed = storedNumber(value);
      if (parsed !== null) lengths.add(String(parsed));
    }
    if (lengths.size > 0) state.filters.length = lengths;
  }

  if (stored.hasPhoto === true) {
    state.filters.has_photo = new Set(["1"]);
  }

  const quantityFrom = storedNumber(stored.quantityFrom);
  const quantityTo = storedNumber(stored.quantityTo);
  if (quantityFrom !== null || quantityTo !== null) {
    state.ranges.quantity = {
      from: quantityFrom === null ? "" : String(quantityFrom),
      to: quantityTo === null ? "" : String(quantityTo),
    };
  }

  const updatedFrom = storedDay(stored.updatedFrom);
  const updatedTo = storedDay(stored.updatedTo);
  if (updatedFrom || updatedTo) {
    state.ranges.updated_at = { from: updatedFrom ?? "", to: updatedTo ?? "" };
  }

  return state;
}
