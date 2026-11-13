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
async function openViewer(page: Page): Promise<{ viewer: Locator; articleDialog: Locator }> {
  // Превью само открывает просмотрщик (спека 0002), поэтому карточку
  // открываем по заголовку: сценарий проверяет фото именно из карточки.
  const card = page
    .getByTestId("profile-card")
    .filter({ has: page.locator('button[title="Открыть фото"]') })
    .first();
  const hasPhoto = await card
    .waitFor({ state: "visible", timeout: 15000 })
    .then(() => true)
    .catch(() => false);
  test.skip(!hasPhoto, "В каталоге нет карточек с фото: нужен стенд с данными.");

  const article = (await card.getByRole("heading").innerText()).trim();
  await card.getByRole("heading").click();

  const articleDialog = page.getByRole("dialog", { name: article });
  await expect(articleDialog).toBeVisible();

  const openPhotoButton = articleDialog.locator('button[title="Открыть фото"]');
  await expect(openPhotoButton).toBeVisible();
  await openPhotoButton.click();

  const viewer = page.getByTestId("photo-viewer");
  await expect(viewer).toBeVisible();
  return { viewer, articleDialog };
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

        const { viewer, articleDialog } = await openViewer(page);
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
        await expect(articleDialog.locator('button[title="Открыть фото"]')).toBeVisible();

        // 5. Скачивание отдаёт файл.
        await articleDialog.locator('button[title="Открыть фото"]').click();
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

test.describe("Каталог: поиск, фильтр по длине и примечание", () => {
  test("поиск сужает список, длина фильтрует таблицу, примечание переживает перезагрузку", async ({
    connectedPage: page,
  }) => {
    test.setTimeout(120_000);

    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`${BASE_URL}/catalog`);
    // Прошлый прогон мог оставить фильтры и режим в localStorage.
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await leaveKioskMode(page);

    const cards = page.getByTestId("profile-card");
    await expect(cards.first()).toBeVisible({ timeout: 15_000 });
    const total = await cards.count();
    expect(total).toBeGreaterThan(0);

    await test.step("превью открывает просмотрщик напрямую", async () => {
      const thumb = cards.locator('button[title="Открыть фото"]').first();
      if ((await thumb.count()) === 0) return;

      await thumb.click();
      const viewer = page.getByTestId("photo-viewer");
      await expect(viewer).toBeVisible();
      // Карточка артикула при этом не открывается.
      await expect(page.getByLabel("Примечание")).toBeHidden();

      await page.keyboard.press("Escape");
      await expect(viewer).toBeHidden();
    });

    const search = page.getByPlaceholder("Поиск по артикулу, наименованию и примечанию...");

    await test.step("поиск «033» сужает список", async () => {
      await search.fill("033");
      await expect.poll(() => cards.count(), { timeout: 5_000 }).toBeLessThan(total);
      expect(await cards.count()).toBeGreaterThan(0);

      await page.locator('button[title="Очистить поиск"]').click();
      await expect.poll(() => cards.count(), { timeout: 5_000 }).toBe(total);
    });

    await test.step("фильтр по длине из заголовка таблицы", async () => {
      await page.locator('button[title="Таблица"]').click();

      const rows = page.locator("table tbody tr");
      await expect(rows.first()).toBeVisible({ timeout: 10_000 });
      const before = await rows.count();

      const lengthHeader = page.locator("th").filter({
        has: page.getByRole("button", { name: "Длина", exact: true }),
      });
      await lengthHeader.locator('button[title="Фильтр"]').click();

      const panel = page.getByRole("dialog", { name: "Фильтр колонки" });
      await expect(panel).toBeVisible();
      const checkbox = panel.getByRole("checkbox").first();
      const lengthLabel = (await checkbox.locator("xpath=..").innerText()).trim();
      await checkbox.click();
      await panel.getByRole("button", { name: "Готово" }).click();

      await expect.poll(() => rows.count(), { timeout: 5_000 }).toBeLessThan(before);
      expect(await rows.count()).toBeGreaterThan(0);
      await expect(page.getByText(`Длина: ${lengthLabel}`)).toBeVisible();
      // Группа длин — одно условие: счётчик считает её один раз.
      await expect(page.getByText("Фильтров: 1")).toBeVisible();
    });

    await test.step("примечание сохраняется по потере фокуса и переживает перезагрузку", async () => {
      const rows = page.locator("table tbody tr");
      const article = (await rows.first().locator("td").nth(1).innerText()).trim();
      await rows.first().locator("td").nth(1).click();

      const dialog = page.getByRole("dialog", { name: article });
      await expect(dialog).toBeVisible();
      const notes = dialog.getByLabel("Примечание");
      const original = await notes.inputValue();
      const saved = `e2e-${Date.now()}`;

      const savedPatch = page.waitForResponse(
        (response) => response.request().method() === "PATCH" && response.url().includes("/notes"),
      );
      await notes.fill(saved);
      await notes.blur();
      expect((await savedPatch).ok()).toBeTruthy();

      // Фильтр длины и режим таблицы пережили перезагрузку; артикул ищем по имени.
      await page.reload();
      await leaveKioskMode(page);
      await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 15_000 });
      await search.fill(article);

      const row = page
        .locator("table tbody tr")
        .filter({ has: page.getByText(article, { exact: true }) })
        .first();
      await expect(row).toBeVisible({ timeout: 5_000 });
      await row.locator("td").nth(1).click();

      const reopened = page.getByRole("dialog", { name: article });
      const reopenedNotes = reopened.getByLabel("Примечание");
      await expect(reopenedNotes).toHaveValue(saved, { timeout: 10_000 });

      // Вернуть примечание как было: тест не оставляет следов в каталоге.
      const restorePatch = page.waitForResponse(
        (response) => response.request().method() === "PATCH" && response.url().includes("/notes"),
      );
      await reopenedNotes.fill(original);
      await reopenedNotes.blur();
      expect((await restorePatch).ok()).toBeTruthy();
    });
  });
});
