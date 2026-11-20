import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  PHOTO_PAIR_MAX_WIDTH,
  PHOTO_SOLO_MAX_WIDTH,
  ProfilePhoto,
} from "@/components/ProfilePhoto";
import type { ProfileInfo } from "@/types/dashboard";

// Ячейка «Фото» на дашборде: снимок или заглушка, артикул, обработки, длина.
// Рендерим в строку: в проекте нет jsdom, но react-dom/server показывает ту же
// разметку, которую увидит киоск (классы Tailwind и aria-атрибуты включительно).

function profile(overrides: Partial<ProfileInfo> = {}): ProfileInfo {
  return {
    name: "ЮП-2083 2,75 метра",
    canonical_name: "ЮП-2083",
    processing: [],
    has_photo: true,
    photo_thumb: "images/ЮП-2083-thumb.jpg",
    photo_full: "images/ЮП-2083.jpg",
    ...overrides,
  };
}

const noop = () => {};

describe("ProfilePhoto: длина из книги", () => {
  it("рисует бейдж длины рядом с обработкой у строки с фото", () => {
    const markup = renderToStaticMarkup(
      <ProfilePhoto
        profile={profile({ processing: ["окно"], length_text: "2,75 м", length_m: 2.75 })}
        onPhotoClick={noop}
      />,
    );

    expect(markup).toContain("ЮП-2083");
    expect(markup).toContain("окно");
    expect(markup).toContain("2,75 м");
    expect(markup).toContain('aria-label="Длина 2,75 м"');
    expect(markup).toContain('title="Длина 2,75 м"');
    expect(markup).toContain("bg-indigo-100");
  });

  it("показывает длину и у строки без снимка: заглушка, артикул, бейдж", () => {
    const markup = renderToStaticMarkup(
      <ProfilePhoto
        profile={profile({
          has_photo: false,
          photo_thumb: undefined,
          photo_full: undefined,
          length_text: "1,8 м",
          length_m: 1.8,
        })}
        onPhotoClick={noop}
      />,
    );

    expect(markup).toContain("1,8 м");
    expect(markup).toContain("bg-muted");
    expect(markup).not.toContain("<img");
  });

  it("без длины не рисует бейдж и не добавляет индиго", () => {
    const markup = renderToStaticMarkup(
      <ProfilePhoto profile={profile({ processing: ["окно"] })} onPhotoClick={noop} />,
    );

    expect(markup).toContain("окно");
    expect(markup).not.toContain('aria-label="Длина');
    expect(markup).not.toContain("bg-indigo-100");
  });

  it("у длинного артикула подпись переносится целиком, а бейдж длины остаётся", () => {
    const markup = renderToStaticMarkup(
      <ProfilePhoto
        profile={profile({ canonical_name: "ПТ80(юп-1880)", length_text: "2,7 м", length_m: 2.7 })}
        onPhotoClick={noop}
      />,
    );

    expect(markup).toContain("ПТ80(юп-1880)");
    // Обрезка прятала хвост артикула без возможности его увидеть на киоске:
    // подпись переносится, а ширина ограничена потолком.
    expect(markup).not.toContain("truncate");
    expect(markup).toContain("break-words");
    expect(markup).toContain("max-w-[110px]");
    expect(markup).toContain("2,7 м");
  });
});

describe("ProfilePhoto: потолок снимка", () => {
  it("в паре снимок ограничен 70 px по ширине", () => {
    const markup = renderToStaticMarkup(<ProfilePhoto profile={profile()} onPhotoClick={noop} />);

    expect(markup).toContain("max-w-[70px]");
    expect(markup).toContain("max-h-[40px]");
    expect(markup).not.toContain("max-w-[148px]");
  });

  it("одиночный снимок занимает всю колонку — 148 px, высота та же 40 px", () => {
    // Широкие превью каталога (аспект до 8,7:1) при потолке 70 px сжимались до
    // 70×8: высоту отнимала ширина. Одиночный снимок получает всю колонку.
    const markup = renderToStaticMarkup(
      <ProfilePhoto profile={profile()} onPhotoClick={noop} solo />,
    );

    expect(markup).toContain("max-w-[148px]");
    expect(markup).toContain("max-h-[40px]");
    expect(markup).not.toContain("max-w-[70px]");
  });

  it("пара ровно заполняет колонку: 70 + зазор 8 + 70 = 148", () => {
    // Инвариант бюджета: если пару расширить, второй снимок уедет под прокрутку.
    expect(PHOTO_PAIR_MAX_WIDTH * 2 + 8).toBe(PHOTO_SOLO_MAX_WIDTH);
    // Колонка «Фото» (PHOTO_COLUMN_WIDTH в Dashboard.tsx) — 150 px: одиночный
    // снимок занимает её целиком, оставляя 2 px на рамку по краям.
    expect(PHOTO_SOLO_MAX_WIDTH + 2).toBe(150);
  });

  it("обводка «сжат по ширине» появляется только по факту загрузки, не в разметке", () => {
    const markup = renderToStaticMarkup(
      <ProfilePhoto profile={profile()} onPhotoClick={noop} solo markShort />,
    );

    // SSR не грузит картинку — обводка ставится из onLoad по naturalWidth.
    expect(markup).not.toContain("ring-rose-500");
    expect(markup).not.toContain("data-short-photo");
  });
});
