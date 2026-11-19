// Синтетическая книга для проверки раскладки дашборда: тысяча строк в форме
// боевой выдачи (`HangerData` с `profiles_info`), собранных из каталога.
// Каждый уникальный профиль и его фото встречаются равномерно, а «выбивающиеся»
// случаи — несколько профилей в подвесе, длинный артикул, обработки, длина в
// разных записях, брак — идут с заданными весами.
//
// В интерфейсе режим не показывается: это инструмент тестов и ручной проверки
// вёрстки (консоль или новый UI-тест), а не витрина для оператора.

import type { ColorSpec } from "@/lib/domain/color";
import type { HangerData, ProfileInfo } from "@/types/dashboard";
import type { Profile } from "@/types/profile";

const NO_VALUE = "—";

/** Обработки так, как их пишет книга: строка → канонический бейдж. */
const PROCESSING: readonly (readonly [string, string])[] = [
  ["окно", "окно"],
  ["гребенка", "греб"],
  ["паз", "паз"],
  ["сверло", "сверло"],
  ["фреза", "фреза"],
];

/** Записи длины из книги: как записано, метры, подпись для бейджа. */
const LENGTHS: readonly (readonly [string, number, string])[] = [
  ["1,8 м", 1.8, "1,8 м"],
  ["1,8 метра", 1.8, "1,8 м"],
  ["(1.8)", 1.8, "1,8 м"],
  ["2,75 м", 2.75, "2,75 м"],
  ["3м", 3, "3 м"],
  ["6,1 метра", 6.1, "6,1 м"],
];

/** Клиенты книги: короткий, средний и длинный — проверяют ширину колонки. */
const CLIENTS = ["РП", "КТМ", "ГорКомплекс", "РП", "—"] as const;

const TYPES = ["Пороги", "Пороги", "Пороги", "Детали", "Клюшки (растрав)"] as const;

function shuffle<T>(items: readonly T[], random: () => number): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    const taken = result[i];
    result[i] = result[j];
    result[j] = taken;
  }
  return result;
}

/** Число профилей в подвесе: один — норма, четыре-пять — редкий тяжёлый случай. */
function profileCountFor(random: () => number): number {
  const roll = random();
  if (roll < 0.04) return 5;
  if (roll < 0.1) return 4;
  if (roll < 0.19) return 3;
  if (roll < 0.4) return 2;
  return 1;
}

/** Как записан один профиль в ячейке книги: артикул + обработка + длина. */
function segmentFor(
  profile: Profile,
  random: () => number,
): { raw: string; processing: string[]; length: (typeof LENGTHS)[number] | null } {
  if (random() < 0.35) {
    const [written, badge] = PROCESSING[Math.floor(random() * PROCESSING.length)];
    return { raw: `${profile.name} ${written}`, processing: [badge], length: null };
  }

  if (random() < 0.55) {
    const length = LENGTHS[Math.floor(random() * LENGTHS.length)];
    return { raw: `${profile.name} ${length[0]}`, processing: [], length };
  }

  return { raw: profile.name, processing: [], length: null };
}

function toInfo(profile: Profile, random: () => number): ProfileInfo {
  const segment = segmentFor(profile, random);
  return {
    name: segment.raw,
    canonical_name: profile.name,
    has_photo: Boolean(profile.photo_thumb),
    photo_thumb: profile.photo_thumb ?? undefined,
    photo_full: profile.photo_full ?? undefined,
    photo_thumb_version: profile.photo_thumb_version,
    photo_full_version: profile.photo_full_version,
    processing: segment.processing,
    length_m: segment.length?.[1] ?? null,
    length_text: segment.length?.[2] ?? null,
  };
}

/**
 * Строки книги: `count` подвесов, уникальные профили раскладываются по кругу —
 * каждый профиль получает одинаковое число строк, а значит и одинаковую долю
 * показов фото. Профили берутся курсором по переставленному каталогу, поэтому
 * в одной строке не повторяются.
 */
export function buildStressRows(
  profiles: readonly Profile[],
  colors: readonly ColorSpec[],
  count = 1000,
  random: () => number = Math.random,
): HangerData[] {
  if (profiles.length === 0) return [];

  const ordered = shuffle(profiles, random);
  const rows: HangerData[] = [];
  let cursor = 0;

  const takeProfile = (): Profile => {
    const profile = ordered[cursor % ordered.length];
    cursor += 1;
    return profile;
  };

  for (let index = 0; index < count; index += 1) {
    const type = TYPES[index % TYPES.length];
    const sticks = type.startsWith("Клюшки");

    // У клюшек профиля нет — как в книге: пустая ячейка и заглушка вместо фото.
    const infos: ProfileInfo[] = sticks
      ? []
      : Array.from({ length: profileCountFor(random) }, () => toInfo(takeProfile(), random));

    const profileText = infos.map((info) => info.name).join(" + ");
    const color = colors[Math.floor(random() * colors.length)]?.name ?? NO_VALUE;
    const hasTime = index % 3 === 0;
    const defect = index % 25 === 5;

    rows.push({
      number: String(index + 1),
      date: "19.11.26",
      time: hasTime
        ? `${String(8 + (index % 10)).padStart(2, "0")}:${String(index % 60).padStart(2, "0")}`
        : "",
      client: CLIENTS[index % CLIENTS.length],
      profile: profileText,
      canonical_name: infos[0]?.canonical_name,
      profiles_info: infos,
      color,
      lamels_qty: sticks || random() < 0.1 ? 0 : 8 + (index % 48),
      kpz_number: index % 11 === 0 ? NO_VALUE : String(160 + (index % 40)),
      material_type: type,
      is_defect: defect,
      // Брак — отдельный флаг книги, а не код подбора: бэкенд шлёт только
      // DELAY и CYCLE_ERROR (`_warning_for`), иначе на экране было бы два «БРАК».
      time_warning: defect ? null : index % 17 === 0 ? "На линии 9.0ч" : null,
      time_warning_code: defect ? null : index % 17 === 0 ? "DELAY" : null,
      entry_date: hasTime ? "19.11.2026" : null,
      entry_time: hasTime ? `11:${String(index % 60).padStart(2, "0")}` : null,
      exit_date: hasTime ? "19.11.2026" : null,
      exit_time: hasTime ? `13:${String(index % 60).padStart(2, "0")}` : null,
    });
  }

  return rows;
}
