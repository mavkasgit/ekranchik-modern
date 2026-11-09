import { describe, expect, it, vi } from "vitest";
import { photoUrl } from "./photo";

describe("photoUrl", () => {
  it("путь без ведущего слэша превращается в /static/…", () => {
    expect(photoUrl("images/1010.jpg")).toBe("/static/images/1010.jpg");
  });

  it("готовый абсолютный путь не дублирует /static", () => {
    expect(photoUrl("/static/images/1010.jpg")).toBe("/static/images/1010.jpg");
  });

  it("пустой путь — нет фото", () => {
    expect(photoUrl(null)).toBeNull();
    expect(photoUrl("")).toBeNull();
  });

  it("версия берётся только из updated_at, а не из текущего времени", () => {
    // Иначе каждый рендер даёт новый URL, и браузер заново качает превью:
    // киоск показывает дашборд круглосуточно, а файл при этом не менялся.
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-11-09T10:00:00Z"));
      const first = photoUrl("images/1010.jpg", "2026-11-01T09:00:00");

      vi.setSystemTime(new Date("2026-11-09T10:05:00Z"));
      const second = photoUrl("images/1010.jpg", "2026-11-01T09:00:00");

      expect(first).toBe("/static/images/1010.jpg?v=2026-11-01T09:00:00");
      expect(second).toBe(first);
    } finally {
      vi.useRealTimers();
    }
  });

  it("новое updated_at даёт новый URL", () => {
    const before = photoUrl("images/1010.jpg", "2026-11-01T09:00:00");
    const after = photoUrl("images/1010.jpg", "2026-11-02T09:00:00");

    expect(after).not.toBe(before);
  });
});
