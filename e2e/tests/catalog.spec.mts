import type { Locator, Page } from "@playwright/test";
import { test, expect } from "../fixtures";

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";

// Окна из спеки: на обоих фото должно быть видно целиком.
const VIEWPORTS = [
  { width: 1366, height: 768 },
  { width: 900, height: 500 },
];

interface ImageMetrics {
  x: number;
  y: number;
  width: number;
  height: number;
  naturalWidth: number;
  naturalHeight: number;
  transform: string;
}

// Kiosk-режим включается сам, когда окно совпадает с экраном: в e2e это
// обычное дело, а навигация в полноэкранном режиме спрятана.
async function leaveKioskMode(page: Page) {
  const exitFullscreenButton = page.getByRole("button", { name: "Выход" });
  try {
    await exitFullscreenButton.waitFor({ state: "visible", timeout: 2000 });
    await exitFullscreenButton.click();
  } catch {
    // Полноэкранный режим не активен.
  }
}

/** Карточка с фото открывает карточку артикула, фото в ней — просмотрщик. */
async function openViewer(page: Page): Promise<Locator> {
  const cardPhoto = page.locator("div.grid img[alt]").first();
  const hasPhoto = await cardPhoto
    .waitFor({ state: "visible", timeout: 15000 })
    .then(() => true)
    .catch(() => false);
  test.skip(!hasPhoto, "В каталоге нет карточек с фото: нужен стенд с данными.");

  await cardPhoto.click();
  const openPhotoButton = page.locator('button[title="Открыть фото"]');
  await expect(openPhotoButton).toBeVisible();
  await openPhotoButton.click();

  const viewer = page.getByTestId("photo-viewer");
  await expect(viewer).toBeVisible();
  return viewer;
}

async function imageMetrics(viewer: Locator): Promise<ImageMetrics> {
  return viewer.locator("img").evaluate((node) => {
    const image = node as HTMLImageElement;
    const rect = image.getBoundingClientRect();
    return {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
      transform: getComputedStyle(image).transform,
    };
  });
}

/** Масштаб из `matrix(...)`/`matrix3d(...)`: первые два числа — оси X и Y. */
function scaleFromTransform(transform: string): number {
  const match = /matrix(?:3d)?\(([^)]+)\)/.exec(transform);
  if (!match) return 1;
  const [a, b] = match[1].split(",").map(Number);
  return Math.hypot(a, b);
}

test.describe("Каталог: просмотр фото", () => {
  test("фото открывается вписанным, зумится, закрывается по Esc и скачивается", async ({
    connectedPage: page,
  }) => {
    test.setTimeout(90_000);

    for (const viewport of VIEWPORTS) {
      await test.step(`окно ${viewport.width}×${viewport.height}`, async () => {
        await page.setViewportSize(viewport);
        await page.goto(`${BASE_URL}/catalog`);
        await leaveKioskMode(page);

        const viewer = await openViewer(page);
        const image = viewer.locator("img");
        await expect
          .poll(async () => (await imageMetrics(viewer)).naturalWidth, { timeout: 10_000 })
          .toBeGreaterThan(0);

        // 1. Старт — «вписано»: картинка целиком внутри экрана, пропорции целы.
        const fitted = await imageMetrics(viewer);
        expect(fitted.x).toBeGreaterThanOrEqual(-1);
        expect(fitted.y).toBeGreaterThanOrEqual(-1);
        expect(fitted.x + fitted.width).toBeLessThanOrEqual(viewport.width + 1);
        expect(fitted.y + fitted.height).toBeLessThanOrEqual(viewport.height + 1);
        const naturalRatio = fitted.naturalWidth / fitted.naturalHeight;
        expect(Math.abs(fitted.width / fitted.height - naturalRatio) / naturalRatio).toBeLessThan(
          0.02,
        );
        // «1×» — именно вписано, а не натуральный размер.
        expect(scaleFromTransform(fitted.transform)).toBeCloseTo(1, 2);

        // 2. Прокрутки в оверлее нет.
        const scroll = await viewer.evaluate((node) => ({
          width: node.scrollWidth,
          clientWidth: node.clientWidth,
          height: node.scrollHeight,
          clientHeight: node.clientHeight,
        }));
        expect(scroll.width).toBeLessThanOrEqual(scroll.clientWidth + 1);
        expect(scroll.height).toBeLessThanOrEqual(scroll.clientHeight + 1);

        // 3. Колесо приближает к курсору, картинка остаётся в окне.
        await page.mouse.move(viewport.width / 2, viewport.height / 2);
        await page.mouse.wheel(0, -300);
        await expect
          .poll(async () => scaleFromTransform((await imageMetrics(viewer)).transform))
          .toBeGreaterThan(1);

        const zoomed = await imageMetrics(viewer);
        expect(zoomed.x).toBeLessThan(viewport.width / 2);
        expect(zoomed.x + zoomed.width).toBeGreaterThan(viewport.width / 2);
        expect(zoomed.y).toBeLessThan(viewport.height / 2);
        expect(zoomed.y + zoomed.height).toBeGreaterThan(viewport.height / 2);

        // 4. Esc закрывает просмотрщик, карточка артикула остаётся.
        await page.keyboard.press("Escape");
        await expect(viewer).toBeHidden();
        await expect(page.locator('button[title="Открыть фото"]')).toBeVisible();

        // 5. Скачивание отдаёт файл.
        await page.locator('button[title="Открыть фото"]').click();
        await expect(viewer).toBeVisible();
        await expect(image).toBeVisible();

        const [download] = await Promise.all([
          page.waitForEvent("download"),
          viewer.getByRole("button", { name: "Скачать фото" }).click(),
        ]);
        expect(download.suggestedFilename()).toMatch(/\.(png|jpe?g|webp|gif|bmp)$/i);
      });
    }

    await page.setViewportSize({ width: 1366, height: 768 });
  });
});
