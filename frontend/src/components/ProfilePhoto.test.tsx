import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ProfilePhoto } from "@/components/ProfilePhoto";
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

  it("у длинного артикула подпись усекается, а бейдж длины остаётся", () => {
    const markup = renderToStaticMarkup(
      <ProfilePhoto
        profile={profile({ canonical_name: "ПТ80(юп-1880)", length_text: "2,7 м", length_m: 2.7 })}
        onPhotoClick={noop}
      />,
    );

    expect(markup).toContain("ПТ80(юп-1880)");
    expect(markup).toContain("truncate");
    expect(markup).toContain("max-w-[70px]");
    expect(markup).toContain("2,7 м");
  });
});
