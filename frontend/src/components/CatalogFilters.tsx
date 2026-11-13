import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Filter, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { activeFilterCount, type CatalogFilters } from "@/lib/domain/catalogView";
import { cn } from "@/lib/utils";

// Фильтры живут в заголовках колонок (таблица) и за кнопкой «Фильтры»
// (плитка), но реализация одна: тот же поповер, тот же набор полей и общие
// для обоих режимов значения. Панель диапазонов над списком не заводится.

export type FilterField =
  | "name"
  | "description"
  | "quantity"
  | "length"
  | "notes"
  | "has_photo"
  | "updated_at";

export const ALL_FILTER_FIELDS: FilterField[] = [
  "name",
  "description",
  "quantity",
  "length",
  "notes",
  "has_photo",
  "updated_at",
];

const PANEL_WIDTH = 320;
const PANEL_ESTIMATED_HEIGHT = 360;
const VIEWPORT_GAP = 8;

function numberOrNull(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toggleLength(lengths: Set<number>, length: number, checked: boolean): Set<number> {
  const next = new Set(lengths);
  if (checked) next.add(length);
  else next.delete(length);
  return next;
}

function formatDay(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

interface FilterFieldsProps {
  fields: FilterField[];
  filters: CatalogFilters;
  lengths: number[];
  onChange: (patch: Partial<CatalogFilters>) => void;
}

/** Поля поповера: показываются только те, что есть у конкретной колонки. */
function FilterFields({
  fields,
  filters,
  lengths,
  onChange,
  idPrefix,
}: FilterFieldsProps & { idPrefix: string }) {
  return (
    <div className="space-y-3">
      {fields.includes("name") && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-name`}>Артикул содержит</Label>
          <Input
            id={`${idPrefix}-name`}
            value={filters.name}
            onChange={(event) => onChange({ name: event.target.value })}
            placeholder="Например, ЮП-3168"
            autoFocus={fields.length > 1}
          />
        </div>
      )}

      {fields.includes("description") && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-description`}>Наименование содержит</Label>
          <Input
            id={`${idPrefix}-description`}
            value={filters.description}
            onChange={(event) => onChange({ description: event.target.value })}
            placeholder="Например, крючок"
            autoFocus={fields.length === 1}
          />
        </div>
      )}

      {fields.includes("quantity") && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-quantity-from`}>Количество на подвесе</Label>
          <div className="flex items-center gap-2">
            <Input
              id={`${idPrefix}-quantity-from`}
              type="number"
              min={0}
              inputMode="numeric"
              placeholder="от"
              value={filters.quantityFrom ?? ""}
              onChange={(event) => onChange({ quantityFrom: numberOrNull(event.target.value) })}
              autoFocus={fields.length === 1}
            />
            <span className="text-muted-foreground">—</span>
            <Input
              type="number"
              min={0}
              inputMode="numeric"
              placeholder="до"
              value={filters.quantityTo ?? ""}
              onChange={(event) => onChange({ quantityTo: numberOrNull(event.target.value) })}
              aria-label="Количество до"
            />
          </div>
        </div>
      )}

      {fields.includes("length") && (
        <div className="space-y-1.5">
          <Label>Длина, мм</Label>
          <div className="max-h-40 space-y-1 overflow-y-auto pr-1">
            {lengths.length === 0 && (
              <p className="text-xs text-muted-foreground">В каталоге нет длин</p>
            )}
            {lengths.map((length) => (
              <label
                key={length}
                className="flex cursor-pointer items-center gap-2 rounded-sm py-0.5 text-sm"
              >
                <Checkbox
                  checked={filters.lengths.has(length)}
                  onCheckedChange={(checked) =>
                    onChange({ lengths: toggleLength(filters.lengths, length, checked === true) })
                  }
                />
                {length} мм
              </label>
            ))}
          </div>
        </div>
      )}

      {fields.includes("notes") && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-notes`}>Примечание содержит</Label>
          <Input
            id={`${idPrefix}-notes`}
            value={filters.notes}
            onChange={(event) => onChange({ notes: event.target.value })}
            placeholder="Например, аналог"
            autoFocus={fields.length === 1}
          />
        </div>
      )}

      {fields.includes("has_photo") && (
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox
            checked={filters.hasPhoto}
            onCheckedChange={(checked) => onChange({ hasPhoto: checked === true })}
          />
          Только с фото
        </label>
      )}

      {fields.includes("updated_at") && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-updated-from`}>Изменён</Label>
          <div className="flex items-center gap-2">
            <Input
              id={`${idPrefix}-updated-from`}
              type="date"
              value={filters.updatedFrom ?? ""}
              onChange={(event) => onChange({ updatedFrom: event.target.value || null })}
              autoFocus={fields.length === 1}
            />
            <span className="text-muted-foreground">—</span>
            <Input
              type="date"
              value={filters.updatedTo ?? ""}
              onChange={(event) => onChange({ updatedTo: event.target.value || null })}
              aria-label="Изменён до"
            />
          </div>
        </div>
      )}
    </div>
  );
}

interface FilterPopoverProps extends FilterFieldsProps {
  /** Текст кнопки-триггера; без него — иконка в заголовке колонки. */
  label?: string;
  onReset: () => void;
}

/**
 * Поповер фильтров. Позиция считается по кнопке при открытии и рисуется
 * порталом: таблица сидит в контейнере с `overflow-auto`, и панель внутри
 * заголовка обрезалась бы.
 */
export function FilterPopover({ label, onReset, ...fieldsProps }: FilterPopoverProps) {
  const { filters } = fieldsProps;
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{
    left: number;
    top?: number;
    bottom?: number;
  } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const count = activeFilterCount(filters);

  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }

    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      const width = Math.min(PANEL_WIDTH, window.innerWidth - VIEWPORT_GAP * 2);
      const left = Math.max(
        VIEWPORT_GAP,
        Math.min(rect.right - width, window.innerWidth - width - VIEWPORT_GAP),
      );
      // Внизу у края экрана панель раскрывается вверх — иначе её нижняя
      // половина осталась бы за вьюпортом.
      const openUp = rect.bottom + PANEL_ESTIMATED_HEIGHT > window.innerHeight;
      setPosition(
        openUp
          ? { left, bottom: window.innerHeight - rect.top + 6 }
          : { left, top: rect.bottom + 6 },
      );
    }
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    // Позиция посчитана по кнопке: после прокрутки или ресайза она устареет.
    const close = (event: Event) => {
      if (
        panelRef.current &&
        event.target instanceof Node &&
        panelRef.current.contains(event.target)
      ) {
        return;
      }
      setOpen(false);
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);

  return (
    <>
      <span
        ref={triggerRef}
        className="inline-flex"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <Button
          type="button"
          variant={label ? "outline" : "ghost"}
          size={label ? "default" : "icon"}
          className={label ? undefined : "h-7 w-7"}
          onClick={toggle}
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-controls={open ? panelId : undefined}
          title="Фильтр"
        >
          <Filter className={cn(label ? "h-4 w-4" : "h-3.5 w-3.5", count > 0 && "text-primary")} />
          {label && <span className="ml-2">{label}</span>}
          {label && count > 0 && (
            <Badge variant="secondary" className="ml-2">
              {count}
            </Badge>
          )}
        </Button>
      </span>

      {open &&
        position &&
        createPortal(
          <div
            ref={panelRef}
            id={panelId}
            role="dialog"
            aria-label={label ?? "Фильтр колонки"}
            style={{ top: position.top, left: position.left }}
            className="fixed z-50 max-h-[70vh] w-80 overflow-y-auto rounded-md border bg-popover p-3 text-popover-foreground shadow-md"
          >
            <FilterFields {...fieldsProps} idPrefix={panelId} />

            <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3">
              <Button type="button" variant="ghost" size="sm" onClick={onReset}>
                Сбросить
              </Button>
              <Button type="button" size="sm" onClick={() => setOpen(false)}>
                Готово
              </Button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

interface Chip {
  key: string;
  label: string;
  /** Как снять ровно это условие. */
  without: Partial<CatalogFilters>;
}

function filterChips(filters: CatalogFilters): Chip[] {
  const chips: Chip[] = [];

  if (filters.name.trim()) {
    chips.push({ key: "name", label: `Артикул: ${filters.name.trim()}`, without: { name: "" } });
  }
  if (filters.description.trim()) {
    chips.push({
      key: "description",
      label: `Наименование: ${filters.description.trim()}`,
      without: { description: "" },
    });
  }
  if (filters.quantityFrom !== null || filters.quantityTo !== null) {
    const label =
      filters.quantityFrom !== null && filters.quantityTo !== null
        ? `Кол-во: ${filters.quantityFrom}–${filters.quantityTo}`
        : filters.quantityFrom !== null
          ? `Кол-во: от ${filters.quantityFrom}`
          : `Кол-во: до ${filters.quantityTo}`;
    chips.push({ key: "quantity", label, without: { quantityFrom: null, quantityTo: null } });
  }
  for (const length of [...filters.lengths].sort((a, b) => a - b)) {
    chips.push({
      key: `length-${length}`,
      label: `Длина: ${length} мм`,
      without: { lengths: new Set([...filters.lengths].filter((value) => value !== length)) },
    });
  }
  if (filters.notes.trim()) {
    chips.push({
      key: "notes",
      label: `Примечание: ${filters.notes.trim()}`,
      without: { notes: "" },
    });
  }
  if (filters.hasPhoto) {
    chips.push({ key: "has_photo", label: "С фото", without: { hasPhoto: false } });
  }
  if (filters.updatedFrom || filters.updatedTo) {
    const from = filters.updatedFrom ? formatDay(filters.updatedFrom) : "…";
    const to = filters.updatedTo ? formatDay(filters.updatedTo) : "…";
    chips.push({
      key: "updated_at",
      label: `Изменён: ${from}–${to}`,
      without: { updatedFrom: null, updatedTo: null },
    });
  }

  return chips;
}

interface FilterChipsProps {
  filters: CatalogFilters;
  onChange: (patch: Partial<CatalogFilters>) => void;
  onReset: () => void;
}

/** Активные фильтры общие для плитки и таблицы — чипы со снятием. */
export function CatalogFilterChips({ filters, onChange, onReset }: FilterChipsProps) {
  const chips = filterChips(filters);
  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="outline">Фильтров: {activeFilterCount(filters)}</Badge>
      {chips.map((chip) => (
        <Badge key={chip.key} variant="secondary" className="gap-1 pr-1">
          {chip.label}
          <button
            type="button"
            onClick={() => onChange(chip.without)}
            className="rounded-sm p-0.5 hover:bg-accent"
            title={`Снять: ${chip.label}`}
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      ))}
      <Button type="button" variant="ghost" size="sm" onClick={onReset}>
        <RotateCcw className="h-3.5 w-3.5" />
        Сбросить
      </Button>
    </div>
  );
}
