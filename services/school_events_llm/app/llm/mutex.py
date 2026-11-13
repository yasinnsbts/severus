"""Межпроцессная блокировка локальной модели (ТЗ 4.7).

- Очередь внутри сервиса - в `limits.py`: число одновременных обращений к локальной модели
  задаёт `local_model_max_parallel` в `config/service.json` (по умолчанию 1 - строго по одному).
- Межпроцессная блокировка - опция для случая, когда та же локальная модель используется
  не только этим сервисом. По умолчанию выключена (`LOCAL_LLM_MUTEX_ENABLED=false`).
  Реализована lock-файлом (`LOCAL_LLM_MUTEX_PATH`) и одинаково работает на любой ОС.
Блокировка берётся только на время одного вызова модели.
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class MutexTimeout(TimeoutError):
    pass


def _try_lock(fh) -> None:
    """Пытается неблокирующе захватить межпроцессную блокировку lock-файла.

    Параметры:
        `fh`.

    Возвращает:
        None.
    """
    if sys.platform == "win32":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fh) -> None:
    """Освобождает ранее захваченную межпроцессную блокировку lock-файла.

    Параметры:
        `fh`.

    Возвращает:
        None.
    """
    if sys.platform == "win32":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def _file_lock(path: Path, wait_seconds: float) -> Iterator[dict]:
    """Предоставляет контекст межпроцессной блокировки через общий lock-файл с таймаутом.

    Параметры:
        `path`, `wait_seconds`.

    Возвращает:
        Iterator[dict].
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    # На Windows msvcrt.locking блокирует существующий байт файла.
    # Один служебный байт делает поведение одинаковым для пустого и существующего lock-файла.
    fh.seek(0, 2)
    if fh.tell() == 0:
        fh.write(b"0")
        fh.flush()
    deadline = time.monotonic() + wait_seconds
    try:
        while True:
            try:
                _try_lock(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise MutexTimeout(f"Локальная модель занята другой программой дольше {wait_seconds} с ({path})")
                time.sleep(0.2)
        try:
            yield {"kind": "file", "path": str(path)}
        finally:
            _unlock(fh)
    finally:
        fh.close()


@contextmanager
def local_llm_lock(path: Path, wait_seconds: float, enabled: bool = False) -> Iterator[dict]:
    """Межпроцессная блокировка (если enabled). Возвращает сведения с `wait_ms`.

    Очередь внутри процесса берётся раньше, в `limits.llm_request_slot(local=True)`; здесь при
    выключенной блокировке ничего не ждём (`kind=queue_only`).
    """
    started = time.monotonic()
    if enabled:
        with _file_lock(path, wait_seconds) as info:
            info["wait_ms"] = int((time.monotonic() - started) * 1000)
            yield info
    else:
        yield {"kind": "queue_only", "wait_ms": 0}


def lock_from_settings(settings) -> dict:
    """Строит параметры блокировки локальной LLM из переменных окружения.

    Параметры:
        `settings`.

    Возвращает:
        dict.
    """
    return {
        "path": settings.path("LOCAL_LLM_MUTEX_PATH", "data/locks/lm_studio.lock"),
        "wait_seconds": float(settings.get("LOCAL_LLM_MUTEX_WAIT_SECONDS", "120")),
        "enabled": settings.flag("LOCAL_LLM_MUTEX_ENABLED", False),
    }


__all__ = ["MutexTimeout", "local_llm_lock", "lock_from_settings"]