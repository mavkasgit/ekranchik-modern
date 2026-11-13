// Полноэкранный просмотр фото артикула.
//
// «1×» здесь — «вписано»: фото целиком помещается в окно, даже если оно
// портретное и открыто на телефоне. Зум считается поверх вписанного
// (1–4×), колесо и пинч приближают к курсору/пальцу, панорама не выпускает
// картинку за окно, двойной клик возвращает «вписано».
//
// Оверлей — отдельный Radix-диалог, а не `fixed`-блок внутри карточки:
// карточка артикула сама диалог, и её контейнер сдвинут `translate`, из-за
// чего вложенный `fixed` считался бы от неё, а не от экрана. Заодно Radix
// держит Esc, фокус и блокировку прокрутки — при открытом фото Esc закрывает
// только просмотрщик, карточка остаётся.

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  Check,
  Copy,
  Download,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  RotateCcw,
  X,
} from "lucide-react";
import {
  MAX_ZOOM,
  MIN_ZOOM,
  ZOOM_STEP,
  clampPan,
  clampZoom,
  resetView,
  zoomAroundPoint,
  zoomFromWheel,
  type PhotoView,
  type Point,
} from "@/lib/domain/photoViewer";
import { copyPhoto, downloadPhoto } from "@/lib/photoTransfer";

interface Notice {
  text: string;
  tone: "success" | "error";
}

interface DragState {
  pointerId: number;
  start: Point;
  pan: Point;
}

interface PinchState {
  distance: number;
  midpoint: Point;
  view: PhotoView;
}

