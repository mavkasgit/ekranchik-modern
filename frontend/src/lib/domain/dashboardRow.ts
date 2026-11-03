// Смысл строки дашборда: почему она окрашена, что оператору показать бейджем,
// где живут фото и занимает ли подвес вторую строку. Дашборд только рисует
// готовое описание, поэтому правила строки читаются и проверяются без рендера.

import type { HangerData } from "@/types/dashboard";
import { hangerKey } from "@/lib/domain/hanger";

/** Чем строка отличается от соседей, по убыванию важности. */
type RowTone = "defect" | "sticks" | "delayed" | "plain";

const TONE_CLASSNAMES: Record<RowTone, string> = {
  defect:
    "bg-red-300 hover:bg-red-400 dark:bg-red-900 dark:hover:bg-red-800 text-red-950 dark:text-red-50 font-semibold",
  sticks:
    "bg-sky-300 hover:bg-sky-400 dark:bg-sky-900 dark:hover:bg-sky-800 text-sky-950 dark:text-sky-50 font-semibold",
  delayed: "bg-orange-200 hover:bg-orange-300/80 dark:bg-orange-950/40",
  plain: "",
};

/** Обычные строки чередуют фон, чтобы глаз не терял ряд. */
const ZEBRA_CLASSNAME = "bg-slate-200 dark:bg-slate-800/50";

/** Прочерк книги: значение есть, данных нет. */
const NO_VALUE = "—";

/** Пустой профиль у клюшек читается не прочерком, а именем детали. */
const STICKS_LABEL = "Клюшки";

/**
 * Печать, которую оператор видит бейджем строки. Причина приходит кодом из
 * бэкенда (`app.api.routes.dashboard._warning_for`), текст причины — в тултипе:
 * поэтому в бейдже только метка, а не целая фраза.
 */
type RowBadgeCode = "DELAY" | "CYCLE_ERROR" | "DEFECT";

interface RowBadge {
  code: RowBadgeCode;
  label: string;
  className: string;
}

const BADGES: Record<RowBadgeCode, RowBadge> = {
  DELAY: {
    code: "DELAY",
    label: "⚠ ЗАДЕРЖКА",
    className:
      "text-orange-700 bg-orange-200 dark:text-orange-400 dark:bg-orange-950/60 border-orange-300/50",
  },
  CYCLE_ERROR: {
    code: "CYCLE_ERROR",
    label: "⚠ ОШИБКА",
    className: "text-red-700 bg-red-200 dark:text-red-400 dark:bg-red-950/60 border-red-300/50",
  },
  DEFECT: {
    code: "DEFECT",
    label: "⚠ БРАК",
    className: "text-red-700 bg-red-200 dark:text-red-400 dark:bg-red-950/60 border-red-300/50",
  },
};

export interface RowMeaning {
  tone: RowTone;
  className: string;
  /** Пометки оператору: задержка, ошибка цикла, брак. */
  badges: RowBadge[];
  /** Профиль в ячейке: пустой профиль у клюшек читается словом. */
  profileLabel: string;
  /** Подвес — клюшки: подпись профиля и тон строки строятся по этому флагу. */
  sticks: boolean;
  /** Профилей больше двух — фото не помещаются в первую строку. */
  photosBelow: boolean;
  /** Есть вторая строка: фото на втором ряду или пометка. */
  detailRow: boolean;
  /** Сколько grid-строк занимает подвес. */
  rowSpan: number;
}

/** Клюшки — и по виду материала, и по имени профиля: так их пишет книга. */
function isSticksHanger(hanger: HangerData): boolean {
  return Boolean(
    hanger.material_type?.toLowerCase().includes("клюш") ||
    hanger.profile?.toLowerCase().includes("клюш"),
  );
}

function rowTone(hanger: HangerData): RowTone {
  if (hanger.is_defect) return "defect";
  if (isSticksHanger(hanger)) return "sticks";
  if (hanger.time_warning) return "delayed";
  return "plain";
}

