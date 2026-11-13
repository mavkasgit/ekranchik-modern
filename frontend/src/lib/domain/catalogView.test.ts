import { describe, expect, it } from "vitest";
import type { Profile } from "@/types/profile";
import {
  activeFilterCount,
  EMPTY_FILTERS,
  lengthOptions,
  matchesFilters,
  matchesQuery,
  parseStoredFilters,
  parseStoredSort,
  serializeFilters,
  sortProfiles,
  toggleSort,
  type CatalogFilters,
} from "./catalogView";

// Витрина грузит весь список сразу, поэтому поиск, фильтры и сортировка —
// чистая функция над уже загруженным массивом. Здесь единственный источник
// правды для того, что экран показывает оператору.

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

/** Локальная дата в ISO: фильтр «изменён» сравнивает календарные дни. */
function localDay(year: number, month: number, day: number): string {
  return new Date(year, month - 1, day, 12, 0, 0).toISOString();
}

describe("matchesQuery", () => {
  it("находит артикул без учёта регистра, в том числе кириллицу", () => {
    const item = profile({ name: "Крючок-ЮП-3168" });

    expect(matchesQuery(item, "юп-3168")).toBe(true);
    expect(matchesQuery(item, "КРЮЧОК")).toBe(true);
  });

  it("ищет по наименованию и примечанию", () => {
    const item = profile({ description: "Крючок латунный", notes: "Аналог ЮП-3168" });

    expect(matchesQuery(item, "латунный")).toBe(true);
    expect(matchesQuery(item, "аналог")).toBe(true);
  });

  it("не находит то, чего нет ни в одном поле", () => {
    expect(matchesQuery(profile(), "петля")).toBe(false);
  });

  it("пустой запрос и одни пробелы пропускают всё", () => {
    expect(matchesQuery(profile({ name: "", description: null, notes: null }), "")).toBe(true);
    expect(matchesQuery(profile(), "   ")).toBe(true);
  });

  it("null в наименовании и примечании не ломает поиск", () => {
    const item = profile({ description: null, notes: null });

    expect(matchesQuery(item, "арт")).toBe(true);
  });
});

describe("matchesFilters", () => {
  it("пустой фильтр пропускает любой артикул", () => {
    expect(matchesFilters(profile(), EMPTY_FILTERS)).toBe(true);
    expect(matchesFilters(profile({ description: null, notes: null }), EMPTY_FILTERS)).toBe(true);
  });

  it("артикул «содержит», без учёта регистра", () => {
    const filters: CatalogFilters = { ...EMPTY_FILTERS, name: "юп-31" };

    expect(matchesFilters(profile({ name: "Крючок-ЮП-3168" }), filters)).toBe(true);
    expect(matchesFilters(profile({ name: "Крючок-ЮП-2000" }), filters)).toBe(false);
  });

  it("наименование «содержит», null не совпадает", () => {
    const filters: CatalogFilters = { ...EMPTY_FILTERS, description: "латун" };

    expect(matchesFilters(profile({ description: "Крючок латунный" }), filters)).toBe(true);
    expect(matchesFilters(profile({ description: null }), filters)).toBe(false);
  });

  it("количество от/до включительно, null не попадает в диапазон", () => {
    const range: CatalogFilters = { ...EMPTY_FILTERS, quantityFrom: 4, quantityTo: 6 };
    const fromOnly: CatalogFilters = { ...EMPTY_FILTERS, quantityFrom: 6 };
    const toOnly: CatalogFilters = { ...EMPTY_FILTERS, quantityTo: 4 };

    expect(matchesFilters(profile({ quantity_per_hanger: 4 }), range)).toBe(true);
    expect(matchesFilters(profile({ quantity_per_hanger: 6 }), range)).toBe(true);
    expect(matchesFilters(profile({ quantity_per_hanger: 3 }), range)).toBe(false);
    expect(matchesFilters(profile({ quantity_per_hanger: 7 }), range)).toBe(false);
    expect(matchesFilters(profile({ quantity_per_hanger: null }), range)).toBe(false);
    expect(matchesFilters(profile({ quantity_per_hanger: 6 }), fromOnly)).toBe(true);
    expect(matchesFilters(profile({ quantity_per_hanger: 5 }), toOnly)).toBe(false);
  });

  it("длина — набор значений; пустой набор значит «любая»", () => {
    const lengths: CatalogFilters = { ...EMPTY_FILTERS, lengths: new Set([400, 500]) };

    expect(matchesFilters(profile({ length: 400 }), lengths)).toBe(true);
    expect(matchesFilters(profile({ length: 500 }), lengths)).toBe(true);
    expect(matchesFilters(profile({ length: 350 }), lengths)).toBe(false);
    expect(matchesFilters(profile({ length: null }), lengths)).toBe(false);
    expect(matchesFilters(profile({ length: null }), EMPTY_FILTERS)).toBe(true);
  });

  it("примечание «содержит»", () => {
    const filters: CatalogFilters = { ...EMPTY_FILTERS, notes: "аналог" };

    expect(matchesFilters(profile({ notes: "Аналог ЮП-3168" }), filters)).toBe(true);
    expect(matchesFilters(profile({ notes: null }), filters)).toBe(false);
  });

  it("«с фото»: фото есть, если есть превью или полное", () => {
    const filters: CatalogFilters = { ...EMPTY_FILTERS, hasPhoto: true };

    expect(matchesFilters(profile({ photo_thumb: "images/a.jpg" }), filters)).toBe(true);
    expect(matchesFilters(profile({ photo_full: "images/a.jpg" }), filters)).toBe(true);
    expect(matchesFilters(profile({ photo_thumb: null, photo_full: null }), filters)).toBe(false);
  });

  it("«изменён» — диапазон календарных дней, границы включительно", () => {
    const filters: CatalogFilters = {
      ...EMPTY_FILTERS,
      updatedFrom: "2026-11-01",
      updatedTo: "2026-11-05",
    };

    expect(matchesFilters(profile({ updated_at: localDay(2026, 11, 1) }), filters)).toBe(true);
    expect(matchesFilters(profile({ updated_at: localDay(2026, 11, 5) }), filters)).toBe(true);
    expect(matchesFilters(profile({ updated_at: localDay(2026, 10, 31) }), filters)).toBe(false);
    expect(matchesFilters(profile({ updated_at: localDay(2026, 11, 6) }), filters)).toBe(false);
  });

  it("несколько условий складываются через «и»", () => {
    const filters: CatalogFilters = {
      ...EMPTY_FILTERS,
      description: "крючок",
      hasPhoto: true,
      lengths: new Set([400]),
    };

    expect(matchesFilters(profile({ photo_thumb: "images/a.jpg", length: 400 }), filters)).toBe(
      true,
    );
    expect(matchesFilters(profile({ photo_thumb: null, length: 400 }), filters)).toBe(false);
    expect(matchesFilters(profile({ photo_thumb: "images/a.jpg", length: 500 }), filters)).toBe(
      false,
    );
  });
});

