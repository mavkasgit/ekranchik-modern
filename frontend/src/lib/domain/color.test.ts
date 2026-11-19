import { describe, expect, it } from "vitest";
import {
  colorAbbreviation,
  colorCode,
  colorHex,
  colorName,
  colorOptionLabel,
  type ColorSpec,
} from "./color";

// Фикстура справочника: старые названия без кода и веер ClassicELOX с кодами,
// как их отдаёт GET /api/colors. Подпись приходит из API: у старых названий
// привычные «сер»/«брз», у цветов веера — код. Порядок — сначала коды, затем названия.
const CATALOG: ColorSpec[] = [
  { code: "C0", name: "Серебро", hex: "#C0C0C0", abbreviation: "C0" },
  { code: "C31", name: "Светлая шампань", hex: "#E8D5A3", abbreviation: "C31" },
  { code: "C32", name: "Тёмная шампань", hex: "#C9A24B", abbreviation: "C32" },
  { code: "C41", name: "Медь", hex: "#B87333", abbreviation: "C41" },
  { code: "C44", name: "Тёмная медь", hex: "#8C4A2F", abbreviation: "C44" },
  { code: "RB", name: "Rose Bronze", hex: "#800020", abbreviation: "RB" },
  { code: "RG", name: "Rose Gold", hex: "#B76E79", abbreviation: "RG" },
  { code: "RST", name: "растрав", hex: "#D3D3D3", abbreviation: "рст" },
  { code: null, name: "серебро", hex: "#C0C0C0", abbreviation: "сер" },
  { code: null, name: "бронза", hex: "#8B5A2B", abbreviation: "брз" },
  { code: null, name: "шампань", hex: "#F7E7CE", abbreviation: "шам" },
  { code: null, name: "черный", hex: "#1C1C1C", abbreviation: "чер" },
];

// В книге учёта код пишут кириллицей, канон справочника — латиница.
const CYRILLIC_C32 = "\u042132";
const CYRILLIC_C41 = "\u042141";

const UNKNOWN_HEX = "#9CA3AF";

describe("colorName", () => {
  it("показывает один канонический пункт для всех написаний цвета из книги учёта", () => {
    for (const written of [
      "Rose Bronze",
      "RoseBronze",
      "rose bronze",
      "ROSE-BRONZE",
      "rose_bronze",
      "  RoseBronze  ",
    ]) {
      expect(colorName(CATALOG, written)).toBe("Rose Bronze");
    }
  });

  it("различает Rose Bronze и Rose Gold", () => {
    expect(colorName(CATALOG, "RoseGold")).toBe("Rose Gold");
    expect(colorName(CATALOG, "Rose Bronze")).not.toBe(colorName(CATALOG, "Rose Gold"));
  });

  it("не выдумывает название для цвета, которого нет в справочнике", () => {
    expect(colorName(CATALOG, "RAL 9016")).toBe("RAL 9016");
    expect(colorName(CATALOG, "  Не указан  ")).toBe("Не указан");
  });

  it("по коду показывает название покрытия — оно же подсказка на дашборде", () => {
    expect(colorName(CATALOG, "C32")).toBe("Тёмная шампань");
    expect(colorName(CATALOG, CYRILLIC_C32)).toBe("Тёмная шампань");
  });

  it("книжное «черный» находит справочное «Чёрный»: ё и е — одна буква", () => {
    const withYo: ColorSpec[] = [
      { code: null, name: "Чёрный", hex: "#1C1C1C", abbreviation: "чер" },
    ];

    expect(colorName(withYo, "черный")).toBe("Чёрный");
    expect(colorHex(withYo, "ЧЁРНЫЙ")).toBe("#1C1C1C");
  });
});

describe("colorHex / colorAbbreviation", () => {
  it("один и тот же цвет с любым написанием даёт один hex и одну аббревиатуру", () => {
    expect(colorHex(CATALOG, "RoseBronze")).toBe(colorHex(CATALOG, "Rose Bronze"));
    expect(colorAbbreviation(CATALOG, "RoseBronze")).toBe("RB");
    expect(colorAbbreviation(CATALOG, "Rose Bronze")).toBe("RB");
  });

  it("подбирает цвет по названию с уточнением («серебро матовое»)", () => {
    expect(colorHex(CATALOG, "серебро матовое")).toBe(colorHex(CATALOG, "серебро"));
  });

  it("не подставляет цвет из чужого названия", () => {
    // «Bronze» — не «Rose Bronze»: на экране не должно появляться то, чего в книге учёта нет.
    expect(colorHex(CATALOG, "Bronze")).not.toBe(colorHex(CATALOG, "Rose Bronze"));
    expect(colorName(CATALOG, "Bronze")).toBe("Bronze");
    expect(colorHex(CATALOG, "Gold")).not.toBe(colorHex(CATALOG, "Rose Gold"));
  });
});