export function rowClassName(hanger: HangerData, index: number): string {
  const tone = rowTone(hanger);
  if (tone === "plain") return index % 2 === 0 ? ZEBRA_CLASSNAME : "";
  return TONE_CLASSNAMES[tone];
}

/** Бейдж по коду бэкенда; неизвестный код на экран не идёт. */
function badgeFor(code: string | null | undefined): RowBadge | null {
  if (!code) return null;
  return Object.values(BADGES).find((badge) => badge.code === code) ?? null;
}

/** Пометки строки в порядке чтения: сначала причина бэкенда, потом брак. */
function rowBadges(hanger: HangerData): RowBadge[] {
  const badges: RowBadge[] = [];
  const badge = badgeFor(hanger.time_warning_code);
  if (badge) badges.push(badge);
  if (hanger.is_defect) badges.push(BADGES.DEFECT);
  return badges;
}

/**
 * Профиль для ячейки. Пустой профиль у клюшек — не пропуск данных, а имя
 * детали: «Клюшки». Плюсы в книге пишут слитно (2020+1010), на экране группы
 * разделяются пробелом.
 */
function profileLabel(hanger: HangerData): string {
  const profile = hanger.profile?.trim();
  const hasProfile = Boolean(profile) && profile !== NO_VALUE;
  if (!hasProfile) return isSticksHanger(hanger) ? STICKS_LABEL : NO_VALUE;
  return profile.replace(/\+/g, "+ ");
}

export function describeHangerRow(hanger: HangerData, index = 0): RowMeaning {
  const badges = rowBadges(hanger);
  const photosBelow = (hanger.profiles_info?.length ?? 0) > 2;
  const detailRow = photosBelow || badges.length > 0;

  return {
    tone: rowTone(hanger),
    className: rowClassName(hanger, index),
    badges,
    profileLabel: profileLabel(hanger),
    sticks: isSticksHanger(hanger),
    photosBelow,
    detailRow,
    rowSpan: detailRow ? 2 : 1,
  };
}

/**
 * Пустая строка книги: ни времени, ни профиля, ни вида материала. Такая строка
 * не несёт подвеса и в боковую очередь не попадает — иначе она вытесняет
 * настоящие строки. Прочерк — тоже «нет значения».
 */
export function isBlankRow(row: Pick<HangerData, "time" | "profile" | "material_type">): boolean {
  const hasValue = (value?: string | null) => {
    const trimmed = value?.trim();
    return Boolean(trimmed) && trimmed !== NO_VALUE;
  };

  return !hasValue(row.time) && !hasValue(row.profile) && !hasValue(row.material_type);
}

export interface HangerMeta {
  profile?: string;
  color?: string;
}

/** Источник сведений о подвесе: строка книги или проход линии. */
export interface HangerMetaRow {
  number?: string | number | null;
  profile?: string | null;
  color?: string | null;
}

export interface HangerMetaEvent {
  hanger?: string | number | null;
  profile?: string | null;
  color?: string | null;
}

/**
 * Сведение Excel и OPC UA по номеру подвеса. Проход линии главнее книги: строка
 * книги — снимок на момент записи, а событие линии говорит, что на подвесе
 * на самом деле. Пустое значение прохода данных книги не стирает.
 */
export function mergeHangerMeta(
  rows: HangerMetaRow[],
  events: HangerMetaEvent[],
): Record<string, HangerMeta> {
  const meta: Record<string, HangerMeta> = {};
  const sources = [
    ...rows.map((row) => ({ key: hangerKey(row.number), ...row })),
    ...events.map((event) => ({ key: hangerKey(event.hanger), ...event })),
  ];

  for (const source of sources) {
    if (!source.key) continue;

    const current = meta[source.key] ?? {};
    const profile = source.profile?.trim();
    const color = source.color?.trim();
    meta[source.key] = {
      profile: profile ? profile : current.profile,
      color: color ? color : current.color,
    };
  }

  return meta;
}
