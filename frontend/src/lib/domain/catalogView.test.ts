import { describe, expect, it } from "vitest";
import type { Profile } from "@/types/profile";
import {
  CATALOG_COLUMNS,
  DEFAULT_SORTS,
  catalogFilterValues,
  catalogSearchText,
  filterCatalog,
  parseStoredColumnState,
  parseStoredSorts,
  serializeSorts,
  type CatalogColumnFilterState,
} from "./catalogView";
import { emptyColumnFilterState } from "./columnFilters";
import type { SortConfig } from "./tableQuery";

// Витрина грузит весь список сразу, поэтому поиск, фильтры и сортировка —
// чистые функции над массивом. Здесь проверяется то, что оператор видит в
// таблице: порядок строк, состав списков фильтра и переживание перезагрузки.

function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    id: 1,
    name: "АРТ-001",
    description: "Крючок латунный",
    quantity_per_hanger: 6,
    length: 400,
    notes: null,
    photo_thumb: null,
    photo_full: null,
    photo_thumb_version: null,
    photo_full_version: null,
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-11-01T10:00:00.000Z",
    ...overrides,
  };
}

function state(patch: Partial<CatalogColumnFilterState> = {}): CatalogColumnFilterState {
  return { ...emptyColumnFilterState(), ...patch };
}

function localDay(year: number, month: number, day: number): string {
  return new Date(year, month - 1, day, 12, 0, 0).toISOString();
}

describe("catalogSearchText", () => {
  it("собирает артикул, наименование и примечание", () => {
    const text = catalogSearchText(
      profile({ name: "ЮП-3168", description: "Крючок", notes: "аналог" }),
    );

    expect(text).toBe("ЮП-3168 Крючок аналог");
  });
});

describe("CATALOG_COLUMNS", () => {
  it("каждая колонка объявляет и фильтр, и сортировку", () => {
    for (const column of CATALOG_COLUMNS) {
      expect(column.filterField).toBeDefined();
      expect(column.sortField).toBeDefined();
      expect(column.label).not.toBe("");
    }
  });

  it("фото — готовый домен значений с подписями", () => {
    const photo = CATALOG_COLUMNS.find((column) => column.filterField === "has_photo");

    expect(photo?.filterValues).toEqual(["1", "0"]);
    expect(photo?.valueLabel?.("1")).toBe("С фото");
    expect(photo?.valueLabel?.("0")).toBe("Без фото");
  });
});

describe("catalogFilterValues", () => {
  const list = [
    profile({ id: 1, length: 500, description: null, notes: null }),
    profile({ id: 2, length: null, description: "Крючок", notes: "аналог" }),
    profile({ id: 3, length: 350, description: "Крючок", notes: null }),
    profile({ id: 4, length: 500, description: null, notes: null }),
  ];

  it("длины — уникальные числа по возрастанию, пустые не попадают", () => {
    expect(catalogFilterValues(list).length).toEqual(["350", "500"]);
  });

  it("наименования и примечания — без пустых строк", () => {
    const values = catalogFilterValues(list);

    expect(values.description).toEqual(["Крючок"]);
    expect(values.notes).toEqual(["аналог"]);
  });

  it("диапазонные колонки списка значений не строят", () => {
    const values = catalogFilterValues(list);

    expect(values.quantity).toBeUndefined();
    expect(values.updated_at).toBeUndefined();
  });
});

describe("filterCatalog", () => {
  const list = [
    profile({
      id: 1,
      name: "Ящик",
      description: null,
      notes: null,
      length: null,
      quantity_per_hanger: null,
    }),
    profile({
      id: 2,
      name: "Абразив",
      description: "Крючок латунный",
      length: 350,
      quantity_per_hanger: 9,
      photo_thumb: "images/a.jpg",
    }),
    profile({
      id: 3,
      name: "Болт",
      description: null,
      length: 500,
      quantity_per_hanger: 6,
      notes: "аналог ЮП-3168",
    }),
  ];

  it("пустые фильтры — сортировка по артикулу по возрастанию", () => {
    expect(filterCatalog(list, "", state(), DEFAULT_SORTS).map((item) => item.id)).toEqual([
      2, 3, 1,
    ]);
  });

  it("общий поиск ищет по наименованию и примечанию без учёта регистра", () => {
    expect(filterCatalog(list, "латун", state(), DEFAULT_SORTS).map((item) => item.id)).toEqual([
      2,
    ]);
    expect(filterCatalog(list, "АНАЛОГ", state(), DEFAULT_SORTS).map((item) => item.id)).toEqual([
      3,
    ]);
  });

  it("фильтр длины — точные значения, несколько через «или»", () => {
    const filters = state({ filters: { length: new Set(["350", "500"]) } });

    expect(filterCatalog(list, "", filters, DEFAULT_SORTS).map((item) => item.id)).toEqual([2, 3]);
  });

  it("текст в колонке «Артикул» — «содержит»", () => {
    const filters = state({ queries: { name: "бол" } });

    expect(filterCatalog(list, "", filters, DEFAULT_SORTS).map((item) => item.id)).toEqual([3]);
  });

  it("выбранное значение колонки — точное совпадение", () => {
    const filters = state({ filters: { has_photo: new Set(["1"]) } });

    expect(filterCatalog(list, "", filters, DEFAULT_SORTS).map((item) => item.id)).toEqual([2]);
  });

  it("количество — диапазон включительно, пустое значение не проходит", () => {
    const filters = state({ ranges: { quantity: { from: "6", to: "9" } } });

    expect(filterCatalog(list, "", filters, DEFAULT_SORTS).map((item) => item.id)).toEqual([2, 3]);

    const fromOnly = state({ ranges: { quantity: { from: "7", to: "" } } });
    expect(filterCatalog(list, "", fromOnly, DEFAULT_SORTS).map((item) => item.id)).toEqual([2]);
  });

  it("«изменён» — календарные дни, обе границы включительно", () => {
    const dated = [
      profile({ id: 1, updated_at: localDay(2026, 10, 31) }),
      profile({ id: 2, updated_at: localDay(2026, 11, 1) }),
      profile({ id: 3, updated_at: localDay(2026, 11, 5) }),
      profile({ id: 4, updated_at: localDay(2026, 11, 6) }),
    ];
    const filters = state({ ranges: { updated_at: { from: "2026-11-01", to: "2026-11-05" } } });

    expect(filterCatalog(dated, "", filters, DEFAULT_SORTS).map((item) => item.id)).toEqual([2, 3]);
  });

  it("фильтры разных колонок складываются через «и»", () => {
    const filters = state({
      filters: { length: new Set(["350"]) },
      queries: { description: "крючок" },
    });

    expect(filterCatalog(list, "", filters, DEFAULT_SORTS).map((item) => item.id)).toEqual([2]);
  });

  it("мультисортировка: первый ключ, затем второй", () => {
    const sorts: SortConfig<"length" | "name">[] = [
      { field: "length", order: "asc" },
      { field: "name", order: "desc" },
    ];

    expect(filterCatalog(list, "", state(), sorts).map((item) => item.id)).toEqual([2, 3, 1]);
  });
});

