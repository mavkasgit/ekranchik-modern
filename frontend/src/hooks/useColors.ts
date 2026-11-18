import { useQuery } from "@tanstack/react-query";
import { colorsApi } from "@/api/colors";
import { COLORS_KEY } from "@/lib/queryKeys";

/** Справочник меняется только при синке с KTM: лишние запросы не нужны. */
const COLORS_STALE_TIME = 30 * 60 * 1000;

/**
 * Справочник цветов из `GET /api/colors`. Он меняется редко, поэтому кэш живёт
 * долго и не тянется по таймеру. Пока запрос грузится или упал, данных нет:
 * цвета показываются как неизвестные (серые, с аббревиатурой), экран живёт.
 */
export function useColors() {
  return useQuery({
    queryKey: COLORS_KEY,
    queryFn: colorsApi.getAll,
    staleTime: COLORS_STALE_TIME,
  });
}
