import { defineConfig } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

function loadEnvFile(filePath: string): Record<string, string> {
  if (!fs.existsSync(filePath)) return {};
  try {
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

// Load env from e2e/.env or fall back to root .env
let envPath = path.resolve(__dirname, 'e2e/.env');
if (!fs.existsSync(envPath)) {
  envPath = path.resolve(__dirname, '.env');
}

const envVars = loadEnvFile(envPath);
Object.entries(envVars).forEach(([k, v]) => {
  if (process.env[k] === undefined || process.env[k] === '') process.env[k] = v;
});

const BROWSER_MODE = process.env.E2E_BROWSER_MODE || 'cdp';

const baseUse = {
  trace: 'retain-on-failure',
  screenshot: 'only-on-failure',
  video: 'retain-on-failure',
} as const;

export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  timeout: 30_000,
  workers: 1,
  reporter: process.env.CI ? 'list' : [['list'], ['html']],
  use: BROWSER_MODE === 'cdp'
    ? { ...baseUse }
    : { ...baseUse, browserName: 'chromium', headless: BROWSER_MODE === 'headless' },
  globalSetup: BROWSER_MODE === 'cdp' ? undefined : './e2e/global-setup.ts',
});
