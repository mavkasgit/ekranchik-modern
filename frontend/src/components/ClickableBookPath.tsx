// Путь к книге учёта как одно кликабельное поле.
//
// В диалоге книг оператор видит полный путь; карандаш и подпись «изменить»
// видны всегда, а не только при наведении: на киоске мышью водят редко, и
// «поле выглядит текстом» — главная причина, по которой путь не правили.

import { useEffect, useRef, useState } from "react";
import { Pencil } from "lucide-react";

export type BookPathTone = "main" | "reserve" | "neutral";

const TONES: Record<BookPathTone, { idle: string; edit: string }> = {
  main: {
    idle: "border-emerald-500/50 bg-emerald-50/40 hover:border-emerald-600 hover:bg-emerald-50 dark:bg-emerald-500/10 dark:hover:bg-emerald-500/15",
    edit: "border-emerald-600 ring-emerald-500/20",
  },
  reserve: {
    idle: "border-amber-500/50 bg-amber-50/40 hover:border-amber-600 hover:bg-amber-50 dark:bg-amber-500/10 dark:hover:bg-amber-500/15",
    edit: "border-amber-600 ring-amber-500/20",
  },
  neutral: {
    idle: "border-border bg-background hover:border-slate-400 hover:bg-muted/60",
    edit: "border-slate-500 ring-slate-400/20",
  },
};

export function ClickableBookPath({
  value,
  onChange,
  tone = "neutral",
  placeholder = "Нажмите, чтобы указать путь",
}: {
  value: string;
  onChange: (next: string) => void;
  tone?: BookPathTone;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);
  const toneStyles = TONES[tone];

  // Фокус и выделение всего пути: чаще всего меняют имя книги или папку,
  // а не набирают путь заново.
  useEffect(() => {
    if (!editing) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    onChange(draft.trim());
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
          if (event.key === "Escape") {
            setDraft(value);
            setEditing(false);
          }
        }}
        placeholder={placeholder}
        className={`w-full rounded-lg border-2 px-3 font-mono text-xs outline-none ring-4 ${toneStyles.edit} min-h-12 py-2`}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => {
        setDraft(value);
        setEditing(true);
      }}
      title="Нажмите, чтобы изменить путь"
      className={`group flex w-full cursor-text items-center gap-3 rounded-lg border-2 border-dashed px-3 py-2 text-left transition-colors min-h-12 ${toneStyles.idle}`}
    >
      <span
        className={`min-w-0 flex-1 break-all font-mono text-xs ${
          value ? "text-slate-800 dark:text-slate-200" : "text-muted-foreground"
        }`}
      >
        {value || placeholder}
      </span>
      <span className="flex shrink-0 items-center gap-1.5 rounded-md bg-background/80 px-2 py-1 text-[10px] font-semibold text-slate-600 shadow-sm group-hover:text-slate-900 dark:text-slate-300 dark:group-hover:text-white">
        <Pencil className="h-3.5 w-3.5" />
        изменить
      </span>
    </button>
  );
}
