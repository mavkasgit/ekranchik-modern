import { describe, expect, it } from "vitest";
import {
  MAX_SORT_FIELDS,
  compareSortValues,
  getAriaSort,
  isDefaultSort,
  nextSortConfigs,
  processTableRows,
  sortRows,
  type SortConfig,
} from "./tableQuery";
import { normalizeText } from "./textNormalize";

// Движок таблицы: поиск → фильтр → мультисортировка. Здесь проверяется то,
// что экран не может проверить глазами: порядок пустых, приоритеты ключей и
// цикл клика по заголовку.

interface Row {
  id: number;
  name: string;
  length: number | null;
  note: string | null;
}

const ROWS: Row[] = [
  { id: 1, name: "Ящик", length: null, note: "нет" },
  { id: 2, name: "Абразив", length: 350, note: null },
  { id: 3, name: "Болт", length: 500, note: "аналог" },
  { id: 4, name: "Арка", length: 350, note: "срочно" },
];

const DEFS = new Map<string, (row: Row) => string | number | null>([
  ["name", (row) => row.name],
  ["length", (row) => row.length],
  ["note", (row) => row.note],
]);

describe("normalizeText", () => {
  it("приводит регистр, ё и диакритику", () => {
    expect(normalizeText("Ёлка")).toBe("елка");
    expect(normalizeText("Café")).toBe("cafe");
    expect(normalizeText("  ЮП-3168  ")).toBe("  юп-3168  ");
  });
});

describe("compareSortValues", () => {
  it("числа сравниваются как числа", () => {
    expect(compareSortValues(2, 10, "asc")).toBeLessThan(0);
    expect(compareSortValues(2, 10, "desc")).toBeGreaterThan(0);
  });

  it("строки — по кириллическому алфавиту и с числами", () => {
    expect(compareSortValues("Абразив", "Болт", "asc")).toBeLessThan(0);
    expect(compareSortValues("ЮП-2", "ЮП-10", "asc")).toBeLessThan(0);
  });

  it("null и пустая строка всегда в конце, независимо от направления", () => {
    expect(compareSortValues(null, "Абразив", "asc")).toBeGreaterThan(0);
    expect(compareSortValues(null, "Абразив", "desc")).toBeGreaterThan(0);
    expect(compareSortValues("", "Абразив", "asc")).toBeGreaterThan(0);
    expect(compareSortValues(null, null, "desc")).toBe(0);
  });
});

describe("sortRows", () => {
  it("сортирует копию и не меняет исходный список", () => {
    const source = [...ROWS];

    const sorted = sortRows(source, [{ field: "name", order: "asc" }], DEFS);

    expect(sorted.map((row) => row.name)).toEqual(["Абразив", "Арка", "Болт", "Ящик"]);
    expect(source.map((row) => row.id)).toEqual([1, 2, 3, 4]);
  });

  it("второй ключ решает ничьи, пустые уезжают в конец", () => {
    const sorted = sortRows(
      ROWS,
      [
        { field: "length", order: "asc" },
        { field: "name", order: "desc" },
      ],
      DEFS,
    );

    expect(sorted.map((row) => row.id)).toEqual([4, 2, 3, 1]);
  });

  it("неизвестное поле пропускается, а не роняет сортировку", () => {
    const sorted = sortRows(ROWS, [{ field: "magic", order: "asc" }], DEFS);

    expect(sorted.map((row) => row.id)).toEqual([1, 2, 3, 4]);
  });

  it("пустой набор ключей возвращает исходный порядок", () => {
    expect(sortRows(ROWS, [], DEFS).map((row) => row.id)).toEqual([1, 2, 3, 4]);
  });
});

describe("processTableRows", () => {
  it("поиск идёт по нормализованной строке и считает total/filtered", () => {
    const result = processTableRows({
      rows: ROWS,
      searchQuery: "АНАЛОГ",
      searchText: (row) => `${row.name} ${row.note ?? ""}`,
      filterPredicate: null,
      sorts: [{ field: "name", order: "asc" }],
      sortDefs: DEFS,
    });

    expect(result.totalCount).toBe(4);
    expect(result.filteredCount).toBe(1);
    expect(result.rows.map((row) => row.id)).toEqual([3]);
  });

  it("фильтр применяется после поиска, сортировка — после фильтра", () => {
    const result = processTableRows({
      rows: ROWS,
      searchQuery: "",
      searchText: (row) => row.name,
      filterPredicate: (row) => row.length !== null,
      sorts: [{ field: "length", order: "desc" }],
      sortDefs: DEFS,
    });

    expect(result.filteredCount).toBe(4);
    expect(result.rows.map((row) => row.id)).toEqual([3, 2, 4]);
  });
});

describe("nextSortConfigs", () => {
  it("цикл: нет → возрастание → убывание → снята", () => {
    const first = nextSortConfigs<"name" | "length">([], "name");
    expect(first).toEqual([{ field: "name", order: "asc" }]);

    const second = nextSortConfigs(first, "name");
    expect(second).toEqual([{ field: "name", order: "desc" }]);

    const third = nextSortConfigs(second, "name");
    expect(third).toEqual([]);
  });

  it("новый ключ добавляется в конец приоритетов", () => {
    const sorts: SortConfig<"name" | "length">[] = [{ field: "name", order: "asc" }];

    expect(nextSortConfigs(sorts, "length")).toEqual([
      { field: "name", order: "asc" },
      { field: "length", order: "asc" },
    ]);
  });

  it("четвёртый ключ вытесняет самый старый", () => {
    let sorts: SortConfig<"a" | "b" | "c" | "d">[] = [];
    for (const field of ["a", "b", "c", "d"] as const) {
      sorts = nextSortConfigs(sorts, field);
    }

    expect(sorts).toHaveLength(MAX_SORT_FIELDS);
    expect(sorts.map((config) => config.field)).toEqual(["b", "c", "d"]);
  });
});

describe("getAriaSort", () => {
  it("объявляет направление активной колонки", () => {
    const sorts: SortConfig<"name" | "length">[] = [
      { field: "name", order: "asc" },
      { field: "length", order: "desc" },
    ];

    expect(getAriaSort(sorts, "name")).toBe("ascending");
    expect(getAriaSort(sorts, "length")).toBe("descending");
    expect(getAriaSort(sorts, "magic" as "name")).toBe("none");
  });
});

describe("isDefaultSort", () => {
  const fallback: SortConfig<"name">[] = [{ field: "name", order: "asc" }];

  it("совпадает только полный порядок ключей", () => {
    expect(isDefaultSort(fallback, fallback)).toBe(true);
    expect(isDefaultSort([], fallback)).toBe(false);
    expect(isDefaultSort([{ field: "name", order: "desc" }], fallback)).toBe(false);
  });
});
