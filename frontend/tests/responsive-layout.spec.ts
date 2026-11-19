
import { test, expect } from '@playwright/test';

for (const width of [1440, 768, 390]) {
  test(`Конструктор помещается на экран ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('http://localhost:5173/');

    await page.getByRole('button', { name: 'Создать сценарий' }).click();

    await expect(
      page.getByText('КОНСТРУКТОР МЕРОПРИЯТИЯ')
    ).toBeVisible();

    const problems = await page.locator(
      '.page-content button:visible, .form-aside:visible, .panel:visible'
    ).evaluateAll(elements => {
      return elements
        .filter(element => {
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && (
            rect.left < -1 ||
            rect.right > window.innerWidth + 1
          );
        })
        .map(element => ({
          element: element.tagName,
          className: element.className,
          text: element.textContent?.trim().slice(0, 60),
        }));
    });

    expect(problems).toEqual([]);
  });
}
