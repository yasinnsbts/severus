
import { test, expect } from '@playwright/test';

test('Копирование сценариев и сброс состояния кнопки', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);

  await page.goto('http://localhost:5173/');

  await page.getByRole('button', { name: 'Создать сценарий' }).click();

  // Работаем только в демо-режиме.
  await page.getByRole('button', { name: 'Демо', exact: true }).click();

  // Генерируем два варианта сценария.
  // В текущем интерфейсе проверяем, что кнопка доступна.
  await page.getByRole('button', { name: 'Сотворить сценарий' }).click();

  await expect(
  page.getByRole('button', { name: 'Копировать сценарий' })
).toBeVisible({ timeout: 30000 });

  // Копирование первого варианта.
  await page.getByRole('button', { name: 'Копировать сценарий' }).click();

  await expect(
    page.getByRole('button', { name: 'Скопировано!' })
  ).toBeVisible();

  const firstText = await page.evaluate(() => navigator.clipboard.readText());

  expect(firstText).toContain('СЦЕНАРИЙ:');

  // Переключение вкладки сбрасывает состояние кнопки.
  await page.getByRole('button', { name: 'Материалы' }).click();

  await expect(
    page.getByRole('button', { name: 'Копировать сценарий' })
  ).toBeVisible();

  await page.getByRole('button', { name: 'Участники' }).click();

  await page.getByRole('button', { name: 'Копировать сценарий' }).click();

  const secondText = await page.evaluate(() => navigator.clipboard.readText());

  // Копирование полного сценария не зависит от выбранной вкладки.
  expect(secondText).toBe(firstText);
  // Переключаемся на второй вариант сценария.
await page.getByRole('button', { name: 'Вариант 2' }).click();

// После переключения кнопка снова должна предлагать копирование.
await expect(
  page.getByRole('button', { name: 'Копировать сценарий' })
).toBeVisible();

// Копируем второй вариант.
await page.getByRole('button', { name: 'Копировать сценарий' }).click();

await expect(
  page.getByRole('button', { name: 'Скопировано!' })
).toBeVisible();

const thirdText = await page.evaluate(() => navigator.clipboard.readText());

// Текст второго варианта должен отличаться от первого.
expect(thirdText).not.toBe(firstText);
expect(thirdText).toContain('Созвездие идей');

// Возвращаемся к первому варианту.
await page.getByRole('button', { name: 'Вариант 1' }).click();

await expect(
  page.getByRole('button', { name: 'Копировать сценарий' })
).toBeVisible();

await page.getByRole('button', { name: 'Копировать сценарий' }).click();

const restoredText = await page.evaluate(() => navigator.clipboard.readText());

// Первый вариант должен копироваться без изменений.
expect(restoredText).toBe(firstText);
});
