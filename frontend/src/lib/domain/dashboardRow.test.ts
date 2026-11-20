import { describe, expect, it } from "vitest";
import {
  describeHangerRow,
  isBlankRow,
  mergeHangerMeta,
  needsPhotoCaption,
  profileCellInfo,
  profilesWithPhoto,
} from "./dashboardRow";
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

describe("profilesWithPhoto: кто попадает в «Фото»", () => {
  it("профиль без файла в колонку не идёт", () => {
    const profiles = [profileInfo("ЮП-3233"), { ...profileInfo("3416"), has_photo: false }];

    expect(profilesWithPhoto(profiles).map((profile) => profile.name)).toEqual(["ЮП-3233"]);
  });
});

describe("needsPhotoCaption: когда у кадра нужен артикул", () => {
  it("один профиль — подпись не нужна", () => {
    expect(needsPhotoCaption([profileInfo("ЮП-2083")])).toBe(false);
  });

  it("снимок есть у каждого профиля — порядок кадров и так совпадает с артикулами", () => {
    expect(needsPhotoCaption([profileInfo("ЮП-3035"), profileInfo("ЮП-2396")])).toBe(false);
  });

  it("у части профилей снимка нет — без подписи не понять, чей это кадр", () => {
    // Строка «3416 + 362»: кадр один, и он не обязательно первый артикул.
    expect(
      needsPhotoCaption([{ ...profileInfo("3416"), has_photo: false }, profileInfo("362")]),
    ).toBe(true);
  });

  it("снимков нет вовсе — подписывать нечего", () => {
    expect(needsPhotoCaption([{ ...profileInfo("3416"), has_photo: false }])).toBe(false);
  });
});

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

describe("profileCellInfo: ячейка «Профиль» в две строки", () => {
  // Бейджи остаются в «Профиле» только у профилей без снимка: у остальных они
  // едут со снимком. Поэтому здесь профили без фото.
  const info = (name: string, lengthText?: string, processing: string[] = []): ProfileInfo => ({
    ...profileInfo(name),
    has_photo: false,
    length_text: lengthText ?? null,
    processing,
  });

  it("длина остаётся в тексте: на киоске — то, что ввёл оператор", () => {
    // Режем только служебные хвосты, а не запись оператора: «1,8 метра» в
    // «Профиле» остаётся, бейдж у снимка — дополнение, а не замена текста.
    const cell = profileCellInfo(row({ profiles_info: [info("ЮП-2083 1,8 метра", "1,8 м")] }));

    expect(cell).toEqual({
      article: "ЮП-2083 1,8 метра",
      articles: ["ЮП-2083 1,8 метра"],
      processing: [],
      lengths: ["1,8 м"],
    });
  });

  it("длина в скобках тоже остаётся как в книге", () => {
    const cell = profileCellInfo(row({ profiles_info: [info("ЮП-2083 (1.8)", "1,8 м")] }));

    expect(cell?.article).toBe("ЮП-2083 (1.8)");
  });

  it("несколько профилей идут через плюс, обработки не повторяются", () => {
    const cell = profileCellInfo(
      row({
        profiles_info: [
          info("АТ-7314 окно", undefined, ["окно"]),
          info("ЮП-2972 паз", "2,75 м", ["паз", "окно"]),
        ],
      }),
    );

    expect(cell).toEqual({
      article: "АТ-7314 окно + ЮП-2972 паз",
      articles: ["АТ-7314 окно", "ЮП-2972 паз"],
      processing: ["окно", "паз"],
      lengths: ["2,75 м"],
    });
  });

  it("у профиля со снимком бейджи остаются при снимке, а не в «Профиле»", () => {
    // «1,8 м — это который?»: два артикула с фото, длина у второго. В ячейке
    // «Профиль» бейджа быть не должно, иначе он читается как общий для строки.
    const cell = profileCellInfo(
      row({
        profiles_info: [
          { name: "ЮП-3233", processing: [], has_photo: true },
          { name: "ЮП-3361 1,8 метра", processing: [], has_photo: true, length_text: "1,8 м" },
        ],
      }),
    );

    expect(cell?.articles).toEqual(["ЮП-3233", "ЮП-3361 1,8 метра"]);
    expect(cell?.processing).toEqual([]);
    expect(cell?.lengths).toEqual([]);
  });

  it("профилей нет — ячейка печатает подпись книги", () => {
    expect(profileCellInfo(row({ profiles_info: [] }))).toBeNull();
  });
});

