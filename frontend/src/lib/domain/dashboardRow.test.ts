import { describe, expect, it } from "vitest";
import { describeHangerRow, isBlankRow, mergeHangerMeta } from "./dashboardRow";
import type { HangerData, ProfileInfo } from "@/types/dashboard";

function row(overrides: Partial<HangerData> = {}): HangerData {
  return {
    number: "777",
    date: "03.11.26",
    time: "12:00",
    client: "ТЕСТ-КЛИЕНТ",
    profile: "ТЕСТ-ПРОФИЛЬ",
    profiles_info: [],
    color: "золото",
    lamels_qty: 12,
    kpz_number: "777",
    material_type: "Пороги",
    ...overrides,
  };
}

describe("describeHangerRow: чем строка окрашена", () => {
  it("брак важнее клюшек и задержки", () => {
    const meaning = describeHangerRow(
      row({
        is_defect: true,
        material_type: "Клюшки",
        time_warning: "На линии 9.0ч при пороге 6ч",
        time_warning_code: "DELAY",
      }),
    );

    expect(meaning.tone).toBe("defect");
  });

  it("клюшки красят строку и когда вид материала обычный", () => {
    expect(describeHangerRow(row({ profile: "Клюшки 600" })).tone).toBe("sticks");
  });

  it("задержка — тон ожидания, когда брака и клюшек нет", () => {
    expect(describeHangerRow(row({ time_warning: "На линии 9.0ч" })).tone).toBe("delayed");
  });

  it("обычная строка чередует фон по индексу", () => {
    const even = describeHangerRow(row(), 0);
    const odd = describeHangerRow(row(), 1);

    expect(even.tone).toBe("plain");
    expect(even.className).not.toBe(odd.className);
  });
});

function profileInfo(name: string): ProfileInfo {
  return { name, processing: [], has_photo: true };
}

describe("describeHangerRow: профиль строки", () => {
  it("пустой профиль у клюшек читается словом", () => {
    for (const empty of ["", "—", "   "]) {
      expect(describeHangerRow(row({ material_type: "Клюшки", profile: empty })).profileLabel).toBe(
        "Клюшки",
      );
    }
  });

  it("плюсы в профиле разделяются пробелом", () => {
    expect(describeHangerRow(row({ profile: "2020+1010" })).profileLabel).toBe("2020+ 1010");
  });

  it("совсем без профиля — прочерк", () => {
    expect(describeHangerRow(row({ profile: "" })).profileLabel).toBe("—");
  });
});

describe("describeHangerRow: сколько строк занимает подвес", () => {
  it("больше двух профилей — фото уходят на второй ряд", () => {
    const meaning = describeHangerRow(
      row({ profiles_info: [profileInfo("a"), profileInfo("b"), profileInfo("c")] }),
    );

    expect(meaning.photosBelow).toBe(true);
    expect(meaning.detailRow).toBe(true);
    expect(meaning.rowSpan).toBe(2);
  });

  it("два профиля остаются в первой строке", () => {
    const meaning = describeHangerRow(row({ profiles_info: [profileInfo("a"), profileInfo("b")] }));

    expect(meaning.photosBelow).toBe(false);
    expect(meaning.detailRow).toBe(false);
    expect(meaning.rowSpan).toBe(1);
  });

  it("бейдж причины тоже добавляет второй ряд", () => {
    const meaning = describeHangerRow(
      row({ time_warning: "На линии 9.0ч", time_warning_code: "DELAY" }),
    );

    expect(meaning.photosBelow).toBe(false);
    expect(meaning.detailRow).toBe(true);
    expect(meaning.rowSpan).toBe(2);
  });
});

