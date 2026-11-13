import type { Profile } from "@/types/profile";

// Витрина держит весь каталог в памяти: поиск, фильтры и сортировка — чистые
// функции над уже загруженным списком. Серверный `/catalog?q` не вызывается:
// сеть на линии ненадёжна, а 1000 артикулов фильтруются мгновенно.

export type SortField =
  | "name"
  | "description"
  | "quantity_per_hanger"
  | "length"
  | "notes"
  | "updated_at"
  | "has_photo";

export type SortDirection = "asc" | "desc";

export interface CatalogSort {
  field: SortField;
  direction: SortDirection;
}

export interface CatalogFilters {
  /** Артикул «содержит». */
  name: string;
  /** Наименование «содержит». */
  description: string;
  quantityFrom: number | null;
  quantityTo: number | null;
  /** Конкретные длины; пустой набор — «любая». */
  lengths: Set<number>;
  /** Примечание «содержит». */
  notes: string;
  hasPhoto: boolean;
  /** Календарный день `YYYY-MM-DD`, границы включительно. */
  updatedFrom: string | null;
  updatedTo: string | null;
}

const DEFAULT_SORT: CatalogSort = { field: "name", direction: "asc" };

/** Пустой фильтр: не мутируется, изменения — только копией. */
export const EMPTY_FILTERS: CatalogFilters = {
  name: "",
  description: "",
  quantityFrom: null,
  quantityTo: null,
  lengths: new Set<number>(),
  notes: "",
  hasPhoto: false,
  updatedFrom: null,
  updatedTo: null,
};

/** Порядок столбцов сортировки: меню в тулбаре и чтение `localStorage`. */
export const SORT_FIELDS: readonly SortField[] = [
  "name",
  "description",
  "quantity_per_hanger",
  "length",
  "notes",
  "updated_at",
  "has_photo",
];

/**
 * Нормализация для сравнения «содержит»: убирает пробелы по краям и регистр.
 * Алфавитный порядок кириллицы задаёт не она, а `sortProfiles` через
 * `localeCompare(..., "ru")`.
 */
function normalize(value: string): string {
  return value.trim().toLocaleLowerCase("ru");
}

/** Фото есть, если каталог-источник отдал превью или полное фото. */
function hasPhoto(profile: Profile): boolean {
  return Boolean(profile.photo_thumb || profile.photo_full);
}

function contains(value: string | null, needle: string): boolean {
  if (!needle) return true;
  return value !== null && normalize(value).includes(needle);
}

export function matchesQuery(profile: Profile, query: string): boolean {
  const needle = normalize(query);
  if (!needle) return true;

  return [profile.name, profile.description, profile.notes].some((value) =>
    value === null ? false : normalize(value).includes(needle),
  );
}

/**
 * Граница календарного дня `YYYY-MM-DD`: `endOfDay` — 23:59:59.999, иначе
 * 00:00:00.000. Обе границы включительно, поэтому фильтр не теряет день.
 */
function dayBoundary(value: string, endOfDay: boolean): number | null {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return null;
  return endOfDay
    ? new Date(year, month - 1, day, 23, 59, 59, 999).getTime()
    : new Date(year, month - 1, day, 0, 0, 0, 0).getTime();
}

function matchesUpdated(profile: Profile, filters: CatalogFilters): boolean {
  if (!filters.updatedFrom && !filters.updatedTo) return true;

  const updated = new Date(profile.updated_at).getTime();
  if (Number.isNaN(updated)) return false;

  const from = filters.updatedFrom ? dayBoundary(filters.updatedFrom, false) : null;
  if (from !== null && updated < from) return false;

  const to = filters.updatedTo ? dayBoundary(filters.updatedTo, true) : null;
  if (to !== null && updated > to) return false;

  return true;
}

export function matchesFilters(profile: Profile, filters: CatalogFilters): boolean {
  if (!contains(profile.name, normalize(filters.name))) return false;
  if (!contains(profile.description, normalize(filters.description))) return false;
  if (!contains(profile.notes, normalize(filters.notes))) return false;

  if (filters.quantityFrom !== null || filters.quantityTo !== null) {
    if (profile.quantity_per_hanger === null) return false;
    if (filters.quantityFrom !== null && profile.quantity_per_hanger < filters.quantityFrom) {
      return false;
    }
    if (filters.quantityTo !== null && profile.quantity_per_hanger > filters.quantityTo)
      return false;
  }

  if (filters.lengths.size > 0) {
    if (profile.length === null || !filters.lengths.has(profile.length)) return false;
  }

  if (filters.hasPhoto && !hasPhoto(profile)) return false;

  return matchesUpdated(profile, filters);
}

