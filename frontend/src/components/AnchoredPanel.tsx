import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

// Позиционируемый портал для поповеров фильтра. Таблица сидит в контейнере с
// `overflow-auto`, поэтому панель внутри заголовка обрезалась бы; портал
// выносит её в `document.body`, а позиция считается по кнопке при открытии.

const FILTER_PANEL_WIDTH = 320;
const FILTER_PANEL_MAX_HEIGHT = 600;
const FILTER_PANEL_MIN_HEIGHT = 160;
const FILTER_PANEL_ESTIMATED_HEIGHT = 380;
const VIEWPORT_GAP = 8;

export interface PanelPosition {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

/**
 * Где показать панель шириной `width`: прижимаем к правому краю кнопки и не
 * выпускаем за вьюпорт. Вниз панель раскрывается, только если там есть место;
 * иначе — вверх. Высота ограничивается свободным краем, чтобы низ панели
 * (кнопка «Готово») не уезжал за экран.
 */
export function panelPosition(
  anchor: Pick<DOMRect, "right" | "top" | "bottom">,
  viewport: { width: number; height: number },
): PanelPosition {
  const width = Math.min(FILTER_PANEL_WIDTH, viewport.width - VIEWPORT_GAP * 2);
  const left = Math.max(
    VIEWPORT_GAP,
    Math.min(anchor.right - width, viewport.width - width - VIEWPORT_GAP),
  );

  const downSpace = viewport.height - anchor.bottom - VIEWPORT_GAP * 2;
  const upSpace = anchor.top - VIEWPORT_GAP * 2;
  const openUp = downSpace < FILTER_PANEL_ESTIMATED_HEIGHT / 2 && upSpace > downSpace;
  const available = openUp ? upSpace : downSpace;
  const maxHeight = Math.max(FILTER_PANEL_MIN_HEIGHT, Math.min(FILTER_PANEL_MAX_HEIGHT, available));

  return openUp
    ? { left, bottom: viewport.height - anchor.top + 6, maxHeight }
    : { left, top: anchor.bottom + 6, maxHeight };
}

export interface AnchoredPanelProps {
  open: boolean;
  position: PanelPosition | null;
  anchorRef: RefObject<HTMLElement | null>;
  ariaLabel: string;
  onClose: () => void;
  children: ReactNode;
}

export function AnchoredPanel({
  open,
  position,
  anchorRef,
  ariaLabel,
  onClose,
  children,
}: AnchoredPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || anchorRef.current?.contains(target)) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    // Позиция посчитана по кнопке: после прокрутки страницы или ресайза она
    // устареет. Прокрутка внутри самой панели (список значений) позицию не
    // меняет и закрывать панель не должна.
    const closeOnLayoutChange = (event: Event) => {
      if (
        event.type === "scroll" &&
        panelRef.current &&
        event.target instanceof Node &&
        panelRef.current.contains(event.target)
      ) {
        return;
      }
      onClose();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", closeOnLayoutChange);
    window.addEventListener("scroll", closeOnLayoutChange, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", closeOnLayoutChange);
      window.removeEventListener("scroll", closeOnLayoutChange, true);
    };
  }, [open, onClose, anchorRef, ariaLabel]);

  if (!open || !position) return null;

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={ariaLabel}
      style={{
        top: position.top,
        left: position.left,
        bottom: position.bottom,
        maxHeight: position.maxHeight,
      }}
      className="fixed z-50 w-[min(20rem,calc(100vw-1rem))] overflow-y-auto rounded-md border bg-popover p-3 text-popover-foreground shadow-md"
    >
      {children}
    </div>,
    document.body,
  );
}
