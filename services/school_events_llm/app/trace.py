"""Трассы генерации (ТЗ 19, упрощённо для прототипа).

data/runs/runs.jsonl                - журнал: одна строка на каждую генерацию (статус, время, вызовы, токены)
data/runs/<job_id>/
  input.json, normalized_request.json, metadata.json, concepts.json, final_result.json
  events.jsonl                      - события этапов и вызовов (одна JSON-запись на строку)
  calls/call_0001/                  - manifest.json, messages.json, prompt.md, response.raw.txt, response.parsed.json,
                                      response.reasoning.txt (если включены рассуждения)
  variants/v1/variant_package.json  - внутренний результат (контракт 03) и validation.json
Секреты (известные значения ключей из .env) маскируются во всех файлах.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Общий журнал runs.jsonl пишут все генерации процесса: строки не должны перемешиваться.
_RUN_LOG_LOCK = threading.Lock()


class RunTrace:
    def __init__(self, run_dir: Path | None, *, full_prompts: bool = True, full_responses: bool = True, secrets: list[str] | None = None):
        """Создаёт трассировщик запуска, настраивает каталог артефактов и список секретов для маскировки.

        Параметры:
            `run_dir`, `full_prompts`, `full_responses`, `secrets`.
        """
        self.run_dir = run_dir
        self.full_prompts = full_prompts
        self.full_responses = full_responses
        self.secrets = [s for s in (secrets or []) if s]
        self._call_seq = 0
        # Варианты одной генерации идут в разных потоках (`max_parallel_variants`): номера вызовов
        # и строки events.jsonl не должны повторяться и перемешиваться.
        self._lock = threading.Lock()
        if run_dir:
            (run_dir / "calls").mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        """Показывает, включено ли сохранение трассы для текущего запуска.

        Возвращает:
            bool.
        """
        return self.run_dir is not None

    def _redact(self, text: str) -> tuple[str, bool]:
        """Удаляет известные секреты из текста перед записью диагностического артефакта.

        Параметры:
            `text`.

        Возвращает:
            tuple[str, bool].
        """
        changed = False
        for secret in self.secrets:
            if secret in text:
                text = text.replace(secret, "***REDACTED***")
                changed = True
        return text, changed

    def write_text(self, rel: str, text: str) -> bool:
        """Сохраняет текстовый артефакт трассы с предварительной маскировкой секретов.

        Параметры:
            `rel`, `text`.

        Возвращает:
            bool.
        """
        if not self.run_dir:
            return False
        text, changed = self._redact(text)
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)  # атомарная запись
        return changed

    def write_json(self, rel: str, obj: Any) -> bool:
        """Сохраняет JSON-артефакт трассы в UTF-8.

        Параметры:
            `rel`, `obj`.

        Возвращает:
            bool.
        """
        return self.write_text(rel, json.dumps(obj, ensure_ascii=False, indent=2, default=str))

    def event(self, event_type: str, **fields: Any) -> None:
        """Добавляет одно структурированное событие в JSONL-журнал запуска.

        Параметры:
            `event_type`, `**fields`.

        Возвращает:
            None.
        """
        if not self.run_dir:
            return
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event_type": event_type, **fields}
        line, _ = self._redact(json.dumps(record, ensure_ascii=False, default=str))
        with self._lock, (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def append_run_log(self, record: dict[str, Any]) -> None:
        """Добавляет строку о завершённой генерации в общий журнал `runs.jsonl` рядом с папками прогонов.

        Журнал пишется только при включённой трассе. Ошибка записи журнала не должна ломать генерацию.

        Параметры:
            `record`: сводка прогона.
        """
        if not self.run_dir:
            return
        line, _ = self._redact(json.dumps(record, ensure_ascii=False, default=str))
        try:
            with _RUN_LOG_LOCK, (self.run_dir.parent / "runs.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def next_call_id(self) -> str:
        """Выдаёт следующий уникальный идентификатор LLM-вызова внутри запуска.

        Возвращает:
            str.
        """
        with self._lock:
            self._call_seq += 1
            return f"call_{self._call_seq:04d}"

    def save_call(self, call_id: str, *, manifest: dict[str, Any], messages: list[dict[str, str]] | None,
                  prompt_md: str | None, raw: str | None, parsed: Any, reasoning: str | None = None) -> None:
        """Сохраняет манифест, сообщения, сырой ответ и разобранный результат одного LLM-вызова.

        Параметры:
            `call_id`, `manifest`, `messages`, `prompt_md`, `raw`, `parsed`.

        Возвращает:
            None.
        """
        if not self.run_dir:
            return
        base = f"calls/{call_id}"
        redacted = False
        if messages is not None and self.full_prompts:
            redacted |= self.write_json(f"{base}/messages.json", messages)
            redacted |= self.write_text(f"{base}/prompt.md", prompt_md or "")
        if raw is not None and self.full_responses:
            redacted |= self.write_text(f"{base}/response.raw.txt", raw)
        if reasoning and self.full_responses:
            redacted |= self.write_text(f"{base}/response.reasoning.txt", reasoning)
        if parsed is not None:
            self.write_json(f"{base}/response.parsed.json", parsed)
        self.write_json(f"{base}/manifest.json", {**manifest, "secret_redacted": redacted})