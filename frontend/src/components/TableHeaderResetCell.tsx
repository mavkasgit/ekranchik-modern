import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// Сброс всех фильтров — в правом верхнем углу таблицы, как в ktm2000.
// Кнопка живёт в шапке, а не в тулбаре: оператор, отфильтровавший таблицу,
// ищет сброс там же, где ставил условия.

export interface TableHeaderResetCellProps {
  hasActiveFilters: boolean;
  onReset: () => void;
  className?: string;
}

export function TableHeaderResetCell({
  hasActiveFilters,
  onReset,
  className,
}: TableHeaderResetCellProps) {
  return (
    <button
      type="button"
      onClick={onReset}
      title="Сбросить фильтры"
      aria-label="Сбросить фильтры"
      disabled={!hasActiveFilters}
      className={cn(
        "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        hasActiveFilters
          ? "bg-primary text-primary-foreground hover:bg-primary/90"
          : "text-muted-foreground/45 hover:bg-accent hover:text-muted-foreground",
        className,
      )}
    >
      <X className="h-3 w-3" strokeWidth={hasActiveFilters ? 2.5 : 1.75} />
    </button>
  );
}
