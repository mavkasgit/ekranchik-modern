import { test, expect } from '../fixtures';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';

test.describe('OPC UA Hanger Realtime Live Demo', () => {
  test('should simulate hanger 777 going through the line and appearing on dashboard', async ({ connectedPage: page }) => {
    test.setTimeout(90000);
    // 1. Открываем страницу мониторинга OPC UA (используем BrowserRouter без хэша!)
    await page.goto(`${BASE_URL}/opcua`);

    // Отключаем Kiosk Mode, если он сработал
    const exitFullscreenButton = page.getByRole('button', { name: 'Выход' });
    try {
      await exitFullscreenButton.waitFor({ state: 'visible', timeout: 2000 });
      await exitFullscreenButton.click();
      console.log('✅ Полноэкранный режим отключен.');
    } catch (e) {
      console.log('ℹ️ Полноэкранный режим не активен.');
    }

    // Если OPC UA отключен, нажимаем кнопку Connect
    const connectButton = page.getByRole('button', { name: 'Connect', exact: true });
    try {
      await connectButton.waitFor({ state: 'visible', timeout: 2000 });
      await connectButton.click();
      console.log('✅ Нажата кнопка Connect для подключения к OPC UA.');
    } catch (e) {
      console.log('ℹ️ OPC UA уже подключен или кнопка Connect отсутствует.');
    }

    // 2. Убеждаемся, что мы на вкладке "Production Line"
    const lineTab = page.getByRole('button', { name: 'Production Line' });
    await expect(lineTab).toBeVisible({ timeout: 10000 });
    await lineTab.click();

    console.log('⌛ Ожидаем появления подвеса 777 на линии...');
    
    // Ожидаем появление плашки с подвесом 777 на линии (в одной из ванн)
    const hangerElement = page.locator('text=777');
    await expect(hangerElement.first()).toBeVisible({ timeout: 20000 });
    console.log('🎯 Подвес 777 появился на линии!');

    // Делаем первый скриншот (подвес на линии)
    await page.screenshot({ path: 'C:\\Users\\user\\.gemini\\antigravity\\browser_recordings\\hanger_on_line.png' });
    console.log('📸 Скриншот подвеса на линии сохранен: hanger_on_line.png');

    // Даем подвесу пройти линию (последовательность занимает около 30 секунд в ускоренном режиме)
    console.log('⌛ Наблюдаем за перемещением подвеса по ваннам...');
    await page.waitForTimeout(20000);

    // 3. Переходим на Дашборд
    console.log('🔄 Переходим на Дашборд для проверки выгрузки...');
    await page.goto(`${BASE_URL}/`);

    // Снова отключаем Kiosk Mode на главной, если требуется
    try {
      await exitFullscreenButton.waitFor({ state: 'visible', timeout: 2000 });
      await exitFullscreenButton.click();
    } catch (e) {}

    // Ожидаем появление подвеса 777 в таблице дашборда
    console.log('⌛ Ожидаем выгрузки и сопоставления подвеса 777 в таблице...');
    
    // Проверяем, что в таблице появилась ячейка с ТЕСТ-КЛИЕНТ
    const clientCell = page.getByRole('cell', { name: 'ТЕСТ-КЛИЕНТ', exact: true });
    await expect(clientCell).toBeVisible({ timeout: 25000 });
    
    console.log('🎉 Подвес 777 успешно выгружен и отображен на дашборде!');
    
    // Проверяем также профиль и цвет
    await expect(page.getByRole('cell', { name: 'ТЕСТ-ПРОФИЛЬ', exact: true }).first()).toBeVisible();
    await expect(page.getByRole('cell', { name: 'золото', exact: true }).first()).toBeVisible();

    // Делаем второй скриншот (подвес на дашборде)
    await page.screenshot({ path: 'C:\\Users\\user\\.gemini\\antigravity\\browser_recordings\\hanger_unloaded_dashboard.png' });
    console.log('📸 Скриншот дашборда сохранен: hanger_unloaded_dashboard.png');
  });
});
