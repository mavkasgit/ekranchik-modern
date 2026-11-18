import { describe, expect, it } from "vitest";
import type { ColorSpec } from "./color";
import { buildTestRows } from "./simRows";
import type { Profile } from "@/types/profile";

/** Фикстура справочника: витрина не должна зависеть от длины боевого списка цветов. */
const COLORS: ColorSpec[] = [
  { code: "C31", name: "Светлая шампань", hex: "#E8D5A3", abbreviation: "C31" },
  { code: "C32", name: "Тёмная шампань", hex: "#C9A24B", abbreviation: "C32" },
  { code: "RG", name: "Rose Gold", hex: "#B76E79", abbreviation: "RG" },
  { code: null, name: "серебро", hex: "#C0C0C0", abbreviation: "сер" },
];

function catalogProfile(
  index: number,
  photo: string | null = `images/p${index}-thumb.jpg`,
): Profile {
  return {
    id: index,
    name: `1010${index}`,
    description: null,
    quantity_per_hanger: 12,
    length: 6000,
    notes: null,
    photo_thumb: photo,
    photo_full: photo ? photo.replace("-thumb", "") : null,
    photo_thumb_version: photo ? `v-${index}` : null,
    photo_full_version: photo ? `v-${index}` : null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const CATALOG: Profile[] = Array.from({ length: 12 }, (_, index) => catalogProfile(index));

/** Детерминированный генератор: выбор профилей проверяется, а не отдаётся на волю Math.random. */
function seededRandom(seed: number): () => number {
  let value = seed;
  return () => {
    value = (value * 9301 + 49297) % 233280;
    return value / 233280;
  };
}

describe("buildTestRows", () => {
  it("профиль без фото — обычная строка, а не повод его выкинуть", () => {
    const withGaps = [
      catalogProfile(1),
      catalogProfile(2, null),
      catalogProfile(3, ""),
      catalogProfile(4),
    ];

    const rows = buildTestRows(withGaps, "catalog", COLORS, seededRandom(7));

    expect(rows.map((row) => row.profile).sort()).toEqual(["10101", "10102", "10103", "10104"]);
    const withoutPhoto = rows.find((row) => row.profile === "10102")!;
    expect(withoutPhoto.profile_photo_thumb).toBeUndefined();
  });

  it("в режиме каталога показывает каждый профиль каталога", () => {
    const rows = buildTestRows(CATALOG, "catalog", COLORS, seededRandom(7));

    expect(rows).toHaveLength(CATALOG.length);
    expect(rows.map((row) => row.profile).sort()).toEqual(
      CATALOG.map((profile) => profile.name).sort(),
    );
  });

  it("в режиме симуляции берёт тот же круг, но в случайном порядке", () => {
    const rows = buildTestRows(CATALOG, "sim", COLORS, seededRandom(7));

    expect(rows.map((row) => row.profile).sort()).toEqual(
      CATALOG.map((profile) => profile.name).sort(),
    );
    expect(rows.map((row) => row.profile)).not.toEqual(CATALOG.map((profile) => profile.name));
  });

  it("в режиме цветов даёт ровно одну строку на каждый цвет справочника", () => {
    const rows = buildTestRows(CATALOG, "colors", COLORS, seededRandom(7));

    // Тестовая витрина показывает обе части справочника: `C31 — Светлая
    // шампань`. У старых цветов кода нет — остаётся название.
    expect(rows.map((row) => row.color)).toEqual(
      COLORS.map((color) => (color.code ? `${color.code} — ${color.name}` : color.name)),
    );
    // Число строк задаёт справочник, а не зашитый список фронтенда.
    expect(rows).toHaveLength(COLORS.length);
  });

  it("в режиме цветов профили под цветами разные, а не один на все строки", () => {
    const rows = buildTestRows(CATALOG, "colors", COLORS, seededRandom(7));

    expect(new Set(rows.map((row) => row.profile)).size).toBe(COLORS.length);
  });

  it("время входа на линии настоящее, а номер подвеса проставлен сразу", () => {
    const rows = buildTestRows(CATALOG, "sim", COLORS, seededRandom(7));

    expect(rows.every((row) => /^\d{2}:\d{2}:\d{2}$/.test(row.time))).toBe(true);
    expect(rows.map((row) => row.number)).toEqual(rows.map((_, index) => String(index + 1)));
  });

  it("в режиме цветов строки пронумерованы подряд", () => {
    const rows = buildTestRows(CATALOG, "colors", COLORS, seededRandom(7));

    expect(rows.map((row) => row.number)).toEqual(COLORS.map((_, index) => String(index + 1)));
  });

  it("строка остаётся опознаваемо витринной, а не боевой", () => {
    const rows = buildTestRows(CATALOG, "sim", COLORS, seededRandom(7));

    expect(rows.every((row) => row.client === "Тест Каталога")).toBe(true);
    expect(rows.every((row) => row.material_type === "Тест")).toBe(true);
  });

  it("фото профиля доезжает до строки в обоих размерах", () => {
    const rows = buildTestRows(CATALOG, "sim", COLORS, seededRandom(7));

    expect(rows.every((row) => row.profile_photo_thumb?.includes("-thumb"))).toBe(true);
    expect(
      rows.every((row) => row.profile_photo_full && !row.profile_photo_full.includes("-thumb")),
    ).toBe(true);
  });

  it("в режиме симуляции и каталога цвет каждой строки — из справочника, а не «Не указан»", () => {
    const names = COLORS.map((color) => color.name);

    for (const mode of ["sim", "catalog"] as const) {
      const rows = buildTestRows(CATALOG, mode, COLORS, seededRandom(11));

      expect(rows.every((row) => names.includes(row.color))).toBe(true);
      expect(rows.every((row) => row.color !== "Не указан")).toBe(true);
    }
  });

  it("цвета в симуляции не все одинаковые — витрина крашена по-разному", () => {
    const rows = buildTestRows(CATALOG, "sim", COLORS, seededRandom(11));

    expect(new Set(rows.map((row) => row.color)).size).toBeGreaterThan(1);
  });

  it("пустому каталогу нечего показывать в любом режиме", () => {
    expect(buildTestRows([], "sim", COLORS, seededRandom(7))).toEqual([]);
    expect(buildTestRows([], "colors", COLORS, seededRandom(7))).toEqual([]);
    expect(buildTestRows([], "catalog", COLORS, seededRandom(7))).toEqual([]);
  });

  it("пустой справочник цветов не выдумывает цвета в строках", () => {
    expect(buildTestRows(CATALOG, "colors", [], seededRandom(7))).toEqual([]);
    const rows = buildTestRows(CATALOG, "sim", [], seededRandom(7));
    expect(rows.every((row) => row.color === "—")).toBe(true);
  });
});
