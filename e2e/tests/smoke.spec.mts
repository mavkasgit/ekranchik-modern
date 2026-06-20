import { test, expect } from '../fixtures';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:5173';

test.describe('Ekranchik Smoke Tests', () => {
  test('should load main page and show navigation links', async ({ connectedPage: page }) => {
    await page.goto(BASE_URL);

    // В автоматических тестах экранные размеры могут совпадать с размерами вьюпорта,
    // что триггерит KioskMode (авто-фуллскрин). Если кнопка "Выход" из фуллскрина видна,
    // кликаем по ней, чтобы отобразить навигационную панель.
    const exitFullscreenButton = page.getByRole('button', { name: 'Выход' });
    
    // Даем кнопке немного времени на отрисовку, если сработал авто-фуллскрин
    try {
      await exitFullscreenButton.waitFor({ state: 'visible', timeout: 3000 });
      await exitFullscreenButton.click();
      console.log('✅ Вышли из полноэкранного режима (Kiosk Mode).');
    } catch (e) {
      // Кнопка выхода не появилась, значит мы не в фуллскрине — продолжаем тест
      console.log('ℹ️ Полноэкранный режим не активен при загрузке.');
    }

    const dashboardLink = page.getByRole('link', { name: 'Дашборд' });
    await expect(dashboardLink).toBeVisible({ timeout: 15000 });

    await expect(page.getByRole('link', { name: 'Каталог' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Анализ' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'OPC UA' })).toBeVisible();
  });
});
