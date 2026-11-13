# UI-регрессия

Скрипт `regression.mjs` проверяет путь пользователя в браузере:

- форма и каталог из 14 событий;
- генерация и результат;
- F5 после результата и во время генерации;
- переключение вариантов;
- вкладки «Этапы», «Материалы», «Участники»;
- копирование;
- новый сценарий;
- `SERVICE_BUSY`.

## Что нужно

- запущенные Backend `:8000`, LLM-сервис `:8090`, Frontend `:5173`;
- Microsoft Edge;
- Playwright в `frontend/node_modules`:

```bash
cd frontend
npm install --no-save playwright
```

Playwright не входит в `package.json`, чтобы не менять продовые зависимости.

## Запуск

```bash
node qa/tests/ui/regression.mjs
```

Результат — JSON в `%TEMP%\opencode\ui_regression_results.json` и строки PASS/FAIL в консоли.

Если Edge установлен в другом месте, поправьте `EDGE` в начале скрипта.
