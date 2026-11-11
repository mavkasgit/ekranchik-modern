import { describe, expect, it } from "vitest";
import { pathHint } from "./bookPath";

describe("pathHint", () => {
  it("показывает последние два сегмента: имена книг совпадают, папки разные", () => {
    expect(pathHint("\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm")).toBe(
      "Оператор\\Учет КПЗ 2026.xlsm",
    );
    expect(pathHint("C:\\testdata\\Учет КПЗ 2026.xlsm")).toBe("testdata\\Учет КПЗ 2026.xlsm");
  });
});
