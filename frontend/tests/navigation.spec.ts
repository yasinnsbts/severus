
import { test, expect } from '@playwright/test';

test('Переход с главной страницы в конструктор', async ({ page }) => {
  await page.goto('http://localhost:5173/');

  await expect(
    page.getByRole('button', { name: 'Создать сценарий' })
  ).toBeVisible();

  await page.getByRole('button', { name: 'Создать сценарий' }).click();

  await expect(
    page.getByText('КОНСТРУКТОР МЕРОПРИЯТИЯ')
  ).toBeVisible();
});
