import { useCallback, useMemo, useState } from "react";
import {
  type ColumnFilterState,
  type RangeFilter,
  EMPTY_RANGE,
  emptyColumnFilterState,
  hasActiveColumnFilters,
  columnFilterCount,
} from "@/lib/domain/columnFilters";
import { type ColumnSpec, buildColumnFilterPredicate } from "@/lib/domain/columnSpecs";

/**
 * Состояние фильтров колонок и привязка к конкретной колонке.
 *
 * Три карты — значения, текст и диапазоны — живут вместе, потому что сброс
 * обязан снимать всё, а не только то, что понимает текущий вид. Экран не
 * собирает их руками: `bindColumn` отдаёт готовый набор пропсов для шапки и
 * поповера.
 */

const EMPTY_SET: Set<string> = new Set<string>();

export interface BoundColumn<Field extends string> {
  searchQuery: string;
  selectedValues: Set<string>;
  onSearchChange: (field: Field, query: string) => void;
  onFilterChange: (field: Field, values: Set<string>) => void;
  range: RangeFilter;
  onRangeChange: (field: Field, patch: Partial<RangeFilter>) => void;
}

export function useSortableColumnFilters<Field extends string>(
  initial: ColumnFilterState<Field> | (() => ColumnFilterState<Field>) = emptyColumnFilterState,
) {
  const [state, setState] = useState<ColumnFilterState<Field>>(initial);

  const onFilterChange = useCallback((field: Field, values: Set<string>) => {
    setState((current) => ({ ...current, filters: { ...current.filters, [field]: values } }));
  }, []);

  const onSearchChange = useCallback((field: Field, query: string) => {
    setState((current) => ({ ...current, queries: { ...current.queries, [field]: query } }));
  }, []);

  const onRangeChange = useCallback((field: Field, patch: Partial<RangeFilter>) => {
    setState((current) => ({
      ...current,
      ranges: {
        ...current.ranges,
        [field]: { ...(current.ranges[field] ?? EMPTY_RANGE), ...patch },
      },
    }));
  }, []);

  const resetColumnFilters = useCallback(() => {
    setState(emptyColumnFilterState<Field>());
  }, []);

  const bindColumn = useCallback(
    (field: Field): BoundColumn<Field> => ({
      searchQuery: state.queries[field] ?? "",
      selectedValues: state.filters[field] ?? EMPTY_SET,
      onSearchChange,
      onFilterChange,
      range: state.ranges[field] ?? EMPTY_RANGE,
      onRangeChange,
    }),
    [state, onSearchChange, onFilterChange, onRangeChange],
  );

  const buildFilterPredicate = useCallback(
    <T, SortField extends string>(columns: ReadonlyArray<ColumnSpec<Field, SortField, T>>) =>
      buildColumnFilterPredicate(state, columns),
    [state],
  );

  const filterCount = useMemo(() => columnFilterCount(state), [state]);

  return {
    state,
    filterCount,
    hasActiveFilters: hasActiveColumnFilters(state),
    bindColumn,
    buildFilterPredicate,
    resetColumnFilters,
  };
}
