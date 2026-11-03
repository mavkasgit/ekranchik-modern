import type { Page } from "@playwright/test";
import { test, expect } from "../fixtures";
import { colorName } from "../../frontend/src/lib/domain/color";

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";
const API_URL = process.env.E2E_API_URL || `${BASE_URL}/api`;

interface MatchedUnloadEvent {
  hanger: number;
  client: string;
  profile: string;
  color: string;
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

/**
 * Номер подвеса, который сейчас стоит на линии. Номер назначает симулятор или
 * ПЛК, поэтому тест читает его из разметки ванны, а не зашивает литералом.
 */
async function hangerOnLine(page: Page): Promise<string | null> {
  const titles = await page
    .locator('[title*="Подвес:"]')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("title") ?? ""));

  for (const title of titles) {
    const match = /Подвес:\s*(\d+)/.exec(title);
    if (match && match[1] !== "0") return match[1];
  }
  return null;
}

/** Проход подвеса, который бэкенд уже сопоставил со строкой книги учёта. */
async function matchedPass(page: Page, hangerNumber: string): Promise<MatchedUnloadEvent | null> {
  const response = await page.request.get(`${API_URL}/dashboard/opcua-unload-matched?limit=100`);
  if (!response.ok()) return null;

  const events = (await response.json()) as MatchedUnloadEvent[];
  return events.find((event) => String(event.hanger) === hangerNumber) ?? null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Имя ячейки профиля: плюсы книги на экране разделяются пробелом. */
function profileCellName(profile: string): RegExp | string {
  if (!profile.trim()) return "—";
  return new RegExp(`^${profile.split("+").map(escapeRegExp).join("\\+\\s*")}$`);
}

test.describe("OPC UA Hanger Realtime Live Demo", () => {
  test("подвес проходит линию и появляется в таблице выгрузки", async ({ connectedPage: page }) => {
    test.setTimeout(180000);

    // 1. Страница мониторинга OPC UA: подключаемся и смотрим линию.
    await page.goto(`${BASE_URL}/opcua`);
    await leaveKioskMode(page);

    // Если OPC UA отключён, нажимаем Connect.
    const connectButton = page.getByRole("button", { name: "Connect", exact: true });
    try {
      await connectButton.waitFor({ state: "visible", timeout: 2000 });
      await connectButton.click();
    } catch {
      // Уже подключено или кнопки нет.
    }

    const lineTab = page.getByRole("button", { name: "Production Line" });
    await expect(lineTab).toBeVisible({ timeout: 10000 });
    await lineTab.click();

    // 2. Ждём, пока подвес встанет в любую ванну, и запоминаем его номер.
    await expect
      .poll(() => hangerOnLine(page), {
        timeout: 60000,
        message: "подвес так и не встал на линию",
      })
      .not.toBeNull();

    const hangerNumber = (await hangerOnLine(page))!;
    console.log(`🎯 На линии подвес ${hangerNumber}`);

    await page.screenshot({ path: ".scratch/live_demo/hanger_on_line.png" });

    // 3. Выгрузка: подвес доходит до контрольной ванны, бэкенд сопоставляет
    //    проход со строкой книги. Клиент, профиль и цвет приходят из книги,
    //    поэтому ожидаемые имена ячеек тест берёт у бэкенда, а не выдумывает.
    console.log(`⌛ Ожидаем выгрузку подвеса ${hangerNumber}...`);
    await expect
      .poll(() => matchedPass(page, hangerNumber), {
        timeout: 90000,
        message: `подвес ${hangerNumber} не выгрузился`,
      })
      .not.toBeNull();

    const pass = (await matchedPass(page, hangerNumber))!;

    await page.goto(`${BASE_URL}/`);
    await leaveKioskMode(page);

    const unloadTable = page.getByRole("table", { name: "Выгрузка" });
    // Строку ищем по номеру в ячейке: номер стоит отдельной ячейкой только
    // внутри строки таблицы выгрузки.
    const unloadRow = unloadTable
      .getByRole("row")
      .filter({ has: page.getByRole("cell", { name: hangerNumber, exact: true }) })
      .first();

    await expect(unloadRow).toBeVisible({ timeout: 30000 });

    // Строка нарисована целиком: подвес, клиент, профиль и цвет связаны.
    await expect(
      unloadRow.getByRole("cell", { name: pass.client, exact: true }).first(),
    ).toBeVisible();
    await expect(
      unloadRow.getByRole("cell", { name: profileCellName(pass.profile) }).first(),
    ).toBeVisible();
    await expect(
      unloadRow.getByRole("cell", { name: colorName(pass.color), exact: true }).first(),
    ).toBeVisible();

    console.log(`🎉 Подвес ${hangerNumber} выгружен и показан на дашборде`);

    // Плашка «Обновление» на полторы секунды закрывает таблицу: для скриншота
    // даём ей уйти, иначе демо-кадр показывает зелёный прямоугольник.
    await page
      .getByText("Обновление", { exact: true })
      .waitFor({ state: "hidden", timeout: 5000 })
      .catch(() => {});

    await page.screenshot({ path: ".scratch/live_demo/hanger_unloaded_dashboard.png" });
  });
});
