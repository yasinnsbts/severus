"""Пределы одновременных обращений к модели внутри процесса сервиса.

Настройки - в `config/service.json`:
- `max_parallel_llm_requests` - общий предел одновременных обращений к любой модели;
- `local_model_max_parallel` - отдельный предел для локальной модели (LM Studio): одна видеокарта
  обычно обслуживает одно обращение за раз, остальные ждут здесь, а не падают по таймауту.

Пределы общие для всех задач процесса: каждая генерация берёт место на время одного обращения
к модели и сразу его отдаёт. Пока занято меньше мест, чем предел, обращение идёт сразу.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator

DEFAULTS = {"max_parallel_llm_requests": 30, "local_model_max_parallel": 1, "llm_slot_wait_seconds": 600}


class SlotTimeout(RuntimeError):
    """Свободное место для обращения к модели не появилось за отведённое время."""


class _Slots:
    """Семафор с учётом занятых мест: нужен для отчёта о нагрузке и для тестов."""

    def __init__(self, size: int):
        self.size = max(1, int(size))
        self._sem = threading.BoundedSemaphore(self.size)
        self._lock = threading.Lock()
        self.busy = 0
        self.peak = 0

    @contextmanager
    def take(self, wait_seconds: float) -> Iterator[int]:
        started = time.monotonic()
        if not self._sem.acquire(timeout=wait_seconds):
            raise SlotTimeout(f"Все {self.size} мест для обращений к модели заняты дольше {int(wait_seconds)} с")
        with self._lock:
            self.busy += 1
            self.peak = max(self.peak, self.busy)
        try:
            yield int((time.monotonic() - started) * 1000)
        finally:
            with self._lock:
                self.busy -= 1
            self._sem.release()


_config_lock = threading.Lock()
_llm = _Slots(DEFAULTS["max_parallel_llm_requests"])
_local = _Slots(DEFAULTS["local_model_max_parallel"])
_wait_seconds = float(DEFAULTS["llm_slot_wait_seconds"])


def configure(config: dict | None) -> None:
    """Применяет настройки из `config/service.json`. Пределы пересоздаются, только если число изменилось."""
    global _llm, _local, _wait_seconds
    cfg = {**DEFAULTS, **(config or {})}
    with _config_lock:
        if _llm.size != int(cfg["max_parallel_llm_requests"]):
            _llm = _Slots(cfg["max_parallel_llm_requests"])
        if _local.size != int(cfg["local_model_max_parallel"]):
            _local = _Slots(cfg["local_model_max_parallel"])
        _wait_seconds = float(cfg["llm_slot_wait_seconds"])


@contextmanager
def llm_request_slot(local: bool = False) -> Iterator[int]:
    """Место для одного обращения к модели. Возвращает, сколько миллисекунд пришлось ждать.

    Для локальной модели сначала берётся общее место, затем место локальной модели.
    """
    with _llm.take(_wait_seconds) as waited:
        if local:
            with _local.take(_wait_seconds) as waited_local:
                yield waited + waited_local
        else:
            yield waited


def load() -> dict[str, int]:
    """Текущая занятость мест: для отчёта о нагрузке сервиса."""
    return {"llm_requests_busy": _llm.busy, "llm_requests_limit": _llm.size, "llm_requests_peak": _llm.peak,
            "local_model_busy": _local.busy, "local_model_limit": _local.size}


def wait_seconds() -> float:
    return _wait_seconds