function sortValue(profile: Profile, field: SortField): string | number | null {
  switch (field) {
    case "name":
      return profile.name;
    case "description":
      return profile.description;
    case "quantity_per_hanger":
      return profile.quantity_per_hanger;
    case "length":
      return profile.length;
    case "notes":
      return profile.notes;
    case "updated_at":
      return new Date(profile.updated_at).getTime();
    case "has_photo":
      return hasPhoto(profile) ? 1 : 0;
  }
}

/**
 * Один столбец за раз. Строки — `localeCompare(..., "ru")`, длина и
 * количество — как числа. `null` всегда в конце: пустое значение не должно
 * всплывать наверх при смене направления.
 */
export function sortProfiles(list: Profile[], sort: CatalogSort): Profile[] {
  return [...list].sort((a, b) => {
    const left = sortValue(a, sort.field);
    const right = sortValue(b, sort.field);

    if (left === null || right === null) {
      if (left === right) return 0;
      return left === null ? 1 : -1;
    }

    const cmp =
      typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right), "ru");

    return sort.direction === "asc" ? cmp : -cmp;
  });
}

/** Уникальные длины по возрастанию — варианты чекбоксов в поповере. */
export function lengthOptions(list: Profile[]): number[] {
  const values = new Set<number>();
  for (const profile of list) {
    if (profile.length !== null) values.add(profile.length);
  }
  return [...values].sort((a, b) => a - b);
}

/** Сколько условий сейчас ограничивает список — для счётчика в тулбаре. */
export function activeFilterCount(filters: CatalogFilters): number {
  let count = 0;
  if (normalize(filters.name)) count += 1;
  if (normalize(filters.description)) count += 1;
  if (filters.quantityFrom !== null || filters.quantityTo !== null) count += 1;
  // Группа длин — одно условие, даже если отмечено несколько значений.
  if (filters.lengths.size > 0) count += 1;
  if (normalize(filters.notes)) count += 1;
  if (filters.hasPhoto) count += 1;
  if (filters.updatedFrom || filters.updatedTo) count += 1;
  return count;
}

function storedRecord(raw: string | null): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return parsed as Record<string, unknown>;
  } catch {
    return {};
  }
}

function storedText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function storedNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function storedDay(value: unknown): string | null {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

/**
 * Старые записи в `localStorage` читаются без новых полей: отсутствующее
 * значение — это «фильтр не задан», а не ошибка.
 */
export function parseStoredFilters(raw: string | null): CatalogFilters {
  const stored = storedRecord(raw);
  const lengths = new Set<number>();

  if (Array.isArray(stored.lengths)) {
    for (const value of stored.lengths) {
      const parsed = storedNumber(value);
      if (parsed !== null) lengths.add(parsed);
    }
  }

  return {
    name: storedText(stored.name),
    description: storedText(stored.description),
    quantityFrom: storedNumber(stored.quantityFrom),
    quantityTo: storedNumber(stored.quantityTo),
    lengths,
    notes: storedText(stored.notes),
    hasPhoto: stored.hasPhoto === true,
    updatedFrom: storedDay(stored.updatedFrom),
    updatedTo: storedDay(stored.updatedTo),
  };
}

export function parseStoredSort(raw: string | null): CatalogSort {
  const stored = storedRecord(raw);
  const field = SORT_FIELDS.find((candidate) => candidate === stored.field);
  const direction =
    stored.direction === "asc" || stored.direction === "desc" ? stored.direction : "asc";

  return { field: field ?? DEFAULT_SORT.field, direction };
}

/** `Set` не переживает `JSON.stringify`, поэтому длины уходят массивом. */
export function serializeFilters(filters: CatalogFilters): string {
  return JSON.stringify({ ...filters, lengths: [...filters.lengths].sort((a, b) => a - b) });
}

export function toggleSort(current: CatalogSort, field: SortField): CatalogSort {
  if (current.field !== field) return { field, direction: "asc" };
  return { field, direction: current.direction === "asc" ? "desc" : "asc" };
}
