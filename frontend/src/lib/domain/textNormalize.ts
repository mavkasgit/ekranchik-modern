const DIACRITICS_REGEX = /\p{Diacritic}/gu;

/**
 * Нормализация текста для поиска и списков фильтра: нижний регистр, без
 * диакритики, `ё` → `е`. Один нормализатор на все сравнения — иначе поиск
 * «ёлка» находил бы «елку» в одной колонке и не находил в другой.
 */
export function normalizeText(value: string): string {
  return value.toLowerCase().normalize("NFKD").replace(DIACRITICS_REGEX, "").replace(/ё/g, "е");
}
