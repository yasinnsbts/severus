// UI-регрессия: форма, генерация, F5, варианты, вкладки, копирование, новый сценарий.
// Запуск: node qa/tests/ui/regression.mjs
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';

const require = createRequire('C:/GitHub/severus/frontend/package.json');
const { chromium } = require('playwright');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const OUT = 'C:\\Users\\user\\AppData\\Local\\Temp\\opencode\\ui_regression_results.json';
const results = [];
const record = (name, ok, details = '') => {
  results.push({ name, ok, details });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${details ? ' — ' + details : ''}`);
};

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  permissions: ['clipboard-read', 'clipboard-write'],
});
const page = await context.newPage();

async function choose(label, optionText) {
  await page.locator(`button[aria-label="${label}"]`).click();
  await page.getByRole('option', { name: optionText, exact: true }).click();
}

async function setCheck(label, desired) {
  const element = page.getByLabel(label);
  if ((await element.isChecked()) !== desired) {
    await element.evaluate(node => node.click());
  }
}

async function waitResult(timeout = 900000) {
  await page.waitForSelector('.result-hero', { timeout });
}

async function clickGenerate() {
  const [response] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/api/v1/generations') && r.request().method() === 'POST'),
    page.getByRole('button', { name: /Сотворить сценарий/ }).click(),
  ]);
  const data = await response.json();
  return { status: response.status(), data };
}

try {
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Создать сценарий' }).click();
  record('Форма открывается', await page.getByText('Создадим немного волшебства').isVisible());

  await page.locator('.mode-actions button', { hasText: 'API' }).click();
  await page.waitForSelector('.mode-badge.connected', { timeout: 15000 });
  record('API подключён', true);

  await page.locator('button[aria-label="Школьное мероприятие"]').click();
  const eventCount = await page.getByRole('option').count();
  await page.keyboard.press('Escape');
  record('Каталог событий загружен', eventCount === 14, `вариантов: ${eventCount}`);

  // Ошибки формы: 36 учеников.
  await page.locator('input[type=number]').nth(0).fill('36');
  const generateDisabled = await page.getByRole('button', { name: /Сотворить сценарий/ }).isDisabled();
  record('36 учеников блокирует отправку', generateDisabled);
  await page.locator('input[type=number]').nth(0).fill('27');

  // Родители.
  await setCheck('В мероприятии участвуют родители', true);
  await page.locator('input[type=number]').nth(2).fill('12');
  await setCheck('Помощники', true);
  await setCheck('Зрители', true);

  // Два варианта.
  await page.locator('.segment button').nth(1).click();
  const started = await clickGenerate();
  record('POST генерации принят', started.status === 202, `HTTP ${started.status}`);
  await waitResult();
  const tabs = await page.locator('.results-header .tabs button').count();
  record('Два варианта отображаются', tabs === 2, `вкладок: ${tabs}`);
  record('Блоки этапов отображаются', (await page.locator('.timeline-step').count()) > 0);

  await page.locator('.results-header .tabs button').nth(1).click();
  const secondTitle = await page.locator('.result-hero h2').innerText();
  record('Переключение варианта работает', secondTitle.length > 0, secondTitle);

  await page.getByRole('button', { name: 'Материалы' }).click();
  const materials = await page.locator('.material-card').count();
  record('Вкладка «Материалы» открывается', materials > 0, `материалов: ${materials}`);

  await page.getByRole('button', { name: 'Участники' }).click();
  const roles = await page.locator('.role-list > div').count();
  record('Вкладка «Участники» открывается', roles > 0, `ролей: ${roles}`);

  await page.getByRole('button', { name: /Копировать сценарий/ }).click();
  await page.waitForTimeout(300);
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  record('Копирование сценария работает', clipboard.length > 100, `символов: ${clipboard.length}`);

  await page.reload({ waitUntil: 'networkidle' });
  await waitResult(20000);
  const restoredTabs = await page.locator('.results-header .tabs button').count();
  record('Готовый сценарий восстановлен после F5', restoredTabs === 2, `вкладок: ${restoredTabs}`);

  await page.locator('.new-scenario').click();
  record('Возврат к новому сценарию', await page.getByText('Создадим немного волшебства').isVisible());

  // F5 во время генерации.
  await page.locator('.segment button').first().click();
  const inFlight = await clickGenerate();
  record('Генерация для F5 запущена', inFlight.status === 202, `job ${inFlight.data.job_id}`);
  await page.waitForTimeout(2500);
  await page.reload({ waitUntil: 'domcontentloaded' });
  const loadingAfterReload = await page.locator('.loader-page').isVisible().catch(() => false);
  record('После F5 во время генерации показан прогресс', loadingAfterReload);
  await waitResult();
  record('Генерация завершилась после F5', (await page.locator('.result-hero').count()) === 1);

  // SERVICE_BUSY: фронтенд должен показать сообщение сервиса, а не общую ошибку.
  await page.locator('.new-scenario').click();
  await page.route('**/api/v1/generations', route => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ error: { code: 'SERVICE_BUSY', message: 'Сервис занят: идёт 30 генераций и ещё 100 ждут. Попробуйте позже.', field: null, retryable: true } }),
  }));
  await page.getByRole('button', { name: /Сотворить сценарий/ }).click();
  const busyText = await page.locator('[role="alert"]').innerText();
  record('SERVICE_BUSY показывается пользователю', busyText.includes('Сервис занят'), busyText);
  await page.unroute('**/api/v1/generations');
} catch (error) {
  record('Критическая ошибка сценария', false, String(error));
  await page.screenshot({ path: 'C:\\Users\\user\\AppData\\Local\\Temp\\opencode\\ui_regression_fail.png', fullPage: true }).catch(() => {});
} finally {
  writeFileSync(OUT, JSON.stringify(results, null, 2), 'utf-8');
  console.log('SAVED', OUT);
  await browser.close();
}
