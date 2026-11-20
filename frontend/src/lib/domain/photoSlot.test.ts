import { describe, expect, it } from "vitest";

import {
  MIN_PHOTO_WIDTH,
  PHOTO_HEIGHT,
  planPhotoSlot,
  photoHeightAtBand,
  photoWidthAtBand,
} from "./photoSlot";

// Раскладка слота «Фото»: кадр в полосе 40 px, подпись сбоку или под кадром.
// Проверяем решение числами, без браузера: страница только исполняет его.

const SOLO = 148;
const PAIR = 70;

describe("photoWidthAtBand: кадр в полосе", () => {
  it("широкий кадр упирается в ширину слота", () => {
    // 800×200 при полосе 148: масштаб держит ширина, кадр 148×38.5 (с рамкой).
    expect(photoWidthAtBand(800, 200, SOLO)).toBeCloseTo(148, 5);
    expect(photoHeightAtBand(800, 200, SOLO)).toBeCloseTo(38.5, 5);
  });

  it("узкий кадр упирается в потолок высоты", () => {
    // 100×100: масштаб держит высота, кадр 40×40.
    expect(photoWidthAtBand(100, 100, SOLO)).toBeCloseTo(40, 5);
    expect(photoHeightAtBand(100, 100, SOLO)).toBeCloseTo(40, 5);
  });

  it("кадр ещё не загружен — считать нечего", () => {
    expect(photoWidthAtBand(0, 0, SOLO)).toBe(0);
    expect(photoHeightAtBand(0, 0, SOLO)).toBe(0);
  });
});

describe("planPhotoSlot: подпись сбоку или под кадром", () => {
  it("бейдж «2,5 м» влезает сбоку: кадр поджимается на 5 %", () => {
    // Реальный случай строки 12–14: кадр 111 px и бейдж 33 px в слоте 148.
    // 111 + 4 + 33 = 148 — подпись сбоку, строка не растёт.
    const plan = planPhotoSlot({
      naturalWidth: 172,
      naturalHeight: 42,
      sideWidth: 33,
      slotWidth: SOLO,
    });

    expect(plan.compact).toBe(false);
    expect(plan.photoMax).toBe(SOLO - 4 - 33);
  });

  it("широкому кадру места сбоку нет: подпись уходит под него", () => {
    // 148 px кадр и подпись 60 px: ужать до 84 — уже не разглядеть деталь.
    const plan = planPhotoSlot({
      naturalWidth: 800,
      naturalHeight: 200,
      sideWidth: 60,
      slotWidth: SOLO,
    });

    expect(plan.compact).toBe(true);
    expect(plan.photoMax).toBeUndefined();
  });

  it("подпись влезает без поджатия — потолок не нужен", () => {
    const plan = planPhotoSlot({
      naturalWidth: 100,
      naturalHeight: 100,
      sideWidth: 31,
      slotWidth: SOLO,
    });

    expect(plan.compact).toBe(false);
    expect(plan.photoMax).toBeUndefined();
  });

  it("пара: узкий кадр и бейдж делят слот 70 px", () => {
    // 36 + 4 + 31 = 71 — кадр поджимается на пиксель, подпись остаётся сбоку.
    const plan = planPhotoSlot({
      naturalWidth: 36,
      naturalHeight: 40,
      sideWidth: 31,
      slotWidth: PAIR,
    });

    expect(plan.compact).toBe(false);
    expect(plan.photoMax).toBe(PAIR - 4 - 31);
  });

  it("пара: широкий кадр с бейджем — только под кадром", () => {
    const plan = planPhotoSlot({
      naturalWidth: 70,
      naturalHeight: 40,
      sideWidth: 40,
      slotWidth: PAIR,
    });

    expect(plan.compact).toBe(true);
  });

  it("подписи нет — переносить нечего", () => {
    const plan = planPhotoSlot({
      naturalWidth: 70,
      naturalHeight: 40,
      sideWidth: 0,
      slotWidth: PAIR,
    });

    expect(plan.compact).toBe(false);
    expect(plan.photoMax).toBeUndefined();
  });

  it("полоса 40 px — потолок ширины не отнимает высоту у квадратного кадра", () => {
    expect(PHOTO_HEIGHT).toBe(40);
    expect(MIN_PHOTO_WIDTH).toBeLessThanOrEqual(PHOTO_HEIGHT);
  });

  it("поджатый кадр теряет высоту — в ?stress его надо обвести", () => {
    // 172×42, ужатый до 111 px: высота 29 px < 36, короче порога обводки.
    expect(photoHeightAtBand(172, 42, 111)).toBeLessThan(PHOTO_HEIGHT - 4);
  });
});
