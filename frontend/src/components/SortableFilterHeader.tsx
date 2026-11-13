import { useCallback, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { AnchoredPanel, panelPosition, type PanelPosition } from "@/components/AnchoredPanel";
import { ColumnFilterBody } from "@/components/ColumnFilterBody";
import type { RangeFilter } from "@/lib/domain/columnFilters";
import type { ColumnFilterKind } from "@/lib/domain/columnSpecs";
import type { SortConfig } from "@/lib/domain/tableQuery";
import { cn } from "@/lib/utils";

// Заголовок колонки с сортировкой и фильтром — как в ktm2000:
// - клик по подписи открывает поповер фильтра (поиск + список значений);
// - клик по иконке сортирует и показывает приоритет мультисортировки;
// - пустая колонка остаётся текстом, без кнопок в никуда.

export interface SortableFilterHeaderProps<Field extends string, SortField extends string = Field> {
  label: string;
  /** Нет — колонка не фильтруется. */
  filterField?: Field;
  /** Нет — колонка не сортируется. */
  sortField?: SortField;
  filterTitle?: string;
  filterKind?: ColumnFilterKind;
  values?: readonly string[];
  valueLabel?: (value: string) => string;
  exactMatch?: boolean;
  multiSelect?: boolean;
  searchQuery?: string;
  selectedValues?: Set<string>;
  onSearchChange?: (field: Field, query: string) => void;
  onFilterChange?: (field: Field, values: Set<string>) => void;
  range?: RangeFilter;
  onRangeChange?: (field: Field, patch: Partial<RangeFilter>) => void;
  sortConfigs?: readonly SortConfig<SortField>[];
  onSortChange?: (field: SortField) => void;
}

const EMPTY_SET: Set<string> = new Set<string>();
const EMPTY_RANGE: RangeFilter = { from: "", to: "" };

export function SortableFilterHeader<Field extends string, SortField extends string = Field>({
  label,
  filterField,
  sortField,
  filterTitle,
  filterKind,
  values = [],
  valueLabel,
  exactMatch = false,
  multiSelect = true,
  searchQuery = "",
  selectedValues = EMPTY_SET,
  onSearchChange,
  onFilterChange,
  range = EMPTY_RANGE,
  onRangeChange,
  sortConfigs = [],
  onSortChange,
}: SortableFilterHeaderProps<Field, SortField>) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => setOpen(false), []);

  const toggleFilter = useCallback(() => {
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

  const activeSort = sortField
    ? sortConfigs.find((config) => config.field === sortField)
    : undefined;
  const sortPriority = activeSort ? sortConfigs.indexOf(activeSort) + 1 : null;
  const sortOrderLabel = activeSort
    ? activeSort.order === "asc"
      ? "по возрастанию"
      : "по убыванию"
    : "не задана";
  const sortPriorityLabel =
    sortPriority !== null && sortConfigs.length > 1
      ? `, приоритет ${sortPriority} из ${sortConfigs.length}`
      : "";
  const sortAriaLabel = `${label}, сортировка ${sortOrderLabel}${sortPriorityLabel}`;

  const hasSearch = searchQuery.trim() !== "";
  const hasSelected = selectedValues.size > 0;
  const hasFilter = hasSearch || hasSelected;
  const kind = filterKind ?? "values";
  const title = filterTitle ?? label;

  return (
    <div className="flex min-w-0 max-w-full items-center gap-1 text-xs">
      {filterField ? (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggleFilter}
          aria-expanded={open}
          aria-haspopup="dialog"
          title={`Фильтр: ${label}`}
          className={cn(
            "flex min-w-0 items-center rounded-sm text-left font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            hasFilter && "gap-1",
            activeSort && "text-foreground",
          )}
        >
          <span className="truncate">{label}</span>
          {hasFilter && (
            <span aria-hidden="true" className="shrink-0">
              <span
                className={cn(
                  "inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-full px-0.5 text-[9px] font-bold",
                  hasSearch ? "bg-primary/15 text-primary" : "bg-primary text-primary-foreground",
                )}
              >
                {hasSearch ? <Search className="h-2.5 w-2.5" /> : selectedValues.size}
              </span>
            </span>
          )}
        </button>
      ) : (
        <span className="inline-flex min-w-0 items-center gap-1 font-medium text-muted-foreground">
          <span className="truncate">{label}</span>
        </span>
      )}

      {sortField && (
        <button
          type="button"
          onClick={() => onSortChange?.(sortField)}
          aria-label={sortAriaLabel}
          aria-pressed={activeSort ? "true" : "false"}
          data-sort-order={activeSort?.order ?? "none"}
          data-sort-priority={sortPriority ?? undefined}
          data-sort-field={sortField}
          className={cn(
            "inline-flex shrink-0 items-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            activeSort && "text-foreground",
          )}
        >
          {activeSort?.order === "asc" ? (
            <ArrowUp className="h-3.5 w-3.5" />
          ) : activeSort?.order === "desc" ? (
            <ArrowDown className="h-3.5 w-3.5" />
          ) : (
            <ArrowUpDown className="h-3.5 w-3.5 opacity-50" />
          )}
          {sortPriority !== null && sortConfigs.length > 1 && (
            <span className="ml-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
              {sortPriority}
            </span>
          )}
        </button>
      )}

      {filterField && (
        <AnchoredPanel
          open={open}
          position={position}
          anchorRef={triggerRef}
          ariaLabel={`Фильтр колонки: ${label}`}
          onClose={close}
        >
          <ColumnFilterBody
            field={filterField}
            title={title}
            kind={kind}
            values={values}
            valueLabel={valueLabel}
            selectedValues={selectedValues}
            onFilterChange={onFilterChange ?? (() => {})}
            searchQuery={searchQuery}
            onSearchChange={onSearchChange ?? (() => {})}
            multiSelect={multiSelect}
            searchFiltersTable={kind === "values" && !exactMatch}
            range={range}
            onRangeChange={onRangeChange ?? (() => {})}
            onDone={close}
            autoFocus
          />
        </AnchoredPanel>
      )}
    </div>
  );
}