describe("parseStoredFilters", () => {
  it("пустое хранилище — пустой фильтр", () => {
    expect(parseStoredFilters(null)).toEqual(EMPTY_FILTERS);
  });

  it("старое значение без новых полей читается, недостающие — по умолчанию", () => {
    expect(parseStoredFilters('{"name":"юп"}')).toEqual({ ...EMPTY_FILTERS, name: "юп" });
  });

  it("битый JSON не роняет экран", () => {
    expect(parseStoredFilters("{не json")).toEqual(EMPTY_FILTERS);
  });

  it("длины сохраняются как числа, мусор отбрасывается", () => {
    expect(parseStoredFilters('{"lengths":[400,"500",null,"x"]}').lengths).toEqual(
      new Set([400, 500]),
    );
  });
});

describe("serializeFilters", () => {
  it("набор длин переживает сохранение и чтение", () => {
    const filters: CatalogFilters = {
      ...EMPTY_FILTERS,
      name: "юп",
      quantityFrom: 4,
      lengths: new Set([500, 350]),
      hasPhoto: true,
      updatedFrom: "2026-11-01",
    };

    expect(parseStoredFilters(serializeFilters(filters))).toEqual(filters);
  });
});

describe("toggleSort", () => {
  it("новый столбец начинает с возрастания", () => {
    expect(toggleSort({ field: "name", direction: "desc" }, "length")).toEqual({
      field: "length",
      direction: "asc",
    });
  });

  it("повторный клик по тому же столбцу меняет направление", () => {
    expect(toggleSort({ field: "name", direction: "asc" }, "name")).toEqual({
      field: "name",
      direction: "desc",
    });
  });
});

