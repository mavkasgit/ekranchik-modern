import { execSync, spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Ручной разбор .env файла
function loadEnvFile(filePath: string): Record<string, string> {
  try {
    if (!fs.existsSync(filePath)) return {};
    const content = fs.readFileSync(filePath, 'utf8');
    const env: Record<string, string> = {};
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx === -1) continue;
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      env[key] = val.replace(/^"|"$/g, '').replace(/^'|'$/g, '');
    }
    return env;
  } catch {
    return {};
  }
}

const envPath = path.resolve(__dirname, '.env');
const envVars = loadEnvFile(envPath);

Object.entries(envVars).forEach(([k, v]) => {
  if (process.env[k] === undefined || process.env[k] === '') process.env[k] = v;
});

const BROWSER_MODE = process.env.E2E_BROWSER_MODE || 'cdp';
const BROWSER_PORT = process.env.BROWSER_PORT || '9222';
const REMOTE_CHROME_HOST = process.env.REMOTE_CHROME_HOST || 'localhost';
const REMOTE_DEBUGGING_URL = `http://${REMOTE_CHROME_HOST}:${BROWSER_PORT}`;
const CHROME_PATH = process.env.CHROME_PATH || '';

async function checkChromeCdp(): Promise<boolean> {
  try {
    const res = await fetch(`${REMOTE_DEBUGGING_URL}/json/version`);
    if (res.ok) {
      const data = await res.json() as any;
      console.log(`✅ Chrome CDP найден: ${data.Browser}`);
      return true;
    }
  } catch (e) {
    // Не отвечает
  }
  return false;
}

async function globalSetup() {
  if (BROWSER_MODE === 'cdp') {
    console.log(`Проверка подключения Chrome CDP на ${REMOTE_DEBUGGING_URL}...`);
    const isReady = await checkChromeCdp();
    if (!isReady) {
      if (CHROME_PATH) {
        console.log(`Chrome недоступен. Запуск через CHROME_PATH: ${CHROME_PATH}...`);
        try {
          if (process.platform === 'win32') {
            const chromeProcess = spawn(CHROME_PATH, [
              `--remote-debugging-port=${BROWSER_PORT}`,
              '--no-first-run',
              '--no-default-browser-check',
              '--user-data-dir=c:\\Users\\user\\VibeCoding\\ekranchik-modern\\.chrome-dev-profile',
              'about:blank'
            ], {
              detached: true,
              stdio: 'ignore'
            });
            chromeProcess.unref();
          } else {
            const chromeProcess = spawn(CHROME_PATH, [
              `--remote-debugging-port=${BROWSER_PORT}`,
              '--no-first-run',
              '--no-default-browser-check',
              '--headless',
              '--user-data-dir=./.chrome-dev-profile',
              'about:blank'
            ], {
              detached: true,
              stdio: 'ignore'
            });
            chromeProcess.unref();
          }
          await new Promise(r => setTimeout(r, 3000));
          const verifyReady = await checkChromeCdp();
          if (verifyReady) {
            console.log(`✅ Chrome успешно запущен и готов к отладке.`);
          } else {
            console.warn(`⚠️ Chrome запущен, но порт отладки ${BROWSER_PORT} все еще недоступен.`);
          }
        } catch (launchErr: any) {
          console.warn(`❌ Не удалось запустить Chrome: ${launchErr.message}`);
        }
      } else {
        console.warn(`⚠️ Chrome недоступен на ${REMOTE_DEBUGGING_URL}. Убедитесь, что он запущен с флагом --remote-debugging-port=${BROWSER_PORT}`);
      }
    }
  } else {
    console.log(`Режим ${BROWSER_MODE} — Playwright будет управлять жизненным циклом браузера.`);
  }
}

export default globalSetup;
