import { describe, expect, it, vi } from "vitest";
import { photoUrl } from "./photo";

describe("photoUrl", () => {
  it("путь без ведущего слэша превращается в /static/…", () => {
    expect(photoUrl("images/1010.jpg")).toBe("/static/images/1010.jpg");
  });

  it("готовый абсолютный путь не дублирует /static", () => {
    expect(photoUrl("/static/images/1010.jpg")).toBe("/static/images/1010.jpg");
  });

  it("разделители Windows нормализуются", () => {
    expect(photoUrl("images\\1010.jpg")).toBe("/static/images/1010.jpg");
  });

  it("пустой путь — нет фото", () => {
    expect(photoUrl(null)).toBeNull();
    expect(photoUrl("")).toBeNull();
  });

  it("внешний URL не переписывается и не версионируется", () => {
    expect(photoUrl("https://cdn.example.com/1010.jpg", "v1")).toBe(
      "https://cdn.example.com/1010.jpg",
    );
  });

  it("версия берётся только из файла, а не из текущего времени", () => {
    // Иначе каждый рендер даёт новый URL, и браузер заново качает превью:
    // киоск показывает дашборд круглосуточно, а файл при этом не менялся.
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-11-09T10:00:00Z"));
      const first = photoUrl("images/1010.jpg", "1a2b-3c4d");

      vi.setSystemTime(new Date("2026-11-09T10:05:00Z"));
      const second = photoUrl("images/1010.jpg", "1a2b-3c4d");

      expect(first).toBe("/static/images/1010.jpg?v=1a2b-3c4d");
      expect(second).toBe(first);
    } finally {
      vi.useRealTimers();
    }
  });

  it("новая версия файла даёт новый URL", () => {
    const before = photoUrl("images/1010.jpg", "old-version");
    const after = photoUrl("images/1010.jpg", "new-version");

    expect(after).not.toBe(before);
  });

  it("без версии URL остаётся стабильным", () => {
    expect(photoUrl("images/1010.jpg", null)).toBe("/static/images/1010.jpg");
  });
});