function midpoint(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function distanceBetween(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** Координаты указателя относительно центра окна: так считает зум математика. */
function pointerInViewport(content: HTMLElement, clientX: number, clientY: number): Point {
  const rect = content.getBoundingClientRect();
  return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
}

/** Прижимает панораму к границам окна по реальным размерам картинки. */
function fitIntoWindow(
  next: PhotoView,
  content: HTMLElement | null,
  image: HTMLImageElement | null,
): PhotoView {
  if (!content || !image || !image.naturalWidth || !image.naturalHeight) return next;
  const rect = content.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return next;
  return {
    zoom: next.zoom,
    pan: clampPan(
      next.pan,
      next.zoom,
      { width: image.naturalWidth, height: image.naturalHeight },
      { width: rect.width, height: rect.height },
    ),
  };
}

function ViewerButton({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="flex h-10 w-10 items-center justify-center rounded-full border border-zinc-700/60 bg-zinc-900/90 text-zinc-200 shadow-lg backdrop-blur-sm transition-colors hover:bg-zinc-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 active:scale-95 disabled:opacity-40 disabled:hover:bg-zinc-900/90"
    >
      {children}
    </button>
  );
}

export function PhotoViewer({
  src,
  article,
  onClose,
}: {
  /** Полное фото, а не превью. */
  src: string;
  /** Артикул: alt картинки и имя скачанного файла. */
  article: string;
  onClose: () => void;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [view, setView] = useState<PhotoView>(resetView);
  const viewRef = useRef(view);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [copied, setCopied] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const pointersRef = useRef(new Map<number, Point>());
  const dragRef = useRef<DragState | null>(null);
  const pinchRef = useRef<PinchState | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const commitView = useCallback((next: PhotoView) => {
    const fitted = fitIntoWindow(next, contentRef.current, imageRef.current);
    viewRef.current = fitted;
    setView(fitted);
  }, []);

  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  // Колесо слушаем нативно: React вешает wheel пассивно, и preventDefault
  // в синтетическом обработчике не остановил бы прокрутку страницы.
  //
  // Слушатель висит на window, а не на contentRef: Radix монтирует содержимое
  // диалога в портал, и на момент этого эффекта ref ещё может быть пустым.
  // Цель проверяем в самом обработчике — тогда зум работает и после портала.
  useEffect(() => {
    const handleWheel = (event: WheelEvent) => {
      const content = contentRef.current;
      if (!content) return;
      if (!(event.target instanceof Node) || !content.contains(event.target)) return;

      event.preventDefault();
      const nextZoom = zoomFromWheel(event.deltaY, viewRef.current.zoom);
      if (nextZoom === viewRef.current.zoom) return;
      const pointer = pointerInViewport(content, event.clientX, event.clientY);
      commitView(zoomAroundPoint(viewRef.current, pointer, nextZoom));
    };

    window.addEventListener("wheel", handleWheel, { passive: false });
    return () => window.removeEventListener("wheel", handleWheel);
  }, [commitView]);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  // Закрытие просмотрщика не должно оставлять браузер в полноэкранном режиме,
  // но чужой фуллскрин (киоск) не трогаем.
  useEffect(() => {
    const content = contentRef.current;
    return () => {
      if (content && document.fullscreenElement === content) {
        void document.exitFullscreen().catch(() => {});
      }
    };
  }, []);

  const showNotice = (text: string, tone: Notice["tone"]) => {
    setNotice({ text, tone });
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 4000);
  };

  const handleCopy = async () => {
    try {
      await copyPhoto(src, imageRef.current);
      setCopied(true);
      showNotice("Фото скопировано в буфер обмена", "success");
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
      copiedTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      showNotice("Не удалось скопировать — скачайте файл", "error");
    }
  };

  const handleDownload = async () => {
    try {
      const fileName = await downloadPhoto(src, article);
      showNotice(`Файл ${fileName} сохранён`, "success");
    } catch {
      showNotice("Не удалось скачать фото", "error");
    }
  };

  const toggleFullscreen = async () => {
    const content = contentRef.current;
    if (!content) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await content.requestFullscreen();
    } catch {
      showNotice("Браузер не разрешил полноэкранный режим", "error");
    }
  };

  const zoomTo = (nextZoom: number, pointer: Point) => {
    commitView(zoomAroundPoint(viewRef.current, pointer, nextZoom));
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;

    const content = event.currentTarget;
    content.setPointerCapture(event.pointerId);
    const point = { x: event.clientX, y: event.clientY };
    const pointers = pointersRef.current;
    pointers.set(event.pointerId, point);

    if (pointers.size === 2) {
      const [first, second] = [...pointers.values()];
      dragRef.current = null;
      pinchRef.current = {
        distance: distanceBetween(first, second),
        midpoint: midpoint(first, second),
        view: viewRef.current,
      };
    } else if (pointers.size === 1) {
      dragRef.current = { pointerId: event.pointerId, start: point, pan: viewRef.current.pan };
    }
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const pointers = pointersRef.current;
    if (!pointers.has(event.pointerId)) return;

    const content = event.currentTarget;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    const pinch = pinchRef.current;
    if (pointers.size >= 2 && pinch) {
      const [first, second] = [...pointers.values()];
      if (pinch.distance <= 0) return;
      const mid = midpoint(first, second);
      const nextZoom = clampZoom(
        pinch.view.zoom * (distanceBetween(first, second) / pinch.distance),
      );
      const zoomed = zoomAroundPoint(
        pinch.view,
        pointerInViewport(content, mid.x, mid.y),
        nextZoom,
      );
      // Пальцы не только раздвигаются, но и едут: картинка следует за серединой.
      commitView({
        zoom: zoomed.zoom,
        pan: {
          x: zoomed.pan.x + (mid.x - pinch.midpoint.x),
          y: zoomed.pan.y + (mid.y - pinch.midpoint.y),
        },
      });
      return;
    }

    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    commitView({
      zoom: viewRef.current.zoom,
      pan: {
        x: drag.pan.x + (event.clientX - drag.start.x),
        y: drag.pan.y + (event.clientY - drag.start.y),
      },
    });
  };

  const handlePointerEnd = (event: React.PointerEvent<HTMLDivElement>) => {
    const pointers = pointersRef.current;
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinchRef.current = null;

    const [remainingId] = [...pointers.keys()];
    const remaining = remainingId !== undefined ? pointers.get(remainingId) : undefined;
    dragRef.current =
      remainingId !== undefined && remaining
        ? { pointerId: remainingId, start: remaining, pan: viewRef.current.pan }
        : null;
  };

  // Двойной клик — сброс; кнопки панели его не перехватывают.
  const handleDoubleClick = () => commitView(resetView());

  const zoomLabel = `${Number(view.zoom.toFixed(2))}×`;
  const scaleHint = view.zoom <= MIN_ZOOM ? `${zoomLabel} · вписано` : zoomLabel;

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[90] bg-black" />
        <DialogPrimitive.Content
          ref={contentRef}
          data-testid="photo-viewer"
          aria-describedby={undefined}
          className="fixed inset-0 z-[100] flex h-dvh w-screen max-w-none touch-none select-none items-center justify-center overflow-hidden border-0 bg-black p-0 shadow-none outline-none"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerEnd}
          onPointerCancel={handlePointerEnd}
          onDoubleClick={handleDoubleClick}
        >
          <DialogPrimitive.Title className="sr-only">Фото {article}</DialogPrimitive.Title>

          <div
            data-photo-controls
            className="absolute right-3 top-3 z-10 flex max-w-[calc(100vw-1.5rem)] flex-wrap justify-end gap-1.5 sm:right-4 sm:top-4 sm:gap-2"
            onPointerDown={(event) => event.stopPropagation()}
            onDoubleClick={(event) => event.stopPropagation()}
          >
            <ViewerButton
              label="Отдалить"
              onClick={() => zoomTo(clampZoom(view.zoom - ZOOM_STEP), { x: 0, y: 0 })}
              disabled={view.zoom <= MIN_ZOOM}
            >
              <Minus className="h-5 w-5" />
            </ViewerButton>
            <ViewerButton
              label="Приблизить"
              onClick={() => zoomTo(clampZoom(view.zoom + ZOOM_STEP), { x: 0, y: 0 })}
              disabled={view.zoom >= MAX_ZOOM}
            >
              <Plus className="h-5 w-5" />
            </ViewerButton>
            <ViewerButton label="Сбросить масштаб" onClick={() => commitView(resetView())}>
              <RotateCcw className="h-5 w-5" />
            </ViewerButton>
            <ViewerButton
              label={isFullscreen ? "Свернуть" : "Развернуть"}
              onClick={() => void toggleFullscreen()}
            >
              {isFullscreen ? <Minimize2 className="h-5 w-5" /> : <Maximize2 className="h-5 w-5" />}
            </ViewerButton>
            <ViewerButton label="Копировать фото" onClick={() => void handleCopy()}>
              {copied ? <Check className="h-5 w-5 text-green-400" /> : <Copy className="h-5 w-5" />}
            </ViewerButton>
            <ViewerButton label="Скачать фото" onClick={() => void handleDownload()}>
              <Download className="h-5 w-5" />
            </ViewerButton>
            <ViewerButton label="Закрыть фото" onClick={onClose}>
              <X className="h-5 w-5" />
            </ViewerButton>
          </div>

          <img
            ref={imageRef}
            src={src}
            alt={article}
            draggable={false}
            onDragStart={(event) => event.preventDefault()}
            onLoad={() => commitView(viewRef.current)}
            className="max-h-full max-w-full object-contain will-change-transform"
            style={{
              transform: `translate3d(${view.pan.x}px, ${view.pan.y}px, 0) scale(${view.zoom})`,
              cursor: view.zoom > MIN_ZOOM ? "grab" : "default",
            }}
          />

          {notice && (
            <div
              role="status"
              className={`absolute bottom-16 left-1/2 z-10 -translate-x-1/2 rounded-full px-4 py-2 text-sm text-white shadow-lg backdrop-blur-sm ${
                notice.tone === "error" ? "bg-red-600/90" : "bg-green-600/90"
              }`}
            >
              {notice.text}
            </div>
          )}

          <p className="pointer-events-none absolute bottom-4 left-4 z-10 max-w-[calc(100vw-2rem)] text-xs text-white/60 sm:text-sm">
            {scaleHint} · колесо или пинч — масштаб · перетаскивание — панорама · двойной клик —
            сброс · Esc — закрыть
          </p>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