describe("parseStoredSorts", () => {
  it("новый формат — массив ключей с приоритетами", () => {
    const raw = JSON.stringify({
      sorts: [
        { field: "length", order: "asc" },
        { field: "name", order: "desc" },
      ],
    });

    expect(parseStoredSorts(raw, null)).toEqual([
      { field: "length", order: "asc" },
      { field: "name", order: "desc" },
    ]);
  });

  it("старый формат — один ключ, читается как один", () => {
    expect(parseStoredSorts(null, JSON.stringify({ field: "length", direction: "desc" }))).toEqual([
      { field: "length", order: "desc" },
    ]);
  });

  it("незнакомые поля, повторы и лишние ключи отбрасываются", () => {
    const raw = JSON.stringify({
      sorts: [
        { field: "name", order: "asc" },
        { field: "name", order: "desc" },
        { field: "magic", order: "asc" },
        { field: "length", order: "sideways" },
        { field: "notes", order: "desc" },
        { field: "description", order: "asc" },
        { field: "updated_at", order: "desc" },
      ],
    });

    expect(parseStoredSorts(raw, null)).toEqual([
      { field: "name", order: "asc" },
      { field: "notes", order: "desc" },
      { field: "description", order: "asc" },
    ]);
  });

  it("битый JSON и пустое хранилище — сортировка по умолчанию", () => {
    expect(parseStoredSorts("{не json", null)).toEqual(DEFAULT_SORTS);
    expect(parseStoredSorts(null, null)).toEqual(DEFAULT_SORTS);
  });

  it("пустой массив — это «без сортировки», а не отсутствие записи", () => {
    expect(parseStoredSorts(JSON.stringify({ sorts: [] }), null)).toEqual([]);
  });

  it("сохранённое читается тем же парсером", () => {
    const sorts: SortConfig<"name" | "length">[] = [
      { field: "name", order: "asc" },
      { field: "length", order: "desc" },
    ];

    expect(parseStoredSorts(serializeSorts(sorts), null)).toEqual(sorts);
  });
});

describe("parseStoredColumnState", () => {
  it("новый формат — значения, текст и диапазоны", () => {
    const raw = JSON.stringify({
      filters: { length: ["350", "500"], has_photo: ["1"] },
      queries: { name: "юп" },
      ranges: { quantity: { from: "4", to: "6" } },
    });

    expect(parseStoredColumnState(raw)).toEqual({
      filters: { length: new Set(["350", "500"]), has_photo: new Set(["1"]) },
      queries: { name: "юп" },
      ranges: { quantity: { from: "4", to: "6" } },
    });
  });

  it("старый формат каталога переводится в те же карты", () => {
    const raw = JSON.stringify({
      name: "юп",
      description: "крючок",
      notes: "аналог",
      lengths: [400, "500"],
      quantityFrom: 4,
      quantityTo: 6,
      hasPhoto: true,
      updatedFrom: "2026-11-01",
      updatedTo: "2026-11-05",
    });

    expect(parseStoredColumnState(raw)).toEqual({
      filters: { length: new Set(["400", "500"]), has_photo: new Set(["1"]) },
      queries: { name: "юп", description: "крючок", notes: "аналог" },
      ranges: {
        quantity: { from: "4", to: "6" },
        updated_at: { from: "2026-11-01", to: "2026-11-05" },
      },
    });
  });

  it("пустое и битое хранилище — пустое состояние", () => {
    expect(parseStoredColumnState(null)).toEqual(emptyColumnFilterState());
    expect(parseStoredColumnState("не json")).toEqual(emptyColumnFilterState());
  });

  it("незнакомые поля отбрасываются", () => {
    const raw = JSON.stringify({
      filters: { magic: ["1"] },
      queries: { magic: "x" },
      ranges: { magic: { from: "1", to: "2" } },
    });

    expect(parseStoredColumnState(raw)).toEqual(emptyColumnFilterState());
  });
});
