import { describe, expect, it } from "vitest";
import {
  EMPTY_RANGE,
  columnFilterCount,
  emptyColumnFilterState,
  hasActiveColumnFilters,
  hasActiveRange,
  matchesPartialSearch,
  parseColumnFilterState,
  rankPartialSearchMatch,
  serializeColumnFilterState,
  sortByPartialSearchMatch,
} from "./columnFilters";

type Field = "name" | "length" | "quantity" | "updated_at";

describe("matchesPartialSearch", () => {
  it("ищет без учёта регистра, ё и диакритики", () => {
    expect(matchesPartialSearch("Крючок латунный", "крюч")).toBe(true);
    expect(matchesPartialSearch("Ёлка", "елка")).toBe(true);
    expect(matchesPartialSearch("Café", "cafe")).toBe(true);
    expect(matchesPartialSearch("Крючок", "петля")).toBe(false);
  });

  it("пустой запрос пропускает всё", () => {
    expect(matchesPartialSearch("что угодно", "")).toBe(true);
    expect(matchesPartialSearch("что угодно", "   ")).toBe(true);
  });
});

describe("rankPartialSearchMatch", () => {
  it("начало строки весит меньше вхождения, отсутствие — бесконечность", () => {
    expect(rankPartialSearchMatch("400 мм", "40")).toBe(0);
    expect(rankPartialSearchMatch("1400 мм", "40")).toBe(2);
    expect(rankPartialSearchMatch("400 мм", "юп")).toBe(Number.POSITIVE_INFINITY);
  });
});

describe("sortByPartialSearchMatch", () => {
  it("совпадения из начала списка выше, затем алфавит", () => {
    expect(sortByPartialSearchMatch(["1400", "400", "40", "350"], "40", (value) => value)).toEqual([
      "40",
      "400",
      "1400",
    ]);
  });

  it("пустой запрос сохраняет исходный порядок", () => {
    expect(sortByPartialSearchMatch(["б", "а"], "", (value) => value)).toEqual(["б", "а"]);
  });
});

describe("hasActiveRange", () => {
  it("граница считается заданной, только если она непустая", () => {
    expect(hasActiveRange(EMPTY_RANGE)).toBe(false);
    expect(hasActiveRange(undefined)).toBe(false);
    expect(hasActiveRange({ from: "4", to: "" })).toBe(true);
    expect(hasActiveRange({ from: "", to: "2026-11-05" })).toBe(true);
    expect(hasActiveRange({ from: "  ", to: "  " })).toBe(false);
  });
});

describe("columnFilterCount", () => {
  it("считает колонки, а не значения: несколько длин — одно условие", () => {
    const state = emptyColumnFilterState<Field>();
    state.filters.length = new Set(["350", "400"]);
    state.queries.name = "юп";
    state.ranges.quantity = { from: "4", to: "6" };

    expect(columnFilterCount(state)).toBe(3);
    expect(hasActiveColumnFilters(state)).toBe(true);
  });

  it("текст из пробелов и пустой диапазон не считаются фильтром", () => {
    const state = emptyColumnFilterState<Field>();
    state.queries.name = "   ";
    state.ranges.quantity = { from: "", to: "" };

    expect(columnFilterCount(state)).toBe(0);
    expect(hasActiveColumnFilters(state)).toBe(false);
  });

  it("одна колонка в двух картах считается один раз", () => {
    const state = emptyColumnFilterState<Field>();
    state.queries.length = "40";
    state.filters.length = new Set(["400"]);

    expect(columnFilterCount(state)).toBe(1);
  });
});

describe("хранение состояния фильтров", () => {
  it("наборы значений переживают сохранение и чтение", () => {
    const state = emptyColumnFilterState<Field>();
    state.filters.length = new Set(["400", "500"]);
    state.queries.name = "юп";
    state.ranges.updated_at = { from: "2026-11-01", to: "2026-11-05" };

    expect(
      parseColumnFilterState(serializeColumnFilterState(state), [
        "name",
        "length",
        "quantity",
        "updated_at",
      ]),
    ).toEqual(state);
  });

  it("битый JSON и мусор не роняют экран", () => {
    expect(parseColumnFilterState("{не json", ["name"])).toEqual(emptyColumnFilterState());
    expect(
      parseColumnFilterState(
        JSON.stringify({
          filters: { length: [400, null, "500", { x: 1 }], magic: ["1"] },
          queries: { name: 42, magic: "x" },
          ranges: { updated_at: { from: 2026, to: null }, magic: { from: "1" } },
        }),
        ["name", "length", "quantity", "updated_at"],
      ),
    ).toEqual({
      filters: { length: new Set(["400", "500"]) },
      queries: { name: "42" },
      ranges: { updated_at: { from: "2026", to: "" } },
    });
  });

  it("пустые значения в хранилище не появляются", () => {
    const state = emptyColumnFilterState<Field>();
    state.queries.name = "   ";
    state.filters.length = new Set();

    expect(serializeColumnFilterState(state)).toBe(
      JSON.stringify({ filters: {}, queries: {}, ranges: {} }),
    );
  });
});
