import { Image } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { photoUrl } from "@/lib/domain/photo";
import type { ProfileInfo } from "@/types/dashboard";

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
}: {
  profile: ProfileInfo;
  onPhotoClick: (url: string, name: string) => void;
  hideText?: boolean;
}) {
  const thumbUrl = photoUrl(profile.photo_thumb, profile.photo_thumb_version);
  const fullUrl = profile.photo_full
    ? photoUrl(profile.photo_full, profile.photo_full_version)
    : photoUrl(profile.photo_thumb, profile.photo_thumb_version);
  const hasPhoto = profile.has_photo && thumbUrl;
  const hasBadges = Boolean(profile.length_text || profile.processing.length);

  return (
    <div className="flex items-center gap-2">
      {hasPhoto ? (
        <img
          src={thumbUrl}
          alt={profile.name}
          className="w-auto h-auto max-h-[40px] max-w-[90px] object-contain rounded cursor-pointer hover:scale-105 transition-transform border border-border hover:border-primary flex-shrink-0"
          onClick={() => onPhotoClick(fullUrl || "", profile.canonical_name || profile.name)}
        />
      ) : (
        <div className="w-12 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
          <Image className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
      {!hideText && (
        <div className="flex flex-col justify-center min-w-0">
          <p className="text-xs font-bold text-foreground truncate max-w-[70px]">
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