describe("describeHangerRow: сколько строк занимает подвес", () => {
  it("больше двух профилей — фото уходят на второй ряд", () => {
    const meaning = describeHangerRow(
      row({ profiles_info: [profileInfo("a"), profileInfo("b"), profileInfo("c")] }),
    );

    expect(meaning.photosBelow).toBe(true);
    expect(meaning.profileOwnsPhotoColumn).toBe(false);
    expect(meaning.rowSpan).toBe(2);
  });

  it("два профиля остаются в первой строке", () => {
    const meaning = describeHangerRow(row({ profiles_info: [profileInfo("a"), profileInfo("b")] }));

    expect(meaning.photosBelow).toBe(false);
    expect(meaning.rowSpan).toBe(1);
  });

  it("снимков нет — колонка «Фото» отдаётся профилю, заглушки не рисуются", () => {
    // Три профиля без каталога: раньше это давало вторую строку из трёх серых
    // квадратов и 150 px пустой колонки, теперь текст занимает всё место.
    const meaning = describeHangerRow(
      row({
        profiles_info: [
          { name: "0.8x1000x600", processing: [], has_photo: false },
          { name: "Остнаска", processing: [], has_photo: false },
          { name: "Панель HOOK-ON H-100 600*1800мм", processing: [], has_photo: false },
        ],
      }),
    );

    expect(meaning.photosBelow).toBe(false);
    expect(meaning.profileOwnsPhotoColumn).toBe(true);
    expect(meaning.rowSpan).toBe(1);
    expect(meaning.badges).toEqual([]);
  });

  it("снимок есть хотя бы у одного профиля — колонка остаётся", () => {
    const meaning = describeHangerRow(
      row({
        profiles_info: [
          { name: "a", processing: [], has_photo: false },
          { name: "b", processing: [], has_photo: true, photo_thumb: "images/b-thumb.jpg" },
        ],
      }),
    );

    expect(meaning.profileOwnsPhotoColumn).toBe(false);
  });

  it("витрина «Все профили»: фото приходит в строке, колонка не отдаётся тексту", () => {
    const meaning = describeHangerRow(
      row({ profiles_info: [], profile_photo_thumb: "images/x-thumb.jpg" }),
    );

    expect(meaning.profileOwnsPhotoColumn).toBe(false);
  });

  it("текст профиля не влез в три строки — снимки уезжают под него", () => {
    // Профиль один и со снимком, но длинная запись не помещается в узкий трек:
    // строка отдаёт «Фото» тексту, а снимок встаёт вторым рядом с подписью.
    const meaning = describeHangerRow(row({ profiles_info: [profileInfo("a")] }), 0, {
      profileOverflows: true,
    });

    expect(meaning.photosBelow).toBe(true);
    expect(meaning.rowSpan).toBe(2);
    expect(meaning.profileOwnsPhotoColumn).toBe(false);
  });

  it("без снимков замер ничего не меняет: колонка и так у профиля", () => {
    const meaning = describeHangerRow(
      row({ profiles_info: [{ name: "Панель HOOK-ON H-100", processing: [], has_photo: false }] }),
      0,
      { profileOverflows: true },
    );

    expect(meaning.photosBelow).toBe(false);
    expect(meaning.profileOwnsPhotoColumn).toBe(true);
    expect(meaning.rowSpan).toBe(1);
  });

  it("бейдж причины второго ряда не добавляет: пометка стоит в ячейке «Тип»", () => {
    const meaning = describeHangerRow(
      row({ time_warning: "На линии 9.0ч", time_warning_code: "DELAY" }),
    );

    expect(meaning.photosBelow).toBe(false);
    expect(meaning.profileOwnsPhotoColumn).toBe(true);
    expect(meaning.rowSpan).toBe(1);
    expect(meaning.badges.map((badge) => badge.code)).toEqual(["DELAY"]);
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

  it("брак не дублируется, если код подбора тоже говорит о браке", () => {
    // Бэкенд такого кода не шлёт, но два одинаковых бейджа оператору ничего
    // не добавляют, а ключи в списке React ломают.
    const badges = describeHangerRow(row({ is_defect: true, time_warning_code: "DEFECT" })).badges;

    expect(badges.map((badge) => badge.code)).toEqual(["DEFECT"]);
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
