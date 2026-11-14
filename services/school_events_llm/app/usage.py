"""Подсчёт токенов за генерацию: вход и выход по каждому вызову модели, итог и разбивка по этапам."""

from __future__ import annotations

import threading
from typing import Any


class TokenTally:
    """Складывает `usage` из ответов провайдера.

    Учитываются и ответы, которые не прошли схему: токены на них потрачены.
    Если провайдер не вернул `usage` хотя бы для одного ответа, итог помечается `complete: false`.
    """

    def __init__(self) -> None:
        self.prompt = 0
        self.completion = 0
        self.calls = 0
        self.calls_without_usage = 0
        self.by_stage: dict[str, dict[str, int]] = {}
        # Варианты одной генерации складывают токены из разных потоков (`max_parallel_variants`).
        self._lock = threading.Lock()

    def add(self, stage: str, usage: dict[str, Any] | None) -> None:
        """Добавляет один ответ модели.

        Параметры:
            stage: этап конвейера; usage: поле `usage` ответа провайдера или None.
        """
        with self._lock:
            self.calls += 1
            row = self.by_stage.setdefault(stage, {"calls": 0, "prompt": 0, "completion": 0})
            row["calls"] += 1
            if not isinstance(usage, dict):
                self.calls_without_usage += 1
                return
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            self.prompt += prompt
            self.completion += completion
            row["prompt"] += prompt
            row["completion"] += completion

    def totals(self) -> dict[str, Any]:
        """Итог без разбивки: для вывода CLI."""
        return {"prompt": self.prompt, "completion": self.completion, "total": self.prompt + self.completion,
                "complete": self.calls_without_usage == 0}

    def as_dict(self) -> dict[str, Any]:
        """Итог с разбивкой по этапам: для `metadata.json` и журнала прогонов."""
        return {**self.totals(), "calls_without_usage": self.calls_without_usage, "by_stage": self.by_stage}