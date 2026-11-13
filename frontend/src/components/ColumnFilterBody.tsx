import { useId } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  type RangeFilter,
  hasActiveRange,
  sortByPartialSearchMatch,
} from "@/lib/domain/columnFilters";
import type { ColumnFilterKind } from "@/lib/domain/columnSpecs";
import { cn } from "@/lib/utils";

// Содержимое поповера одной колонки. Один компонент на шапку таблицы и на
// панель «Фильтры» в плитке: набор контролов и правила выбора не могут
// разойтись между режимами.

export interface ColumnFilterBodyProps<Field extends string> {
  field: Field;
  title: string;
  kind: ColumnFilterKind;
  values?: readonly string[];
  valueLabel?: (value: string) => string;
  selectedValues: Set<string>;
  onFilterChange: (field: Field, values: Set<string>) => void;
  searchQuery: string;
  onSearchChange: (field: Field, query: string) => void;
  multiSelect?: boolean;
  /** Текст в поповере фильтрует строки, а не только список значений. */
  searchFiltersTable?: boolean;
  range: RangeFilter;
  onRangeChange: (field: Field, patch: Partial<RangeFilter>) => void;
  showActions?: boolean;
  onDone: () => void;
  autoFocus?: boolean;
}

function toggleValue(selected: Set<string>, value: string, checked: boolean): Set<string> {
  const next = new Set(selected);
  if (checked) next.add(value);
  else next.delete(value);
  return next;
}

function ValueFilterBody<Field extends string>({
  field,
  title,
  values = [],
  valueLabel,
  selectedValues,
  onFilterChange,
  searchQuery,
  onSearchChange,
  multiSelect = true,
  searchFiltersTable = true,
  showActions = true,
  onDone,
  autoFocus = false,
}: ColumnFilterBodyProps<Field>) {
  const id = useId();
  const display = (value: string) => (valueLabel ? valueLabel(value) : value);
  const hasSearch = searchQuery.trim() !== "";
  const hasSelected = selectedValues.size > 0;
  const hasFilter = hasSearch || hasSelected;
  const list = sortByPartialSearchMatch(values, searchQuery, display);
  const showList = !(searchFiltersTable && hasSearch);

  const toggle = (value: string) => {
    if (!multiSelect) {
      onFilterChange(field, selectedValues.has(value) ? new Set() : new Set([value]));
      return;
    }
    onFilterChange(field, toggleValue(selectedValues, value, !selectedValues.has(value)));
  };

  return (
    <div className="space-y-2">
      <Label htmlFor={`${id}-search`} className="sr-only">
        Поиск по значениям: {title}
      </Label>
      <Input
        id={`${id}-search`}
        placeholder="Поиск..."
        value={searchQuery}
        autoFocus={autoFocus}
        onChange={(event) => {
          const next = event.target.value;
          onSearchChange(field, next);
          // Непустой текст забирает контрол себе: выбранное значение, которое
          // в запрос уже не уйдёт, оставлять нельзя — в шапке был бы фильтр,
          // которого нет. У точной колонки поиск сужает только список.
          if (searchFiltersTable && next.trim() && selectedValues.size > 0) {
            onFilterChange(field, new Set());
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            onDone();
          }
        }}
        className="h-8 text-sm"
      />

      {showList ? (
        <>
          {multiSelect && list.length > 0 && (
            <div className="flex items-center justify-between px-1">
              <button
                type="button"
                className="text-xs text-primary hover:underline"
                onClick={() => onFilterChange(field, new Set(list))}
              >
                Выбрать все
              </button>
              <span className="text-[10px] text-muted-foreground">
                Выбрано: {selectedValues.size}
              </span>
            </div>
          )}
          <div className="max-h-52 overflow-y-auto rounded border">
            {list.length === 0 && (
              <p className="px-2 py-2 text-xs text-muted-foreground">Нет значений</p>
            )}
            {list.map((value) => {
              const isSelected = selectedValues.has(value);
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={isSelected}
                  data-filter-value={value}
                  className={cn(
                    "block w-full truncate px-2 py-1 text-left text-xs transition-colors",
                    isSelected
                      ? "bg-primary text-primary-foreground"
                      : "text-foreground hover:bg-accent",
                  )}
                  onClick={() => toggle(value)}
                >
                  {display(value)}
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <p className="px-1 text-[10px] text-muted-foreground">
          Список значений скрыт, пока идёт поиск. Сбросить — «Сбросить колонку».
        </p>
      )}

      {showActions && (
        <div className="flex items-center justify-end gap-1 border-t pt-2">
          {hasFilter && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => {
                onSearchChange(field, "");
                onFilterChange(field, new Set());
              }}
            >
              <X className="mr-1 h-3 w-3" />
              Сбросить колонку
            </Button>
          )}
          <Button type="button" size="sm" className="h-7 text-xs" onClick={onDone}>
            Готово
          </Button>
        </div>
      )}
    </div>
  );
}

function RangeFilterBody<Field extends string>({
  field,
  title,
  kind,
  range,
  onRangeChange,
  showActions = true,
  onDone,
}: ColumnFilterBodyProps<Field>) {
  const id = useId();
  const dateKind = kind === "dateRange";
  const active = hasActiveRange(range);

  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        <Label className="text-xs">{title}</Label>
        <div className="flex items-center gap-2">
          <Input
            id={`${id}-from`}
            type={dateKind ? "date" : "number"}
            inputMode={dateKind ? undefined : "numeric"}
            min={dateKind ? undefined : 0}
            placeholder={dateKind ? undefined : "от"}
            aria-label={`${title}: от`}
            value={range.from}
            onChange={(event) => onRangeChange(field, { from: event.target.value })}
            onKeyDown={(event) => {
              if (event.key === "Enter") onDone();
            }}
            className="h-8 text-sm"
          />
          <span className="text-muted-foreground">—</span>
          <Input
            id={`${id}-to`}
            type={dateKind ? "date" : "number"}
            inputMode={dateKind ? undefined : "numeric"}
            min={dateKind ? undefined : 0}
            placeholder={dateKind ? undefined : "до"}
            aria-label={`${title}: до`}
            value={range.to}
            onChange={(event) => onRangeChange(field, { to: event.target.value })}
            onKeyDown={(event) => {
              if (event.key === "Enter") onDone();
            }}
            className="h-8 text-sm"
          />
        </div>
      </div>

      {showActions && (
        <div className="flex items-center justify-end gap-1 border-t pt-2">
          {active && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onRangeChange(field, { from: "", to: "" })}
            >
              <X className="mr-1 h-3 w-3" />
              Сбросить колонку
            </Button>
          )}
          <Button type="button" size="sm" className="h-7 text-xs" onClick={onDone}>
            Готово
          </Button>
        </div>
      )}
    </div>
  );
}

export function ColumnFilterBody<Field extends string>(props: ColumnFilterBodyProps<Field>) {
  const kind = props.kind;
  if (kind === "range" || kind === "dateRange") {
    return <RangeFilterBody {...props} />;
  }
  return <ValueFilterBody {...props} />;
}
