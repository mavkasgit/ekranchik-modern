import { keepPreviousData, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { catalogApi } from "@/api/catalog";
import { catalogKeys } from "@/lib/queryKeys";
import { notesPayload } from "@/lib/domain/catalogNotes";
import type { Profile } from "@/types/profile";

export function useCatalogAll() {
  return useQuery({
    queryKey: catalogKeys.list,
    queryFn: () => catalogApi.getAll(),
    // Ручное обновление не должно мигать скелетоном: пока грузится новая
    // копия списка, экран показывает предыдущую.
    placeholderData: keepPreviousData,
    staleTime: 30000, // 30 seconds - prevent unnecessary refetches
  });
}

/**
 * Единственная запись витрины. Оптимистично подставляет примечание в список,
 * при ошибке возвращает прежнее значение, в конце сверяется с сервером.
 */
export function useUpdateNotes() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) => catalogApi.updateNotes(id, notes),
    onMutate: async ({ id, notes }) => {
      await queryClient.cancelQueries({ queryKey: catalogKeys.root });
      const previous = queryClient.getQueriesData<Profile[]>({ queryKey: catalogKeys.root });
      const value = notesPayload(notes).notes;

      queryClient.setQueriesData<Profile[]>({ queryKey: catalogKeys.root }, (list) =>
        list?.map((profile) => (profile.id === id ? { ...profile, notes: value } : profile)),
      );

      return { previous };
    },
    onError: (_error, _variables, context) => {
      for (const [queryKey, data] of context?.previous ?? []) {
        queryClient.setQueryData(queryKey, data);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: catalogKeys.root });
    },
  });
}