describe("sortProfiles", () => {
  const items = [
    profile({ id: 1, name: "Ящик", length: null, quantity_per_hanger: 100 }),
    profile({ id: 2, name: "Абразив", length: 350, quantity_per_hanger: 9 }),
    profile({ id: 3, name: "Болт", length: 500, quantity_per_hanger: null }),
  ];

  it("по артикулу — кириллическая азбука, а не код символов", () => {
    expect(sortProfiles(items, { field: "name", direction: "asc" }).map((p) => p.name)).toEqual([
      "Абразив",
      "Болт",
      "Ящик",
    ]);
    expect(sortProfiles(items, { field: "name", direction: "desc" }).map((p) => p.name)).toEqual([
      "Ящик",
      "Болт",
      "Абразив",
    ]);
  });

  it("по длине — числа, а не строки: 350 < 500", () => {
    expect(sortProfiles(items, { field: "length", direction: "asc" }).map((p) => p.id)).toEqual([
      2, 3, 1,
    ]);
  });

  it("null всегда в конце, независимо от направления", () => {
    expect(sortProfiles(items, { field: "length", direction: "desc" }).map((p) => p.id)).toEqual([
      3, 2, 1,
    ]);
    expect(
      sortProfiles(items, { field: "quantity_per_hanger", direction: "asc" }).map((p) => p.id),
    ).toEqual([2, 1, 3]);
  });

  it("по дате изменения — хронология", () => {
    const dated = [
      profile({ id: 1, updated_at: "2026-11-05T10:00:00.000Z" }),
      profile({ id: 2, updated_at: "2026-10-01T10:00:00.000Z" }),
      profile({ id: 3, updated_at: "2026-12-31T10:00:00.000Z" }),
    ];

    expect(sortProfiles(dated, { field: "updated_at", direction: "asc" }).map((p) => p.id)).toEqual(
      [2, 1, 3],
    );
  });

  it("по наличию фото: полное фото без превью — тоже фото", () => {
    const fullOnly = profile({ id: 1, photo_thumb: null, photo_full: "images/f.jpg" });
    const none = profile({ id: 2, photo_thumb: null, photo_full: null });

    expect(
      sortProfiles([fullOnly, none], { field: "has_photo", direction: "asc" }).map((p) => p.id),
    ).toEqual([2, 1]);
  });

  it("исходный массив не меняется", () => {
    const source = [profile({ id: 1, name: "Ящик" }), profile({ id: 2, name: "Абразив" })];

    sortProfiles(source, { field: "name", direction: "asc" });

    expect(source.map((p) => p.id)).toEqual([1, 2]);
  });
});

describe("lengthOptions", () => {
  it("уникальные длины по возрастанию, null не попадает", () => {
    const list = [
      profile({ length: 500 }),
      profile({ length: null }),
      profile({ length: 350 }),
      profile({ length: 500 }),
    ];

    expect(lengthOptions(list)).toEqual([350, 500]);
  });

  it("пустой список — пустой набор длин", () => {
    expect(lengthOptions([])).toEqual([]);
  });
});

describe("activeFilterCount", () => {
  it("пустой фильтр — ноль", () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
  });

  it("каждое условие считается один раз", () => {
    expect(activeFilterCount({ ...EMPTY_FILTERS, name: "юп" })).toBe(1);
    expect(activeFilterCount({ ...EMPTY_FILTERS, quantityFrom: 1, quantityTo: 6 })).toBe(1);
    expect(
      activeFilterCount({ ...EMPTY_FILTERS, updatedFrom: "2026-11-01", updatedTo: "2026-11-05" }),
    ).toBe(1);
    expect(activeFilterCount({ ...EMPTY_FILTERS, hasPhoto: true })).toBe(1);
  });

  it("каждая выбранная длина — одно условие группы, как и один чип группы", () => {
    expect(activeFilterCount({ ...EMPTY_FILTERS, lengths: new Set([350, 400, 500]) })).toBe(1);
    expect(activeFilterCount({ ...EMPTY_FILTERS, name: "юп", lengths: new Set([350, 400]) })).toBe(
      2,
    );
  });

  it("пробелы в текстовых фильтрах не считаются условием", () => {
    expect(activeFilterCount({ ...EMPTY_FILTERS, name: "  ", notes: " " })).toBe(0);
  });
});

describe("parseStoredSort", () => {
  it("пустое хранилище — артикул по возрастанию", () => {
    expect(parseStoredSort(null)).toEqual({ field: "name", direction: "asc" });
  });

  it("сохранённая сортировка читается", () => {
    expect(parseStoredSort('{"field":"length","direction":"desc"}')).toEqual({
      field: "length",
      direction: "desc",
    });
  });

  it("неизвестное поле и направление — значения по умолчанию", () => {
    expect(parseStoredSort('{"field":"magic","direction":"sideways"}')).toEqual({
      field: "name",
      direction: "asc",
    });
  });

  it("битый JSON не роняет экран", () => {
    expect(parseStoredSort("не json")).toEqual({ field: "name", direction: "asc" });
  });
});