describe("код цвета", () => {
  it("кириллический С32 из книги находит латинский C32 справочника", () => {
    expect(colorCode(CATALOG, CYRILLIC_C32)).toBe("C32");
    expect(colorCode(CATALOG, "C32")).toBe("C32");
    expect(colorHex(CATALOG, CYRILLIC_C32)).toBe(colorHex(CATALOG, "C32"));
  });

  it("находит код без учёта регистра, пробелов, дефисов и подчёркиваний", () => {
    for (const written of ["c32", " C 32 ", "c-32", "c_32"]) {
      expect(colorCode(CATALOG, written)).toBe("C32");
    }
  });

  it("C41 — медь, C44 — тёмная медь, это разные цвета", () => {
    expect(colorCode(CATALOG, CYRILLIC_C41)).toBe("C41");
    expect(colorCode(CATALOG, "C44")).toBe("C44");
    expect(colorName(CATALOG, "C41")).toBe("Медь");
    expect(colorName(CATALOG, "C44")).toBe("Тёмная медь");
    expect(colorHex(CATALOG, "C41")).not.toBe(colorHex(CATALOG, "C44"));
  });

  it("находит локальные коды RG, RB и RST", () => {
    expect(colorCode(CATALOG, "rg")).toBe("RG");
    expect(colorCode(CATALOG, "RB")).toBe("RB");
    expect(colorCode(CATALOG, "RST")).toBe("RST");
  });

  it("шампань остаётся за старым названием, а не за светлой или тёмной", () => {
    expect(colorHex(CATALOG, "шампань")).toBe("#F7E7CE");
    expect(colorName(CATALOG, "шампань")).toBe("шампань");
    // Без кода панель показывает аббревиатуру, как раньше.
    expect(colorCode(CATALOG, "шампань")).toBe("шам");
    expect(colorCode(CATALOG, "Светлая шампань")).toBe("C31");
  });

  it("у цвета без кода показывает старую аббревиатуру, а не выдуманный код", () => {
    expect(colorCode(CATALOG, "серебро")).toBe("сер");
    expect(colorHex(CATALOG, "серебро")).toBe("#C0C0C0");
  });

  it("подпись берёт из справочника: «бронза» — брз, «растрав» — рст", () => {
    expect(colorAbbreviation(CATALOG, "бронза")).toBe("брз");
    expect(colorAbbreviation(CATALOG, "растрав")).toBe("рст");
    expect(colorAbbreviation(CATALOG, "Растрав")).toBe("рст");
    expect(colorCode(CATALOG, "бронза")).toBe("брз");
  });

  it("у цвета веера вместо подписи стоит код", () => {
    expect(colorAbbreviation(CATALOG, "C31")).toBe("C31");
    expect(colorAbbreviation(CATALOG, "Светлая шампань")).toBe("C31");
    expect(colorCode(CATALOG, "C31")).toBe("C31");
  });

  it("если API не прислал подпись, остаются код или первые три буквы названия", () => {
    const sparse: ColorSpec[] = [
      { code: "C77", name: "Новый цвет", hex: "#123456", abbreviation: "" },
      { code: null, name: "патина", hex: "#654321", abbreviation: "" },
    ];

    expect(colorAbbreviation(sparse, "C77")).toBe("C77");
    expect(colorAbbreviation(sparse, "патина")).toBe("пати");
  });

  it("неизвестный цвет остаётся серым и с аббревиатурой из книги", () => {
    expect(colorHex(CATALOG, "RAL 9016")).toBe(UNKNOWN_HEX);
    expect(colorCode(CATALOG, "RAL 9016")).toBe("ral");
  });

  it("пустой справочник (API грузится или упал) не ломает панель", () => {
    const empty: ColorSpec[] = [];
    expect(colorName(empty, "C32")).toBe("C32");
    expect(colorHex(empty, "C32")).toBe(UNKNOWN_HEX);
    expect(colorCode(empty, "C32")).toBe("c32");
  });
});

describe("colorOptionLabel", () => {
  it("в витрине «Все цвета» код и название идут вместе", () => {
    expect(colorOptionLabel(CATALOG[1])).toBe("C31 — Светлая шампань");
    expect(colorOptionLabel(CATALOG[2])).toBe("C32 — Тёмная шампань");
  });

  it("у цвета без кода остаётся одно название", () => {
    expect(colorOptionLabel(CATALOG[8])).toBe("серебро");
    expect(colorOptionLabel(CATALOG[9])).toBe("бронза");
  });

  it("подпись витрины по-прежнему находится справочником: плашка и hex цветные", () => {
    const label = colorOptionLabel(CATALOG[1]);

    expect(colorHex(CATALOG, label)).toBe("#E8D5A3");
  });
});
