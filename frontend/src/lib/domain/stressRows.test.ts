import { describe, expect, it } from "vitest";
import type { ColorSpec } from "./color";
import { buildStressRows } from "./stressRows";
import type { Profile } from "@/types/profile";

/** Детерминированный генератор: раскладку строк проверяем, а не бросаем кубик. */
function seededRandom(seed: number): () => number {
  let value = seed;
  return () => {
    value = (value * 9301 + 49297) % 233280;
    return value / 233280;
  };
}

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

const COLORS: ColorSpec[] = [
  { code: "C31", name: "Светлая шампань", hex: "#E8D5A3", abbreviation: "C31" },
  { code: null, name: "серебро", hex: "#C0C0C0", abbreviation: "сер" },
];

const CATALOG: Profile[] = Array.from({ length: 40 }, (_, index) => catalogProfile(index));

describe("buildStressRows", () => {
  it("на витрине ровно столько строк, сколько попросили", () => {
    const rows = buildStressRows(CATALOG, COLORS, 1000, seededRandom(7));

    expect(rows).toHaveLength(1000);
    expect(rows[0].number).toBe("1");
    expect(rows[999].number).toBe("1000");
  });

  it("каждый профиль показывается одинаково часто: фото распределены равномерно", () => {
    const rows = buildStressRows(CATALOG, COLORS, 1000, seededRandom(7));

    const shown = new Map<string, number>();
    for (const row of rows) {
      for (const profile of row.profiles_info) {
        expect(profile.photo_thumb).toBeTruthy();
        shown.set(profile.canonical_name!, (shown.get(profile.canonical_name!) ?? 0) + 1);
      }
    }

    const counts = [...shown.values()];
    expect(shown.size).toBe(CATALOG.length);
    expect(Math.max(...counts) - Math.min(...counts)).toBeLessThanOrEqual(1);
  });

  it("клюшки идут без профиля: ячейка пустая, как в книге", () => {
    const rows = buildStressRows(CATALOG, COLORS, 100, seededRandom(7));
    const sticks = rows.filter((row) => row.material_type.startsWith("Клюшки"));

    expect(sticks.length).toBeGreaterThan(0);
    for (const row of sticks) {
      expect(row.profiles_info).toEqual([]);
      expect(row.profile).toBe("");
    }
  });

  it("тяжёлые подвесы встречаются: профилей в строке бывает и пять", () => {
    const rows = buildStressRows(CATALOG, COLORS, 1000, seededRandom(7));
    const counts = rows.map((row) => row.profiles_info.length);

    expect(Math.max(...counts)).toBe(5);
    expect(rows.filter((row) => row.profiles_info.length > 2).length).toBeGreaterThan(100);
  });

  it("профиль в строке записан так, как его пишет книга: имя, обработка, длина", () => {
    const rows = buildStressRows(CATALOG, COLORS, 200, seededRandom(3));
    const withLength = rows.flatMap((row) => row.profiles_info).filter((p) => p.length_text);
    const withProcessing = rows
      .flatMap((row) => row.profiles_info)
      .filter((p) => p.processing.length);

    expect(withLength.length).toBeGreaterThan(0);
    expect(withProcessing.length).toBeGreaterThan(0);
    // Длина приходит отдельным признаком, а не только текстом артикула.
    expect(withLength.every((p) => typeof p.length_m === "number")).toBe(true);
  });

  it("брак не дублируется кодом подбора", () => {
    const rows = buildStressRows(CATALOG, COLORS, 200, seededRandom(7));
    const defects = rows.filter((row) => row.is_defect);

    expect(defects.length).toBeGreaterThan(0);
    expect(defects.every((row) => row.time_warning_code !== "DEFECT")).toBe(true);
  });

  it("без каталога строк нет — витрине нечего показывать", () => {
    expect(buildStressRows([], COLORS, 1000, seededRandom(7))).toEqual([]);
  });
});
