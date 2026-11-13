import { api } from "./client";
import { notesPayload } from "@/lib/domain/catalogNotes";
import type { Profile, ProfileSearchResult } from "@/types/profile";

// Витрина: каталог только читается. Единственная запись — примечание.
export const catalogApi = {
  // Остаётся как API поиска; витрина фильтрует список на клиенте.
  search: async (query: string, limit = 50): Promise<ProfileSearchResult[]> => {
    const { data } = await api.get<ProfileSearchResult[]>("/catalog", {
      params: { q: query, limit },
    });
    return data;
  },

  getAll: async (limit = 500): Promise<Profile[]> => {
    const { data } = await api.get<Profile[]>("/catalog/all", {
      params: { limit },
    });
    return data;
  },

  getProfile: async (name: string): Promise<Profile> => {
    const { data } = await api.get<Profile>(`/catalog/${encodeURIComponent(name)}`);
    return data;
  },

  updateNotes: async (id: number, notes: string): Promise<Profile> => {
    const { data } = await api.patch<Profile>(`/catalog/${id}/notes`, notesPayload(notes));
    return data;
  },
};
