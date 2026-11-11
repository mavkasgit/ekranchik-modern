import { describe, expect, it } from "vitest";
import { assignBookRole, buildBookRows, renameBookPath } from "./bookRoles";

describe("buildBookRows", () => {
  it("основная и запасная идут первыми и получают свои роли", () => {
    expect(buildBookRows("\\\\srv\\main.xlsm", "\\\\srv\\reserve.xlsm", [])).toEqual([
      { path: "\\\\srv\\main.xlsm", role: "main" },
      { path: "\\\\srv\\reserve.xlsm", role: "reserve" },
    ]);
  });

  it("последние пути добавляются без роли", () => {
    expect(buildBookRows("a", null, ["a", "b"])).toEqual([
      { path: "a", role: "main" },
      { path: "b", role: "none" },
    ]);
  });

  it("дубли и пустые пути не показываются", () => {
    expect(buildBookRows("a", "a", ["a", "  ", "b"])).toEqual([
      { path: "a", role: "main" },
      { path: "b", role: "none" },
    ]);
  });
});

describe("assignBookRole", () => {
  it("роль переезжает: прежняя основная становится обычным путём", () => {
    const rows = buildBookRows("a", "b", ["c"]);
    expect(assignBookRole(rows, "c", "main")).toEqual([
      { path: "a", role: "none" },
      { path: "b", role: "reserve" },
      { path: "c", role: "main" },
    ]);
  });

  it("снятие роли не трогает остальные", () => {
    const rows = buildBookRows("a", "b", []);
    expect(assignBookRole(rows, "b", "none")).toEqual([
      { path: "a", role: "main" },
      { path: "b", role: "none" },
    ]);
  });
});

describe("renameBookPath", () => {
  it("путь правится на месте, роль сохраняется", () => {
    const rows = buildBookRows("a", "b", []);
    expect(renameBookPath(rows, "a", "c")[0]).toEqual({ path: "c", role: "main" });
  });

  it("существующий путь не дублируется", () => {
    const rows = buildBookRows("a", "b", []);
    expect(renameBookPath(rows, "a", "b")).toEqual(rows);
  });

  it("пустой путь не затирает прежний", () => {
    const rows = buildBookRows("a", "b", []);
    expect(renameBookPath(rows, "a", "   ")).toEqual(rows);
  });
});
