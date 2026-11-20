import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { photoUrl } from "@/lib/domain/photo";
import { PHOTO_HEIGHT, photoHeightAtBand } from "@/lib/domain/photoSlot";
import type { ProfileInfo } from "@/types/dashboard";

/**
 * Потолки снимка по ширине, px.
 *
 * Горизонталь ограничивает только слот, а не фиксированный размер снимка: в
 * колонку «Фото» (150 px) пара должна влезать целиком (70 + 8 + 70 = 148),
 * а одиночный снимок может занять всю колонку (148 px). Это важно для широких
 * превью каталога: их аспект доходит до 8,7:1, и при потолке 70 px такой снимок
 * сжимался до 70×8 — деталь по нему не разглядеть. Высота держится 40 px, а
 * ширина берётся из аспекта, пока влезает в слот.
 */
export const PHOTO_SOLO_MAX_WIDTH = 148;
export const PHOTO_PAIR_MAX_WIDTH = 70;

/**
 * Снимок профиля: потолок по высоте и обводка «сжат по ширине» в ?stress.
 *
 * `markShort` — инструмент проверки раскладки, а не операторский вид: обводит
 * те снимки, у которых ширина слота отняла высоту, чтобы их было видно в сотне
 * строк. В бою флаг не включается.
 */
export function PhotoImage({
  src,
  alt,
  onClick,
  solo = false,
  markShort = false,
  photoMax,
  onSized,
}: {
  src: string;
  alt: string;
  onClick?: () => void;
  /** Снимок один в ячейке: ему доступна вся ширина колонки. */
  solo?: boolean;
  /** Обвести снимки, потерявшие высоту из-за потолка ширины (?stress). */
  markShort?: boolean;
  /** Потолок ширины, px: ячейка поджимает кадр, чтобы подпись влезла сбоку. */
  photoMax?: number;
  /** Снимок получил размеры: по ним ячейка решает, влезает ли подпись сбоку. */
  onSized?: () => void;
}) {
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const maxWidth = solo ? PHOTO_SOLO_MAX_WIDTH : PHOTO_PAIR_MAX_WIDTH;
  // Поджатый кадр тоже считается: он теряет высоту вместе с шириной, и в
  // ?stress его надо обвести, иначе «сжат по ширине» врёт.
  const cap = photoMax ? Math.min(maxWidth, photoMax) : maxWidth;
  const short =
    markShort && natural
      ? photoHeightAtBand(natural.width, natural.height, cap) < PHOTO_HEIGHT - 4
      : false;

  return (
    <img
      src={src}
      alt={alt}
      data-short-photo={short ? "1" : undefined}
      title={short ? "Снимок сжат по ширине: высота меньше 40 px" : undefined}
      style={{ maxHeight: PHOTO_HEIGHT, ...(photoMax ? { maxWidth: photoMax } : null) }}
      className={`w-auto h-auto ${solo ? "max-w-[148px]" : "max-w-[70px]"} object-contain rounded cursor-pointer ${
        // Одиночный снимок занимает почти всю колонку: scale раздул бы его до
        // ~155 px и накрыл соседние ячейки, поэтому отклик — яркостью. Паре
        // хватает запаса в 8 px между снимками, там scale остаётся.
        solo ? "hover:brightness-110" : "hover:scale-105"
      } transition-transform border border-border hover:border-primary flex-shrink-0 ${
        short ? "ring-2 ring-rose-500 ring-offset-1" : ""
      }`}
      onLoad={(event) => {
        // Обводим только заметно сжатые (ниже 36 из 40 px): 38 px на глаз не
        // отличить от 40, и такие снимки только шумели бы в сотне строк.
        const image = event.currentTarget;
        setNatural({ width: image.naturalWidth, height: image.naturalHeight });
        onSized?.();
      }}
      onClick={onClick}
    />
  );
}

/** Есть ли у профиля что показать бейджем: обработки или длина из книги. */
export function hasProfileBadges(profile: ProfileInfo): boolean {
  return profile.processing.length > 0 || Boolean(profile.length_text);
}

/**
 * Бейджи обработок и длины. Принадлежат профилю, а не строке: два артикула в
 * подвесе легко имеют разные обработки, и сводка в «Профиле» не отвечала на
 * вопрос «1,8 м — это который?».
 */
export function ProfileBadges({ profile, solo = false }: { profile: ProfileInfo; solo?: boolean }) {
  if (!hasProfileBadges(profile)) return null;

  return (
    <div
      className={`flex flex-wrap items-center justify-center gap-1 ${
        solo ? "max-w-[148px]" : "max-w-[70px]"
      }`}
    >
      {profile.processing.map((proc, i) => (
        <Badge
          key={i}
          className="text-[10px] px-1 py-0 bg-yellow-400 text-yellow-900 hover:bg-yellow-500"
        >
          {proc}
        </Badge>
      ))}
      {profile.length_text && (
        <Badge
          className="text-[10px] px-1 py-0 whitespace-nowrap bg-indigo-100 text-indigo-900 border-indigo-300 hover:bg-indigo-200"
          title={`Длина ${profile.length_text}`}
          aria-label={`Длина ${profile.length_text}`}
        >
          {profile.length_text}
        </Badge>
      )}
    </div>
  );
}

/**
 * Снимок профиля в полосе фиксированной высоты.
 *
 * Полоса одна на все снимки строки. Пара прижимается к низу: кадры разной
 * высоты встают на одну линию. Одиночный кадр сравнивать не с чем, поэтому он
 * центрируется в полосе — иначе короткий снимок одиноко висит на её дне, пока
 * бейдж рядом стоит по центру. Заглушки нет — профиль без файла ничего не
 * показывает.
 */
