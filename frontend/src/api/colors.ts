import { api } from "./client";
import type { ColorSpec } from "@/lib/domain/color";

/**
 * Строка ответа `GET /api/colors` (тикет 0022). Панели нужны код, название,
 * hex и готовая подпись; остальные поля справочника — забота синка и правки.
 */
interface ColorRow {
  id: number;
  code: string | null;
  name: string;
  hex: string;
  /** Колонка необязательная: у строки из синка подписи может не быть. */
  abbreviation: string | null;
  operation_code: string | null;
  source: "ktm" | "local";
  updated_at: string;
}

// Цвета только читаются: справочник ведёт бэкенд, создания и удаления
// через API в этом срезе нет.
export const colorsApi = {
  getAll: async (): Promise<ColorSpec[]> => {
    const { data } = await api.get<ColorRow[]>("/colors");
    return data.map((color) => ({
      code: color.code,
      name: color.name,
      hex: color.hex,
      // Пустая подпись включает запасной путь colorLabel: код или первые буквы.
      abbreviation: color.abbreviation ?? "",
    }));
  },
};
