import { useState } from "react";
import { Image } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { photoUrl } from "@/lib/domain/photo";
import type { ProfileInfo } from "@/types/dashboard";

/** Потолок снимка по высоте, px: строка дашборда не растёт из-за фото. */
const PHOTO_HEIGHT = 40;

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
}: {
  src: string;
  alt: string;
  onClick?: () => void;
  /** Снимок один в ячейке: ему доступна вся ширина колонки. */
  solo?: boolean;
  /** Обвести снимки, потерявшие высоту из-за потолка ширины (?stress). */
  markShort?: boolean;
}) {
  const [short, setShort] = useState(false);
  const maxWidth = solo ? PHOTO_SOLO_MAX_WIDTH : PHOTO_PAIR_MAX_WIDTH;

  return (
    <img
      src={src}
      alt={alt}
      data-short-photo={short ? "1" : undefined}
      title={short ? "Снимок сжат по ширине: высота меньше 40 px" : undefined}
      className={`w-auto h-auto max-h-[40px] ${
        solo ? "max-w-[148px]" : "max-w-[70px]"
      } object-contain rounded cursor-pointer hover:scale-105 transition-transform border border-border hover:border-primary flex-shrink-0 ${
        short ? "ring-2 ring-rose-500 ring-offset-1" : ""
      }`}
      onLoad={(event) => {
        if (!markShort) return;
        const img = event.currentTarget;
        const { naturalWidth: w, naturalHeight: h } = img;
        // Рамка 1 px входит в потолок (box-sizing: border-box), поэтому
        // содержимому остаётся (maxWidth − 2) × 38 px. Снимок теряет высоту,
        // когда масштаб упирается в ширину: при 148/40 это аспект шире 3,7:1.
        // Обводим только заметно сжатые (ниже 36 из 40 px): 38 px на глаз не
        // отличить от 40, и такие снимки только шумели бы в сотне строк.
        if (w && h) {
          const scale = Math.min(1, (maxWidth - 2) / w, (PHOTO_HEIGHT - 2) / h);
          setShort(2 + h * scale < PHOTO_HEIGHT - 4);
        }
      }}
      onClick={onClick}
    />
  );
}

/**
 * Профиль в ячейке «Фото»: снимок или заглушка, артикул, обработки и длина.
 *
 * Длина приходит из книги (`length_text`), а не из каталога: каталожная длина
 * в миллиметрах — другой признак (ADR 0012). Бейдж стоит второй строкой под
 * артикулом, в одном ряду с обработками, и не переносит фото на второй ряд.
 */
export function ProfilePhoto({
  profile,
  onPhotoClick,
  hideText = false,
  solo = false,
  markShort = false,
}: {
  profile: ProfileInfo;
  onPhotoClick: (url: string, name: string) => void;
  hideText?: boolean;
  /** Снимок один в ячейке: ему доступна вся ширина колонки. */
  solo?: boolean;
  /** Обвести снимки, сжатые по ширине (?stress). */
  markShort?: boolean;
}) {
  const thumbUrl = photoUrl(profile.photo_thumb, profile.photo_thumb_version);
  const fullUrl = profile.photo_full
    ? photoUrl(profile.photo_full, profile.photo_full_version)
    : photoUrl(profile.photo_thumb, profile.photo_thumb_version);
  /** Снимок к показу: нет файла или профиль без фото — заглушка. */
  const thumbSrc = profile.has_photo ? thumbUrl : null;
  const hasBadges = Boolean(profile.length_text || profile.processing.length);

  return (
    <div className="flex items-center gap-2">
      {thumbSrc ? (
        <PhotoImage
          src={thumbSrc}
          alt={profile.name}
          solo={solo}
          markShort={markShort}
          onClick={() => onPhotoClick(fullUrl || "", profile.canonical_name || profile.name)}
        />
      ) : (
        <div className="w-12 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
          <Image className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
      {!hideText && (
        <div className="flex flex-col justify-center min-w-0">
          {/* Подпись под фото — полное имя: в ряду подвеса места хватает,
              а обрезанный артикул оператор не восстановит. */}
          <p className="text-xs font-bold text-foreground break-words max-w-[110px]">
            {profile.canonical_name || profile.name}
          </p>
          {hasBadges && (
            <div className="flex gap-1 mt-1 flex-wrap">
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
          )}
        </div>
      )}
    </div>
  );
}
