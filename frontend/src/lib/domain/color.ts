// Цвет подвеса: имя цвета из книги учёта → код, название, hex и аббревиатура.
// Справочник приходит из API (`useColors`) и передаётся первым аргументом: зашитого
// списка цветов у панели нет. Единственный владелец правила: раньше жило копиями
// в Dashboard и BathForecastTable.

export interface ColorSpec {
  /** Отображаемый код справочника: `C32`, `RG`. У старых операций кода нет. */
  code: string | null;
  /** Каноническое написание: его показываем и по нему узнаём вариант из книги учёта. */
  name: string;
  hex: string;
  /** Короткая подпись из справочника: «сер», «брз»; у цвета веера — его код. */
  abbreviation: string;
}

const UNKNOWN_COLOR_HEX = "#9CA3AF";

/**
 * Ключ названия: регистр, пробелы, дефисы и подчёркивания не различают цвета.
 * `ё` и `е` — одна буква: книга учёта пишет «черный», справочник — «Чёрный».
 */
const CYRILLIC_YO = /\u0451/g;

function normalizeColorName(colorName: string): string {
  return colorName
    .toLowerCase()
    .replace(CYRILLIC_YO, "\u0435")
    .replace(/[\s\-_]/g, "");
}

/**
 * Ключ кода: то же самое плюс кириллическая `С`. В книге учёта код пишут
 * кириллицей (`С32`), канон справочника — латиница (`C32`), это одна буква.
 */
const CYRILLIC_ES = /\u0441/g;

function normalizeColorCode(code: string): string {
  return code
    .toLowerCase()
    .replace(CYRILLIC_ES, "c")
    .replace(/[\s\-_]/g, "");
}

/**
 * Ближайший цвет справочника. Сначала точное совпадение по коду, затем по
 * названию. Затем — только уточнения записанного значения: «серебро матовое»
 * содержит «серебро» и остаётся серебром. Обратного вхождения нет намеренно:
 * иначе «Bronze» (чужое название) подхватил бы «Rose Bronze».
 *
 * Старое название и цвет веера могут совпасть по названию («серебро» и `C0`
 * «Серебро»): запись книги без кода остаётся за старым цветом, иначе строка
 * с «серебро» неожиданно показывала бы `C0`.
 */
function matchColor(colors: readonly ColorSpec[], written: string): ColorSpec | undefined {
  const codeKey = normalizeColorCode(written);
  if (codeKey) {
    const byCode = colors.find((color) => color.code && normalizeColorCode(color.code) === codeKey);
    if (byCode) return byCode;
  }

  const key = normalizeColorName(written);
  if (!key) return undefined;

  let exact: ColorSpec | undefined;
  for (const color of colors) {
    if (normalizeColorName(color.name) !== key) continue;
    if (!exact || (exact.code && !color.code)) exact = color;
  }
  if (exact) return exact;

  let best: ColorSpec | undefined;
  let bestLength = 0;
  for (const color of colors) {
    const name = normalizeColorName(color.name);
    if (!key.includes(name)) continue;
    const better =
      name.length > bestLength || (name.length === bestLength && best?.code && !color.code);
    if (better) {
      best = color;
      bestLength = name.length;
    }
  }
  return best;
}

/**
 * Короткая подпись цвета — из справочника: «сер», «брз», у цвета веера — код.
 * Пустая подпись из API не должна оставлять ячейку без текста: тогда остаются
 * код или первые три буквы названия.
 */
function colorLabel(color: ColorSpec): string {
  return (
    color.abbreviation.trim() ||
    color.code?.trim() ||
    color.name.toLowerCase().trim().slice(0, 4).trimEnd()
  );
}

/** Цвета нет в справочнике: показываем первые четыре символа из книги, как раньше. */
function writtenLabel(written: string): string {
  return written.toLowerCase().trim().slice(0, 4).trimEnd() || "—";
}

/**
 * Название цвета для подсказки. Код `C32` и любое написание названия
 * показываются канонически; уточнение («серебро матовое») остаётся как в книге.
 */
export function colorName(colors: readonly ColorSpec[], written: string): string {
  const color = matchColor(colors, written);
  if (!color) return written.trim();

  if (color.code && normalizeColorCode(color.code) === normalizeColorCode(written))
    return color.name;
  if (normalizeColorName(color.name) === normalizeColorName(written)) return color.name;
  return written.trim();
}

export function colorHex(colors: readonly ColorSpec[], written: string): string {
  return matchColor(colors, written)?.hex ?? UNKNOWN_COLOR_HEX;
}

/** Подпись цвета в тесной ячейке — из справочника; у неизвестного — из книги. */
export function colorAbbreviation(colors: readonly ColorSpec[], written: string): string {
  const color = matchColor(colors, written);
  return color ? colorLabel(color) : writtenLabel(written);
}

/**
 * Код цвета для ячейки дашборда. Если у найденного цвета кода нет, остаётся
 * подпись из справочника — так «серебро» показывает «сер», как раньше.
 */
export function colorCode(colors: readonly ColorSpec[], written: string): string {
  const color = matchColor(colors, written);
  if (!color) return writtenLabel(written);
  return color.code?.trim() || colorLabel(color);
}

/**
 * Подпись для витрины «Все цвета»: код и название вместе (`C31 — Светлая
 * шампань`), чтобы тестовая строка показывала обе части справочника. У старых
 * цветов кода нет — остаётся одно название.
 */
export function colorOptionLabel(color: ColorSpec): string {
  return color.code ? `${color.code} — ${color.name}` : color.name;
}

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace("#", "").trim();
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `rgba(156, 163, 175, ${alpha})`;
  }

  const r = Number.parseInt(normalized.slice(0, 2), 16);
  const g = Number.parseInt(normalized.slice(2, 4), 16);
  const b = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function colorCellStyle(hex: string) {
  return {
    background: `linear-gradient(135deg, ${hexToRgba(hex, 0.6)} 0%, ${hexToRgba(hex, 0.4)} 100%)`,
    boxShadow: `inset 0 0 0 1px ${hexToRgba(hex, 0.52)}`,
  };
}
