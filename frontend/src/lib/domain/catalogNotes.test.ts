import { describe, expect, it } from "vitest";
import { notesPayload } from "./catalogNotes";

// Примечание — единственное поле каталога, которое пишет киоск. Пустой текст
// и одни пробелы означают «стереть»: на бэкенд уходит null, а не "".
describe("notesPayload", () => {
  it("непустое примечание уходит без изменений", () => {
    expect(notesPayload("Аналог-ЮП-3168")).toEqual({ notes: "Аналог-ЮП-3168" });
  });

  it("пустая строка очищает примечание", () => {
    expect(notesPayload("")).toEqual({ notes: null });
  });

  it("пробелы и переводы строк — тоже очистка", () => {
    expect(notesPayload("   \n\t  ")).toEqual({ notes: null });
  });
});
