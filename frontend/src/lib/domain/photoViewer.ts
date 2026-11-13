// Математика просмотрщика фото: «вписано», зум и панорама.
//
// «1×» здесь — вписанный масштаб, а не натуральный размер: портретное фото
// на экране киоска иначе не помещается целиком. Зум считается поверх
// вписанного, поэтому `fitScale` зависит только от картинки и окна, а `zoom`
// меняется жестами в пределах 1–4×.

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Масштаб относительно вписанного и сдвиг в пикселях экрана. */
export interface PhotoView {
  zoom: number;
  pan: Point;
}

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;
/** Шаг колеса и кнопок «+»/«−»: 12 шагов от «вписано» до 4×. */
export const ZOOM_STEP = 0.25;

/** Масштаб, при котором картинка целиком входит в окно. Мелкую не растягиваем. */
export function fitScale(natural: Size, viewport: Size): number {
  if (natural.width <= 0 || natural.height <= 0) return 1;
  if (viewport.width <= 0 || viewport.height <= 0) return 1;
  return Math.min(1, viewport.width / natural.width, viewport.height / natural.height);
}

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) return MIN_ZOOM;
  // Два знака: пинч приходит с дробным множителем и без округления копит хвост.
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(zoom * 100) / 100));
}

/** Размер картинки на экране: вписанный размер, умноженный на зум. */
function displayedSize(natural: Size, viewport: Size, zoom: number): Size {
  const scale = fitScale(natural, viewport) * zoom;
  return { width: natural.width * scale, height: natural.height * scale };
}

/**
 * Не даёт картинке уехать за окно. По оси, где она меньше окна, сдвиг нулевой:
 * пустые поля по краям — это и есть «вписано».
 */
export function clampPan(pan: Point, zoom: number, natural: Size, viewport: Size): Point {
  const size = displayedSize(natural, viewport, zoom);
  const maxX = Math.max(0, (size.width - viewport.width) / 2);
  const maxY = Math.max(0, (size.height - viewport.height) / 2);
  return {
    x: clampAxis(pan.x, maxX),
    y: clampAxis(pan.y, maxY),
  };
}

function clampAxis(value: number, max: number): number {
  const clamped = Math.min(max, Math.max(-max, value));
  // Math.max(-0, 0) даёт -0: в transform он уходит как «-0px», а в тестах
  // отличается от нуля.
  return clamped === 0 ? 0 : clamped;
}

/**
 * Зум к курсору или середине пинча: точка под указателем остаётся на месте.
 * `pointer` — координаты относительно центра окна. Границы панорамы проверяет
 * вызывающий: у этой функции нет размеров окна.
 */
export function zoomAroundPoint(view: PhotoView, pointer: Point, nextZoom: number): PhotoView {
  const zoom = clampZoom(nextZoom);
  if (zoom === view.zoom) return view;

  const factor = zoom / view.zoom;
  return {
    zoom,
    pan: {
      x: pointer.x - (pointer.x - view.pan.x) * factor,
      y: pointer.y - (pointer.y - view.pan.y) * factor,
    },
  };
}

/** Один шаг колеса: от себя — ближе, на себя — дальше, без выхода за 1–4×. */
export function zoomFromWheel(deltaY: number, zoom: number): number {
  if (!Number.isFinite(deltaY) || deltaY === 0) return zoom;
  return clampZoom(zoom + (deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP));
}

/** Двойной клик и кнопка сброса: «вписано» по центру. */
export function resetView(): PhotoView {
  return { zoom: MIN_ZOOM, pan: { x: 0, y: 0 } };
}
