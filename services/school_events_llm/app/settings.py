"""Пути, переменные окружения и загрузка конфигурации сервиса."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> dict[str, str]:
    """Простой парсер .env (KEY=VALUE, комментарии #). Без внешних зависимостей."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def read_json(path: Path) -> Any:
    """Читает JSON-файл в кодировке UTF-8 и возвращает его содержимое как Python-объект.

    Параметры:
        `path`.

    Возвращает:
        Any.
    """
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path) -> str:
    """Вычисляет SHA-256 содержимого файла для контроля версии и воспроизводимости.

    Параметры:
        `path`.

    Возвращает:
        str.
    """
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    """Вычисляет SHA-256 строки в UTF-8 для манифестов и трассировки.

    Параметры:
        `text`.

    Возвращает:
        str.
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Settings:
    root: Path = SERVICE_ROOT
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None, env_file: Path | None = None) -> "Settings":
        """Загружает настройки из `.env` и переменных окружения процесса; переменные процесса имеют приоритет.

        Параметры:
            `root`, `env_file`.

        Возвращает:
            'Settings'.
        """
        root = root or SERVICE_ROOT
        env = load_dotenv(env_file or root / ".env")
        # переменные процесса имеют приоритет над .env
        for key, value in os.environ.items():
            if key.isupper():
                env[key] = value
        return cls(root=root, env=env)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Возвращает значение настройки с учётом значения по умолчанию.

        Параметры:
            `key`, `default`.

        Возвращает:
            str | None.
        """
        value = self.env.get(key)
        return value if value not in (None, "") else default

    def flag(self, key: str, default: bool = False) -> bool:
        """Преобразует строковую переменную окружения в логическое значение.

        Параметры:
            `key`, `default`.

        Возвращает:
            bool.
        """
        value = self.get(key)
        if value is None:
            return default
        return value.strip().lower() in ("1", "true", "yes", "on")

    def path(self, key: str, default: str) -> Path:
        """Преобразует настройку пути в абсолютный путь относительно корня сервиса.

        Параметры:
            `key`, `default`.

        Возвращает:
            Path.
        """
        value = Path(self.get(key, default) or default)
        return value if value.is_absolute() else (self.root / value)

    # Пути к файлам конфигурации.
    @property
    def models_file(self) -> Path:
        """Возвращает путь к конфигурации моделей `config/models.json`.

        Возвращает:
            Path.
        """
        return self.root / "config" / "models.json"

    @property
    def generation_file(self) -> Path:
        """Возвращает путь к конфигурации этапов генерации `config/generation.json`.

        Возвращает:
            Path.
        """
        return self.root / "config" / "generation.json"

    @property
    def defaults_file(self) -> Path:
        """Возвращает путь к файлу серверных значений по умолчанию входного запроса."""
        return self.path("REQUEST_DEFAULTS_FILE", "config/request_defaults.json")

    @property
    def experiment_modes_file(self) -> Path:
        """Возвращает путь к конфигурации состава prompt-блоков для экспериментальных режимов."""
        return self.root / "config" / "experiment_modes.json"

    @property
    def school_profile_file(self) -> Path:
        """Возвращает путь к серверному профилю школы с учётом переменной окружения.

        Возвращает:
            Path.
        """
        return self.path("SCHOOL_PROFILE_FILE", "config/school_profile.json")

    @property
    def catalog_dir(self) -> Path:
        """Возвращает путь к общему каталогу событий проекта (по умолчанию `severus/catalog/`).

        Сервис только читает каталог: карточки `events/*.json` и источники `sources/*.json`.
        Справочники сервиса (`catalog/values.json`, `catalog/dependencies.json`) лежат в корне сервиса.
        """
        return self.path("CATALOG_DIR", "../../catalog").resolve()

    @property
    def data_dir(self) -> Path:
        """Возвращает каталог для локальных трасс, результатов и служебных данных.

        Возвращает:
            Path.
        """
        return self.path("DATA_DIR", "data")

    def models(self) -> dict[str, Any]:
        """Загружает конфигурацию доступных LLM-провайдеров и моделей.

        Возвращает:
            dict[str, Any].
        """
        return read_json(self.models_file)

    def generation(self) -> dict[str, Any]:
        """Загружает настройки конвейера генерации и параметров LLM-этапов."""
        return read_json(self.generation_file)

    def service(self) -> dict[str, Any]:
        """Настройки параллельной работы сервиса `config/service.json`; без файла - значения по умолчанию."""
        defaults = {"max_parallel_generations": 30, "max_waiting_generations": 100, "max_parallel_llm_requests": 30,
                    "max_parallel_variants": 3, "local_model_max_parallel": 1, "llm_slot_wait_seconds": 600,
                    "results_keep_hours": 24, "llm_cache_bypass": True}
        path = self.root / "config" / "service.json"
        data = read_json(path) if path.is_file() else {}
        return {**defaults, **{k: v for k, v in data.items() if k in defaults}}

    def experiment_modes(self) -> dict[str, Any]:
        """Загружает конфигурацию экспериментальных режимов full и universal."""
        return read_json(self.experiment_modes_file)

    def request_defaults(self) -> dict[str, Any]:
        """Загружает серверные значения по умолчанию для контракта 01.

        Возвращает:
            dict[str, Any].
        """
        return read_json(self.defaults_file)

    def active_model_key(self, override: str | None = None) -> str:
        """Определяет ключ активной модели с учётом явного переопределения и конфигурации.

        Параметры:
            `override`.

        Возвращает:
            str.
        """
        if override:
            return override
        key = self.get("ACTIVE_MODEL") or self.models().get("default_model")
        if not key:
            raise RuntimeError("Не задана модель: укажите ACTIVE_MODEL в .env или default_model в config/models.json")
        return key

    def secret_values(self) -> list[str]:
        """Известные секреты для маскировки в трассах."""
        secrets = []
        for key, value in self.env.items():
            if value and any(part in key for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                if len(value) >= 6:
                    secrets.append(value)
        return secrets