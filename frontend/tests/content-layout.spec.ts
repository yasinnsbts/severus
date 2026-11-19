
import { test, expect, type Page } from '@playwright/test';

const BASE_URL = 'http://localhost:5173/';

const longText = [
  'Подробные инструкции педагогу.',
  'Первый раздел: объясните правила и распределите роли.',
  'Второй раздел: организуйте обсуждение результатов.',
  'Третий раздел: предложите участникам сделать выводы.',
  'ОченьДлинноеСловоБезПробелов'.repeat(15),
].join('\n\n').repeat(8);

async function openSavedScenario(page: Page, empty: boolean) {
  await page.goto(BASE_URL);

  await page.evaluate(({ text, empty }) => {
    const form = {
      event_id: 'knowledge_day',
      region_id: 'RU-SVE',
      grade: 6,
      pupils_count: 25,
      duration_minutes: 45,
      format: 'class_hour',
      participants: {
        teachers_count: 1,
        parents_enabled: false,
        parents_count: 0,
        parent_roles: [],
        parent_audience_engagement: 'none',
      },
      resources: {
        projector: true,
        printer: false,
        internet: true,
        audio: true,
        room: 'classroom',
        available_materials: [],
      },
      teacher_preferences: {
        style: 'interactive',
        script_detail: 'standard',
        difficulty: 'standard',
        interaction_level: 'medium',
        group_work: true,
        preparation_effort: 'minimal',
        notes: null,
      },
      generation: { variants_count: 1, language: 'ru' },
    };

    const variant = {
      variant_id: 'v1',
      title: 'Проверочный сценарий',
      concept: {
        summary: 'Проверка отображения длинного содержимого',
        goal: 'Проверить адаптивность интерфейса',
        expected_outcomes: ['Проверка завершена'],
      },
      timeline: [{
        block_id: 'block_01',
        start_minute: 0,
        duration_minutes: 45,
        title: 'Подробный этап',
        purpose: 'Проверка текста',
        teacher_script: text,
        pupil_actions: ['Обсуждение', 'Подведение итогов'],
        material_ids: empty ? [] : ['m1'],
      }],
      materials: empty ? [] : [{
        material_id: 'm1',
        title: 'Материалы с несколькими разделами',
        content: text,
      }],
      roles: empty ? [] : [{
        role_id: 'teacher',
        title: 'Педагог',
        count: 1,
      }],
      teacher_instructions: ['Подготовьте материалы'],
      quality_report: { status: 'ok', issues: [] },
    };

    sessionStorage.setItem('severus_completed_generation', JSON.stringify({
      project: {
        schema_version: 'test',
        project_id: 'layout-test',
        status: 'completed',
        variants: [variant],
      },
      form,
      catalog: [{ id: 'knowledge_day', title: 'День знаний' }],
      options: {
        formats: [{ value: 'class_hour', label: 'Классный час' }],
        regions: [{ value: 'RU-SVE', label: 'Свердловская область' }],
        grades: [6],
        duration_minutes: [{ value: 45, label: '45 минут' }],
        rooms: [],
        teacher_preferences: { style: [], script_detail: [] },
      },
      mode: 'demo',
    }));
  }, { text: longText, empty });

  await page.reload();
  await expect(page.getByText('Проверочный сценарий')).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - window.innerWidth
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

for (const width of [1440, 768, 390]) {
  test(`Длинные тексты отображаются при ширине ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await openSavedScenario(page, false);

    await expect(page.locator('.teacher-script p')).toContainText(
      'Подробные инструкции педагогу'
    );

    await expectNoHorizontalOverflow(page);

    await page.getByRole('button', { name: 'Материалы' }).click();

    await expect(page.getByText('Материалы с несколькими разделами')).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const cardFits = await page.locator('.material-card').evaluate(element => {
      const card = element.getBoundingClientRect();
      const paragraph = element.querySelector('p')?.getBoundingClientRect();
      return !!paragraph &&
        paragraph.left >= card.left - 1 &&
        paragraph.right <= card.right + 1;
    });

    expect(cardFits).toBe(true);
  });

  test(`Пустые разделы не ломают страницу при ширине ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await openSavedScenario(page, true);

    await page.getByRole('button', { name: 'Материалы' }).click();
    await expect(page.getByText('Дополнительные материалы не требуются.')).toBeVisible();

    await page.getByRole('button', { name: 'Участники' }).click();
    await expect(page.getByText('Информация о ролях участников отсутствует.')).toBeVisible();

    await expectNoHorizontalOverflow(page);
  });
}

test('Предупреждения сервера не блокируют готовый сценарий', async ({ page }) => {
  await openSavedScenario(page, false);

  await page.evaluate(() => {
    const key = 'severus_completed_generation';
    const saved = sessionStorage.getItem(key);

    if (!saved) {
      throw new Error('Нет сохранённого тестового сценария');
    }

    const data = JSON.parse(saved);

    data.mode = 'api';
    data.project.generation_warnings = [
      { code: 'EVENT-MIXUP', message: 'Проверьте соответствие мероприятия' },
    ];

    data.project.variants[0].quality_report = {
      status: 'warning',
      issues: [
        {
          code: 'TECH-ID-IN-TEXT',
          severity: 'warning',
          message: 'В тексте обнаружен технический идентификатор',
        },
        {
          code: 'CULTURE-UNSOURCED',
          severity: 'warning',
          message: 'Проверьте культурно-исторические сведения',
        },
        {
          code: 'INNER-TIMING',
          severity: 'warning',
          message: 'Проверьте продолжительность этапов',
        },
      ],
    };

    sessionStorage.setItem(key, JSON.stringify(data));
  });

  await page.reload();

  await expect(
    page.getByText('Проверьте соответствие мероприятия')
  ).toBeVisible();

  await expect(
    page.getByText('В тексте обнаружен технический идентификатор')
  ).toBeVisible();

  await expect(
    page.getByText('Проверьте культурно-исторические сведения')
  ).toBeVisible();

  await expect(
    page.getByText('Проверьте продолжительность этапов')
  ).toBeVisible();

  await expect(
    page.getByText('Проверочный сценарий')
  ).toBeVisible();

  await expect(
    page.getByText(/Искусственный интеллект может допускать ошибки/)
  ).toBeVisible();
});
