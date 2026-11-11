import { describe, expect, it } from "vitest";
import { parseRecentPaths, RECENT_PATHS_LIMIT, rememberRecentPath } from "./recentPaths";

describe("rememberRecentPath", () => {
  it("новый путь встаёт первым", () => {
    expect(rememberRecentPath(["\\\\srv\\book\\b.xlsm"], "C:\\testdata\\a.xlsm")).toEqual([
      "C:\\testdata\\a.xlsm",
      "\\\\srv\\book\\b.xlsm",
    ]);
  });

  it("держится не больше трёх путей", () => {
    let paths: string[] = [];
    for (const path of ["a", "b", "c", "d"]) paths = rememberRecentPath(paths, path);

    expect(paths).toHaveLength(RECENT_PATHS_LIMIT);
    expect(paths).toEqual(["d", "c", "b"]);
  });

  it("повторный путь не дублируется, а поднимается наверх", () => {
    expect(rememberRecentPath(["a", "b", "c"], "c")).toEqual(["c", "a", "b"]);
  });

  it("пробелы вокруг пути не создают второй такой же путь", () => {
    expect(rememberRecentPath(["C:\\a.xlsm"], "  C:\\a.xlsm  ")).toEqual(["C:\\a.xlsm"]);
  });

  it("пустой путь память не меняет", () => {
    expect(rememberRecentPath(["a", "b"], "   ")).toEqual(["a", "b"]);
  });
});

describe("parseRecentPaths", () => {
  it("пустое и битое значение — пустая память", () => {
    expect(parseRecentPaths(null)).toEqual([]);
    expect(parseRecentPaths("")).toEqual([]);
    expect(parseRecentPaths("not json")).toEqual([]);
    expect(parseRecentPaths('{"path":"a"}')).toEqual([]);
  });

  it("нестроковые и пустые элементы отбрасываются", () => {
    expect(parseRecentPaths('["a", 1, null, "  ", "b"]')).toEqual(["a", "b"]);
  });

  it("порядок хранения сохраняется", () => {
    expect(parseRecentPaths('["newest", "older", "oldest"]')).toEqual([
      "newest",
      "older",
      "oldest",
    ]);
  });
});
