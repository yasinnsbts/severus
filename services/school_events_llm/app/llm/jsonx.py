"""Извлечение JSON из ответа модели: вырезка рассуждений, Markdown-обёрток и мусора."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_THINK_OPEN = re.compile(r"^.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


class JSONExtractionError(ValueError):
    pass


def strip_reasoning(text: str) -> tuple[str, bool]:
    """Удаляет блоки <think>…</think> (в т. ч. незакрытое начало). Возвращает (текст, был_ли_блок)."""
    had = bool(_THINK.search(text)) or "</think>" in text.lower()
    text = _THINK.sub("", text)
    if "</think>" in text.lower():
        text = _THINK_OPEN.sub("", text)
    return text.strip(), had


def _balanced_object(text: str) -> str | None:
    """Находит первый сбалансированный JSON-объект в произвольном тексте с учётом строк и экранирования.

    Параметры:
        `text`.

    Возвращает:
        str | None.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find("{", start + 1)
    return None


def _strip_comments(text: str) -> str:
    """Убирает комментарии `// …` вне строк: модели иногда дописывают их прямо в JSON."""
    out: list[str] = []
    in_str = escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch == "/" and text[i + 1:i + 2] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


MAX_QUOTE_REPAIRS = 30

# Строка закрыта экранированной кавычкой, и следующий ключ тоже в экранированных кавычках:
# `"teacher_script": "…следующим этапом будет презентация\",\n\"pupil_actions\": [` (BUG-21, Новый год 14.11:
# GigaChat трижды подряд так закрыл реплику, `pupil_actions` и `role_ids` уходили внутрь текста, и блок
# не проходил схему). Ключ из латиницы с подчёркиваниями после `\",` в русском тексте не встречается.
_ESCAPED_KEY = re.compile(r'(?<!\\)\\"\s*,\s*(?:\\n\s*)*\\?"([a-z][a-z0-9_]*)\\?"\s*:')


def _unescape_key_quotes(text: str) -> str:
    """Возвращает на место кавычки, которыми модель закрыла строку и открыла следующий ключ (`_ESCAPED_KEY`)."""
    return _ESCAPED_KEY.sub(lambda m: f'",\n"{m.group(1)}":', text)


def _merge_stray_string(text: str, pos: int) -> str | None:
    """Строка без ключа внутри объекта: `"teacher_script": "Реплика 1", "Реплика 2", "pupil_actions": [...]`.

    GigaChat так разбивает длинный текст на абзацы. `pos` - место ошибки «Expecting ':'» сразу после
    такой строки; если за ней `,` или `}`, а перед ней `"значение",`, строка присоединяется к значению
    через перенос строки. Иначе - `None` (это другая ошибка, например неэкранированная кавычка).
    """
    if pos >= len(text) or text[pos] not in ",}":
        return None
    close = text.rfind('"', 0, pos)
    if close <= 0 or text[close + 1:pos].strip():
        return None
    start = close - 1
    while start >= 0 and not (text[start] == '"' and text[start - 1] != "\\"):
        start -= 1
    match = re.search(r'(?<!\\)"\s*,\s*$', text[:start])
    if start <= 0 or not match:
        return None
    return text[:match.start()] + "\\n" + text[start + 1:]


def _loads_lenient(text: str) -> Any:
    """`json.loads` с поправками на типичные ошибки моделей.

    - Управляющие символы (перенос строки, табуляция) внутри строк допускаются (`strict=False`).
    - Запятая перед `}`/`]` убирается.
    - Строка, закрытая экранированной кавычкой перед следующим ключом (`…класса\\",\\n\\"pupil_actions\\": [`),
      закрывается обычной (`_unescape_key_quotes`).
    - Неэкранированная кавычка внутри строки («…дружно!" (Через 10 минут…»): если разбор ломается
      сразу после неё с ожиданием `,` или `:`, кавычка экранируется и разбор повторяется
      (не больше `MAX_QUOTE_REPAIRS` раз). Результат всё равно проходит проверку схемы этапа.
    - Строки без ключа после значения-строки (текст, разбитый на абзацы) присоединяются к этому значению
      (`_merge_stray_string`). Проверяется раньше кавычки: иначе экранирование склеит их со следующим ключом.
    """
    text = _unescape_key_quotes(re.sub(r",\s*([}\]])", r"\1", text))
    for _ in range(MAX_QUOTE_REPAIRS + 1):
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError as exc:
            if not (exc.msg.startswith("Expecting ',' delimiter") or exc.msg.startswith("Expecting ':' delimiter")):
                raise
            if exc.msg.startswith("Expecting ':' delimiter"):
                merged = _merge_stray_string(text, exc.pos)
                if merged is not None:
                    text = merged
                    continue
            quote = text.rfind('"', 0, exc.pos)
            if quote <= 0 or text[quote - 1] == "\\":
                raise
            text = text[:quote] + '\\"' + text[quote + 1:]
    return json.loads(text, strict=False)


def extract_json(text: str) -> dict[str, Any]:
    """Извлекает первый корректный JSON-объект из сырого текстового ответа модели.

    Параметры:
        `text`.

    Возвращает:
        dict[str, Any].
    """
    cleaned, _ = strip_reasoning(text)
    candidates = [cleaned]
    candidates += [m.group(1).strip() for m in _FENCE.finditer(cleaned)]
    obj = _balanced_object(cleaned)
    if obj:
        candidates.append(obj)
    last_error: Exception | None = None
    for cand in candidates:
        try:
            value = json.loads(cand)
        except json.JSONDecodeError as exc:
            last_error = exc
            try:
                value = _loads_lenient(_strip_comments(cand))
            except json.JSONDecodeError:
                continue
        if isinstance(value, dict):
            return value
    raise JSONExtractionError(f"В ответе модели не найден корректный JSON-объект ({last_error})")