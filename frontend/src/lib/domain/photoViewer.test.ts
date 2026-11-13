import { describe, expect, it } from "vitest";
import {
  MAX_ZOOM,
  MIN_ZOOM,
  clampPan,
  fitScale,
  resetView,
  zoomAroundPoint,
  zoomFromWheel,
} from "./photoViewer";

// Вьюпорты из спеки: фото должно влезать целиком на киоске, ноутбуке,
// маленьком окне и телефоне.
const VIEWPORTS = {
  desktop: { width: 1920, height: 1080 },
  laptop: { width: 1366, height: 768 },
  narrow: { width: 900, height: 500 },
  phone: { width: 390, height: 844 },
} as const;

const PORTRAIT = { width: 1200, height: 1600 };

describe("fitScale", () => {
  it("портретное фото вписывается в каждый вьюпорт из спеки", () => {
    // 1920/1200 = 1.6, 1080/1600 = 0.675 — ограничивает высота.
    expect(fitScale(PORTRAIT, VIEWPORTS.desktop)).toBeCloseTo(0.675, 6);
    expect(fitScale(PORTRAIT, VIEWPORTS.laptop)).toBeCloseTo(0.48, 6);
    expect(fitScale(PORTRAIT, VIEWPORTS.narrow)).toBeCloseTo(0.3125, 6);
    // 390/1200 = 0.325, 844/1600 = 0.5275 — ограничивает ширина.
    expect(fitScale(PORTRAIT, VIEWPORTS.phone)).toBeCloseTo(0.325, 6);
  });

  it("горизонтальное фото ограничивает ширина", () => {
    expect(fitScale({ width: 1600, height: 900 }, VIEWPORTS.narrow)).toBeCloseTo(5 / 9, 6);
  });

  it("мелкое фото не растягивается больше натурального размера", () => {
    expect(fitScale({ width: 200, height: 150 }, VIEWPORTS.desktop)).toBe(1);
  });

  it("фото ровно по размеру окна даёт 1×", () => {
    expect(fitScale({ width: 1920, height: 1080 }, VIEWPORTS.desktop)).toBe(1);
  });

  it("пока картинка не загружена, масштаб не считается", () => {
    expect(fitScale({ width: 0, height: 0 }, VIEWPORTS.desktop)).toBe(1);
  });
});

describe("clampPan", () => {
  it("во вписанном масштабе панорамы нет", () => {
    expect(clampPan({ x: 120, y: -80 }, 1, PORTRAIT, VIEWPORTS.narrow)).toEqual({
      x: 0,
      y: 0,
    });
  });

  it("на 2× двигает только по оси, где картинка больше окна", () => {
    // 1200×1600 в 900×500: вписано 375×500, на 2× — 750×1000.
    // По ширине 750 < 900 — запаса нет; по высоте (1000 - 500) / 2 = 250.
    expect(clampPan({ x: 100, y: 400 }, 2, PORTRAIT, VIEWPORTS.narrow)).toEqual({
      x: 0,
      y: 250,
    });
    expect(clampPan({ x: 0, y: -400 }, 2, PORTRAIT, VIEWPORTS.narrow)).toEqual({
      x: 0,
      y: -250,
    });
  });

  it("на 4× ограничивает обе оси", () => {
    // 4×: 1500×2000; запас по X (1500 - 900) / 2 = 300, по Y (2000 - 500) / 2 = 750.
    expect(clampPan({ x: 999, y: -999 }, 4, PORTRAIT, VIEWPORTS.narrow)).toEqual({
      x: 300,
      y: -750,
    });
  });

  it("внутри границ панорама остаётся как есть", () => {
    // 1000×1000 в 500×500: вписано 500×500, на 2× — 1000×1000, запас 250 по обеим осям.
    expect(
      clampPan({ x: 50, y: -100 }, 2, { width: 1000, height: 1000 }, { width: 500, height: 500 }),
    ).toEqual({
      x: 50,
      y: -100,
    });
  });
});

describe("zoomAroundPoint", () => {
  it("зум к курсору оставляет точку под курсором на месте", () => {
    // Точка в 100 px правее центра при 2× уходит в 200 px — панорама -100.
    expect(zoomAroundPoint({ zoom: 1, pan: { x: 0, y: 0 } }, { x: 100, y: 40 }, 2)).toEqual({
      zoom: 2,
      pan: { x: -100, y: -40 },
    });
  });

  it("обратный зум возвращает панораму к нулю", () => {
    expect(zoomAroundPoint({ zoom: 2, pan: { x: -100, y: -40 } }, { x: 100, y: 40 }, 1)).toEqual({
      zoom: 1,
      pan: { x: 0, y: 0 },
    });
  });

  it("зум в центре не двигает картинку", () => {
    expect(zoomAroundPoint({ zoom: 1, pan: { x: 0, y: 0 } }, { x: 0, y: 0 }, 3).pan).toEqual({
      x: 0,
      y: 0,
    });
  });

  it("масштаб не выходит за границы 1–4×", () => {
    expect(zoomAroundPoint({ zoom: 1, pan: { x: 0, y: 0 } }, { x: 0, y: 0 }, 10).zoom).toBe(
      MAX_ZOOM,
    );
    expect(zoomAroundPoint({ zoom: 2, pan: { x: 0, y: 0 } }, { x: 0, y: 0 }, 0.5).zoom).toBe(
      MIN_ZOOM,
    );
  });

  it("тот же масштаб оставляет вид без изменений", () => {
    const view = { zoom: 2.5, pan: { x: -30, y: 12 } };
    expect(zoomAroundPoint(view, { x: 10, y: 10 }, 2.5)).toEqual(view);
  });
});

describe("zoomFromWheel", () => {
  it("колесо от себя приближает, на себя отдаляет", () => {
    expect(zoomFromWheel(-100, 1)).toBe(1.25);
    expect(zoomFromWheel(100, 2)).toBe(1.75);
  });

  it("за границами масштаб упирается в 1× и 4×", () => {
    expect(zoomFromWheel(100, 1)).toBe(MIN_ZOOM);
    expect(zoomFromWheel(-100, MAX_ZOOM)).toBe(MAX_ZOOM);
    expect(zoomFromWheel(-100, 3.9)).toBe(MAX_ZOOM);
  });

  it("нулевая дельта не меняет масштаб", () => {
    expect(zoomFromWheel(0, 2)).toBe(2);
  });
});

describe("resetView", () => {
  it("двойной клик возвращает «вписано» и центр", () => {
    expect(resetView()).toEqual({ zoom: 1, pan: { x: 0, y: 0 } });
  });
});