describe("describeHangerRow: пометки оператору", () => {
  it("долгий проход помечается задержкой", () => {
    const badges = describeHangerRow(
      row({ time_warning: "На линии 9.0ч при пороге 6ч", time_warning_code: "DELAY" }),
    ).badges;

    expect(badges.map((badge) => badge.code)).toEqual(["DELAY"]);
    expect(badges[0].label).toBe("⚠ ЗАДЕРЖКА");
  });

  it("ошибка цикла помечается отдельным бейджем", () => {
    const badges = describeHangerRow(
      row({ time_warning_code: "CYCLE_ERROR", time_warning: "Нет открытого цикла" }),
    ).badges;

    expect(badges.map((badge) => badge.code)).toEqual(["CYCLE_ERROR"]);
    expect(badges[0].label).toBe("⚠ ОШИБКА");
  });

  it("брак виден бейджем рядом с причиной", () => {
    const badges = describeHangerRow(
      row({ is_defect: true, time_warning: "На линии 9.0ч", time_warning_code: "DELAY" }),
    ).badges;

    expect(badges.map((badge) => badge.code)).toEqual(["DELAY", "DEFECT"]);
    expect(badges[1].label).toContain("БРАК");
  });

  it("строка без книги не помечается: пустая строка читается сама", () => {
    expect(describeHangerRow(row({ time_warning_code: "NO_ROW" })).badges).toEqual([]);
  });

  it("неизвестный код не становится бейджем", () => {
    // «constructor» and «toString» are inherited object keys: a lookup through
    // `in` would turn them into a badge with an empty label.
    for (const code of ["", "constructor", "toString", "SOMETHING_NEW"]) {
      expect(describeHangerRow(row({ time_warning_code: code })).badges).toEqual([]);
    }
  });
});

describe("describeHangerRow: клюшки", () => {
  it("клюшки видны флагом, а не сравнением подписи", () => {
    expect(describeHangerRow(row({ material_type: "Клюшки", profile: "" })).sticks).toBe(true);
    expect(describeHangerRow(row({ profile: "Клюшки 600" })).sticks).toBe(true);
    expect(describeHangerRow(row()).sticks).toBe(false);
  });
});

describe("isBlankRow: строка книги без данных", () => {
  it("без времени, профиля и вида материала строка пуста", () => {
    expect(isBlankRow(row({ time: "", profile: "", material_type: "" }))).toBe(true);
  });

  it("прочерк за значение не считается", () => {
    expect(isBlankRow(row({ time: "—", profile: "—", material_type: "—" }))).toBe(true);
  });

  it("любое из трёх полей делает строку непустой", () => {
    expect(isBlankRow(row({ time: "", profile: "", material_type: "Пороги" }))).toBe(false);
    expect(isBlankRow(row({ time: "", profile: "ЮП-1401", material_type: "" }))).toBe(false);
    expect(isBlankRow(row({ time: "12:00", profile: "", material_type: "" }))).toBe(false);
  });
});

describe("mergeHangerMeta: книга и проход линии", () => {
  it("проход линии перекрывает книгу: строка могла измениться после записи", () => {
    const meta = mergeHangerMeta(
      [row({ number: "777", profile: "ЮП-1401", color: "белый" })],
      [{ hanger: 777, profile: "СП-777", color: "золото" }],
    );

    expect(meta["777"].profile).toBe("СП-777");
    expect(meta["777"].color).toBe("золото");
  });

  it("пустое значение прохода не стирает данные книги", () => {
    const meta = mergeHangerMeta(
      [row({ number: "777", profile: "ЮП-1401", color: "белый" })],
      [{ hanger: "777", profile: "   ", color: null }],
    );

    expect(meta["777"].profile).toBe("ЮП-1401");
    expect(meta["777"].color).toBe("белый");
  });

  it("проход добавляет подвес, которого нет в книге", () => {
    const meta = mergeHangerMeta([], [{ hanger: 801, profile: "СП-777", color: "золото" }]);

    expect(meta["801"].profile).toBe("СП-777");
  });

  it("строки и проходы без номера в сводку не попадают", () => {
    const meta = mergeHangerMeta(
      [row({ number: "", profile: "ЮП-1401" })],
      [{ hanger: "", profile: "СП-777" }],
    );

    expect(meta).toEqual({});
  });
});
