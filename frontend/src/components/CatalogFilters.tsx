import { useCallback, useRef, useState } from "react";
import { Filter, RotateCcw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AnchoredPanel, panelPosition, type PanelPosition } from "@/components/AnchoredPanel";
import { ColumnFilterBody } from "@/components/ColumnFilterBody";
import type { BoundColumn } from "@/hooks/useSortableColumnFilters";
import { hasActiveRange } from "@/lib/domain/columnFilters";
import type { ColumnFilterKind } from "@/lib/domain/columnSpecs";
import { cn } from "@/lib/utils";

// Фильтры общие для плитки и таблицы. В таблице их открывают заголовки
// колонок, в плитке — эта панель: тот же `ColumnFilterBody`, то же состояние,
// поэтому режим не меняет смысл фильтра.

interface FilterPanelColumn<Field extends string> {
  filterField?: Field;
  label: string;
  filterTitle?: string;
  filterKind?: ColumnFilterKind;
  valueLabel?: (value: string) => string;
  exactMatch?: boolean;
  multiSelect?: boolean;
}

interface CommonProps<Field extends string> {
  columns: ReadonlyArray<FilterPanelColumn<Field>>;
  bindColumn: (field: Field) => BoundColumn<Field>;
  filterCount: number;
  onReset: () => void;
}

function formatDay(value: string): string {
  if (!value) return "…";
  const [year, month, day] = value.split("-");
  if (!year || !month || !day) return value;
  return `${day}.${month}.${year}`;
}

function columnTitle(column: FilterPanelColumn<string>): string {
  return column.filterTitle ?? column.label;
}

export interface CatalogFilterPanelProps<Field extends string> extends CommonProps<Field> {
  values: Partial<Record<Field, string[]>>;
}

/** Кнопка «Фильтры» в тулбаре: в плитке заголовков колонок нет. */
export function CatalogFilterPanel<Field extends string>({
  columns,
  values,
  bindColumn,
  filterCount,
  onReset,
}: CatalogFilterPanelProps<Field>) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => setOpen(false), []);

  const toggle = useCallback(() => {
    if (open) {
      setOpen(false);
      return;
    }
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setPosition(panelPosition(rect, { width: window.innerWidth, height: window.innerHeight }));
    }
    setOpen(true);
  }, [open]);

  return (
    <>
      <Button
        ref={triggerRef}
        type="button"
        variant="outline"
        onClick={toggle}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Фильтры"
      >
        <Filter className={cn("h-4 w-4 md:mr-2", filterCount > 0 && "text-primary")} />
        <span className="hidden md:inline">Фильтры</span>
        {filterCount > 0 && (
          <Badge variant="secondary" className="ml-2">
            {filterCount}
          </Badge>
        )}
      </Button>

      <AnchoredPanel
        open={open}
        position={position}
        anchorRef={triggerRef}
        ariaLabel="Фильтры"
        onClose={close}
      >
        <div className="space-y-3">
          {columns.map((column) => {
            const field = column.filterField;
            if (!field) return null;
            const bound = bindColumn(field);
            const kind = column.filterKind ?? "values";
            return (
              <section key={field} className="space-y-1.5">
                <h3 className="text-xs font-semibold text-foreground">{columnTitle(column)}</h3>
                <ColumnFilterBody
                  field={field}
                  title={columnTitle(column)}
                  kind={kind}
                  values={values[field] ?? []}
                  valueLabel={column.valueLabel}
                  selectedValues={bound.selectedValues}
                  onFilterChange={bound.onFilterChange}
                  searchQuery={bound.searchQuery}
                  onSearchChange={bound.onSearchChange}
                  multiSelect={column.multiSelect ?? true}
                  searchFiltersTable={kind === "values" && column.exactMatch !== true}
                  range={bound.range}
                  onRangeChange={bound.onRangeChange}
                  showActions={false}
                  onDone={close}
                />
              </section>
            );
          })}
        </div>

        <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onReset}
            disabled={filterCount === 0}
          >
            Сбросить
          </Button>
          <Button type="button" size="sm" onClick={close}>
            Готово
          </Button>
        </div>
      </AnchoredPanel>
    </>
  );
}

export type CatalogFilterChipsProps<Field extends string> = CommonProps<Field>;

interface Chip {
  key: string;
  label: string;
  clear: () => void;
}

/** Активные фильтры — чипами со снятием; одинаково в плитке и таблице. */
export function CatalogFilterChips<Field extends string>({
  columns,
  bindColumn,
  filterCount,
  onReset,
}: CatalogFilterChipsProps<Field>) {
  const chips: Chip[] = [];

  for (const column of columns) {
    const field = column.filterField;
    if (!field) continue;
    const bound = bindColumn(field);
    const title = column.label;
    const valueLabel = (value: string) => (column.valueLabel ? column.valueLabel(value) : value);

    if (bound.searchQuery.trim()) {
      chips.push({
        key: `query-${field}`,
        label: `${title}: ${bound.searchQuery.trim()}`,
        clear: () => bound.onSearchChange(field, ""),
      });
    }

    const values = [...bound.selectedValues].sort((left, right) =>
      column.valueLabel
        ? valueLabel(left).localeCompare(valueLabel(right), "ru")
        : left.localeCompare(right, "ru"),
    );
    for (const value of values) {
      chips.push({
        key: `value-${field}-${value}`,
        label: `${title}: ${valueLabel(value)}`,
        clear: () =>
          bound.onFilterChange(
            field,
            new Set([...bound.selectedValues].filter((candidate) => candidate !== value)),
          ),
      });
    }

    if (hasActiveRange(bound.range)) {
      const kind = column.filterKind ?? "values";
      const format = (value: string) => (kind === "dateRange" ? formatDay(value) : value || "…");
      chips.push({
        key: `range-${field}`,
        label: `${title}: ${format(bound.range.from)}–${format(bound.range.to)}`,
        clear: () => bound.onRangeChange(field, { from: "", to: "" }),
      });
    }
  }

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="outline">Фильтров: {filterCount}</Badge>
      {chips.map((chip) => (
        <Badge key={chip.key} variant="secondary" className="gap-1 pr-1">
          {chip.label}
          <button
            type="button"
            onClick={chip.clear}
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