export function ProfileThumb({
  profile,
  onPhotoClick,
  solo = false,
  markShort = false,
  photoMax,
  onSized,
}: {
  profile: ProfileInfo;
  onPhotoClick: (url: string, name: string) => void;
  /** Снимок один в ячейке: ему доступна вся ширина колонки. */
  solo?: boolean;
  /** Обвести снимки, сжатые по ширине (?stress). */
  markShort?: boolean;
  /** Потолок ширины снимка, px: поджали, чтобы подпись влезла сбоку. */
  photoMax?: number;
  /** Снимок получил размеры: ячейке пора решить, влезает ли подпись сбоку. */
  onSized?: () => void;
}) {
  const thumbUrl = photoUrl(profile.photo_thumb, profile.photo_thumb_version);
  if (!profile.has_photo || !thumbUrl) return null;

  const fullUrl = profile.photo_full
    ? photoUrl(profile.photo_full, profile.photo_full_version)
    : thumbUrl;

  return (
    <div
      className={`flex justify-center ${solo ? "items-center" : "items-end"}`}
      style={{ height: PHOTO_HEIGHT }}
    >
      <PhotoImage
        src={thumbUrl}
        alt={profile.name}
        solo={solo}
        markShort={markShort}
        photoMax={photoMax}
        onSized={onSized}
        onClick={() => onPhotoClick(fullUrl || "", profile.canonical_name || profile.name)}
      />
    </div>
  );
}

/**
 * Снимок в ячейке «Фото» вместе с артикулом и бейджами своего профиля.
 *
 * Снимок стоит в полосе фиксированной высоты. Артикул и бейджи — колонка сбоку
 * от снимка: строка не растёт вверх, а подпись стоит прямо у своего кадра.
 * `compact` — крайний случай, когда рядом места нет совсем: тогда подпись и
 * бейджи переносятся под полосу снимка и держатся в его слоте.
 *
 * `showName` включается, когда снимков меньше, чем профилей: по ячейке
 * «Профиль» там стоит «3416 + 362», и без подписи у кадра не понять, чей он.
 * Когда кадр есть у каждого профиля, порядок кадров совпадает с порядком
 * артикулов, и подпись только добавляет строку высоты.
 */
export function ProfilePhotoSlot({
  profile,
  onPhotoClick,
  solo = false,
  markShort = false,
  showName = false,
  compact = false,
  photoMax,
  onSized,
}: {
  profile: ProfileInfo;
  onPhotoClick: (url: string, name: string) => void;
  /** Снимок один в ячейке: ему доступна вся ширина колонки. */
  solo?: boolean;
  /** Обвести снимки, сжатые по ширине (?stress). */
  markShort?: boolean;
  /** В подвесе снимков меньше, чем профилей: у кадра нужен его артикул. */
  showName?: boolean;
  /** Сбоку места нет совсем: подпись и бейджи уходят под снимок. */
  compact?: boolean;
  /** Потолок ширины снимка, px: поджали, чтобы подпись влезла сбоку. */
  photoMax?: number;
  /** Снимок получил размеры: ячейке пора решить, влезает ли подпись сбоку. */
  onSized?: () => void;
}) {
  const name = profile.canonical_name || profile.name;
  const slot = solo ? "max-w-[148px]" : "max-w-[70px]";

  return (
    <div
      data-photo-slot=""
      className={
        compact
          ? `flex flex-wrap items-center justify-center gap-x-1 gap-y-0.5 ${slot}`
          : // Сбоку от снимка места хватает: слот не режем, иначе подпись
            // переносилась бы под кадр, хотя свободная ширина в колонке есть.
            `flex items-center justify-center gap-1 ${slot}`
      }
    >
      <ProfileThumb
        profile={profile}
        onPhotoClick={onPhotoClick}
        solo={solo}
        markShort={markShort}
        photoMax={photoMax}
        onSized={onSized}
      />
      {(showName || hasProfileBadges(profile)) && (
        <div
          data-photo-side=""
          className={`flex min-w-0 flex-col items-center justify-center gap-0.5 ${
            compact ? "" : "flex-shrink-0"
          }`}
        >
          {showName && (
            <span
              className={`text-center text-[10px] font-semibold leading-tight text-foreground/75 ${
                compact ? `break-words ${slot}` : "whitespace-nowrap"
              }`}
              title={name}
            >
              {name}
            </span>
          )}
          <ProfileBadges profile={profile} solo={solo} />
        </div>
      )}
    </div>
  );
}

/**
 * Профиль во втором ряду подвеса: снимок, артикул и бейджи в одну линию.
 * Здесь бейджи стоят справа от снимка — второго ряда в строке уже нет, и
 * подпись с бейджами читается как одна запись.
 */
export function ProfilePhoto({
  profile,
  onPhotoClick,
  markShort = false,
}: {
  profile: ProfileInfo;
  onPhotoClick: (url: string, name: string) => void;
  /** Обвести снимки, сжатые по ширине (?stress). */
  markShort?: boolean;
}) {
  return (
    <div className="flex items-end gap-2">
      <ProfileThumb profile={profile} onPhotoClick={onPhotoClick} markShort={markShort} />
      <div className="flex flex-col justify-end min-w-0">
        {/* Подпись под фото — полное имя: в ряду подвеса места хватает,
            а обрезанный артикул оператор не восстановит. */}
        <p className="text-xs font-bold text-foreground break-words max-w-[110px]">
          {profile.canonical_name || profile.name}
        </p>
        <ProfileBadges profile={profile} />
      </div>
    </div>
  );
}
