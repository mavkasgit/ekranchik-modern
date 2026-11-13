// Тело PATCH /catalog/{id}/notes. Пустая строка и одни пробелы означают
// «стереть примечание», а не записать пустую строку: на бэкенд уходит null.
export function notesPayload(notes: string): { notes: string | null } {
  return { notes: notes.trim() ? notes : null };
}
