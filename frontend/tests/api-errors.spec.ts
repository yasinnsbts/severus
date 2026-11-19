
import { test, expect } from '@playwright/test';

test('Ошибка 503 SERVICE_BUSY отображается пользователю', async ({ page }) => {
  // Подменяем только запуск генерации.
  await page.route('**/api/v1/generations', async route => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 'SERVICE_BUSY',
        message: 'Service is busy',
      }),
    });
  });

  await page.goto('http://localhost:5173/');

  await page.getByRole('button', { name: 'Создать сценарий' }).click();

  // Для перехода в API-режим подменяем каталог.
  await page.route('**/api/v1/catalog/events', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'knowledge_day',
          title: 'День знаний',
          supported_formats: ['class_hour'],
          supported_age_groups: ['5-8'],
        },
      ]),
    })
  );

  await page.route('**/api/v1/catalog/options', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        regions: [{ value: 'RU-SVE', label: 'Свердловская область' }],
        grades: [6],
        duration_minutes: [{ value: 45, label: '45 минут' }],
        formats: [{ value: 'class_hour', label: 'Классный час' }],
        rooms: [{ value: 'classroom', label: 'Класс' }],
        teacher_preferences: {
          style: [{ value: 'interactive', label: 'Интерактивный' }],
          script_detail: [{ value: 'standard', label: 'Стандартная' }],
        },
      }),
    })
  );

  await page.getByRole('button', { name: 'API', exact: true }).click();

  // Убеждаемся, что API-режим действительно включился.
  await expect(
    page.getByRole('button', { name: 'API', exact: true })
  ).toHaveClass(/active|selected|current/);

  await page.getByRole('button', { name: 'Сотворить сценарий' }).click();

  await expect(
    page.getByText('Сервис занят, попробуйте через минуту')
  ).toBeVisible({ timeout: 15000 });
});

test('Недоступность сервера показывает понятную ошибку', async ({ page }) => {
  await page.route('**/api/v1/catalog/**', route =>
    route.abort('failed')
  );

  await page.goto('http://localhost:5173/');

  await page.getByRole('button', { name: 'Создать сценарий' }).click();

  await page.getByRole('button', { name: 'API', exact: true }).click();

  await expect(
    page.getByText(/Нет соединения с сервером/)
  ).toBeVisible({ timeout: 15000 });

  // Не должно создаваться ложное впечатление,
  // что API успешно подключён.
  await expect(
    page.getByRole('button', { name: 'Сотворить сценарий' })
  ).toBeVisible();
});
