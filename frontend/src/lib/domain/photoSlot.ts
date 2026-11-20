// Подгонка снимка в колонке «Фото»: сколько места остаётся подписи сбоку и
// можно ли ужать кадр, чтобы подпись не уезжала под него. Правило живёт здесь,
// а не в разметке: его проверяют тесты без браузера, а страница только читает
// готовое решение.

/** Потолок снимка по высоте, px: строка дашборда не растёт из-за фото. */
export const PHOTO_HEIGHT = 40;

/** Рамка снимка, px: входит в потолок высоты (`box-sizing: border-box`). */
const PHOTO_BORDER = 2;

/** Просвет между снимком и его подписью или бейджами, px (`gap-1`). */
const PHOTO_SIDE_GAP = 4;

/** Уже этого снимок не ужимаем ради подписи: деталь перестанет читаться. */
export const MIN_PHOTO_WIDTH = 40;

/** Насколько можно ужать кадр ради подписи сбоку. */
const MAX_PHOTO_SHRINK = 0.25;

/**
 * Во сколько раз уменьшается кадр в полосе: упирается в ширину слота или в
 * потолок высоты. Снимок теряет высоту, когда масштаб упирается в ширину:
 * при 148/40 это аспект шире 3,7:1.
 */
function photoBandScale(naturalWidth: number, naturalHeight: number, bandWidth: number): number {
  if (!naturalWidth || !naturalHeight) return 0;
  return Math.min(
    1,
    (bandWidth - PHOTO_BORDER) / naturalWidth,
    (PHOTO_HEIGHT - PHOTO_BORDER) / naturalHeight,
  );
}

/** Ширина снимка при полной полосе: аспект, потолок высоты и рамка. */
export function photoWidthAtBand(
  naturalWidth: number,
  naturalHeight: number,
  bandWidth: number,
): number {
  if (!naturalWidth || !naturalHeight) return 0;
  return PHOTO_BORDER + naturalWidth * photoBandScale(naturalWidth, naturalHeight, bandWidth);
}

/** Высота снимка при полной полосе: по ней видно, что кадр вышел полосой. */
export function photoHeightAtBand(
  naturalWidth: number,
  naturalHeight: number,
  bandWidth: number,
): number {
  if (!naturalWidth || !naturalHeight) return 0;
  return PHOTO_BORDER + naturalHeight * photoBandScale(naturalWidth, naturalHeight, bandWidth);
}

export interface PhotoSlotPlan {
  /** Сбоку не влезает даже с ужатым кадром: подпись и бейджи уходят под снимок. */
  compact: boolean;
  /** Потолок ширины кадра, px: поджали, чтобы подпись влезла сбоку. */
  photoMax?: number;
}

/**
 * Решение по слоту «Фото»: подпись сбоку или под кадром.
 *
 * Сначала кадр поджимается под подпись — не больше чем на четверть и не ниже
 * 40 px: ужать кадр дешевле, чем вырастить строку. Если и ужатый кадр оставляет
 * подписи слишком мало места, она уходит под снимок. Кадр уже 40 px — ужимать
 * некуда, и потолок 40 px к нему не применяется: работает только доля.
 */
export function planPhotoSlot({
  naturalWidth,
  naturalHeight,
  sideWidth,
  slotWidth,
}: {
  naturalWidth: number;
  naturalHeight: number;
  sideWidth: number;
  slotWidth: number;
}): PhotoSlotPlan {
  const bandWidth = photoWidthAtBand(naturalWidth, naturalHeight, slotWidth);
  if (!bandWidth || sideWidth <= 0) return { compact: false };

  const free = slotWidth - PHOTO_SIDE_GAP - sideWidth;
  // Пол поджатия: не уже 75 % ширины кадра, для кадра от 40 px — и не ниже 40.
  const floor =
    bandWidth >= MIN_PHOTO_WIDTH
      ? Math.max(MIN_PHOTO_WIDTH, bandWidth * (1 - MAX_PHOTO_SHRINK))
      : bandWidth * (1 - MAX_PHOTO_SHRINK);
  // Пиксель допуска: дробная ширина подписи не повод переносить её под кадр.
  if (free + 1 < floor) return { compact: true };

  const photoMax = Math.floor(free);
  return { compact: false, photoMax: photoMax < Math.floor(bandWidth) ? photoMax : undefined };
}
