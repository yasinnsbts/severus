"""Общий каталог событий проекта, справочники сервиса, источники и фрагменты, профиль школы."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .settings import Settings, read_json, sha256_file

EVENT_CATEGORIES = {"federal", "regional", "school", "cultural"}
AGE_GROUPS = {"1-4", "5-8", "9-11"}
FORMATS = {"class_hour", "school_event", "interactive_lesson"}
REQUIRED_EVENT_FIELDS = (
    "id", "title", "category", "date_rule", "supported_age_groups", "supported_formats",
    "educational_goals", "values", "age_appropriateness_notes", "facts_to_verify", "regional_topics",
)


class CatalogError(ValueError):
    """Общий каталог не найден или не прошёл проверку сервиса."""

    def __init__(self, catalog_dir: Path, problems: list[str]):
        """Сохраняет все найденные проблемы и формирует сообщение для куратора каталога."""
        self.problems = problems
        lines = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"Каталог {catalog_dir} не прошёл проверку сервиса ({len(problems)}):\n{lines}")


@dataclass
class Catalog:
    events: dict[str, dict[str, Any]]
    values: dict[str, dict[str, Any]]
    dependencies: dict[str, dict[str, Any]]
    sources: dict[str, dict[str, Any]]
    fragments: dict[str, dict[str, Any]]
    school_profile: dict[str, Any]
    hashes: dict[str, str] = field(default_factory=dict)
    # Близкие праздники и названия региональных тем (`config/event_boundaries.json`).
    boundaries: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, settings: Settings) -> "Catalog":
        """Загружает общий каталог событий, справочники сервиса, источники и профиль школы и проверяет их согласованность.

        Карточки и источники читаются из общего каталога проекта (`settings.catalog_dir`):
        `events/<id>.json` и `sources/<id>.json` (поля `sources` и `fragments`).
        Справочники ценностей и зависимостей материалов принадлежат сервису: `catalog/values.json`,
        `catalog/dependencies.json` в корне сервиса.

        Исключения:
            CatalogError: если каталог не найден или не прошёл проверку; в сообщении перечислены все проблемы.
        """
        shared = settings.catalog_dir
        if not (shared / "events").is_dir():
            raise CatalogError(shared, [f"не найдена папка {shared / 'events'}; задайте CATALOG_DIR в .env"])
        hashes: dict[str, str] = {}
        events: dict[str, dict[str, Any]] = {}
        problems: list[str] = []
        for path in sorted((shared / "events").glob("*.json")):
            try:
                data = read_json(path)
            except ValueError as exc:
                problems.append(f"events/{path.name}: не читается как JSON ({exc})")
                continue
            events[data.get("id", path.stem)] = data
            hashes[f"severus/catalog/events/{path.name}"] = sha256_file(path)

        own = settings.root / "catalog"
        values_path = own / "values.json"
        deps_path = own / "dependencies.json"
        values = {v["value_id"]: v for v in read_json(values_path)["values"]}
        deps = {d["id"]: d for d in read_json(deps_path)["items"]}
        hashes["catalog/values.json"] = sha256_file(values_path)
        hashes["catalog/dependencies.json"] = sha256_file(deps_path)

        sources: dict[str, dict[str, Any]] = {}
        fragments: dict[str, dict[str, Any]] = {}
        for path in sorted((shared / "sources").glob("*.json")):
            data = read_json(path)
            hashes[f"severus/catalog/sources/{path.name}"] = sha256_file(path)
            for src in data.get("sources", []):
                sources[src["source_id"]] = src
            for frag in data.get("fragments", []):
                fragments[frag["fragment_id"]] = frag

        profile_path = settings.school_profile_file
        profile = read_json(profile_path) if profile_path.is_file() else {}
        if profile_path.is_file():
            hashes["config/school_profile.json"] = sha256_file(profile_path)

        boundaries_path = settings.root / "config" / "event_boundaries.json"
        boundaries = read_json(boundaries_path) if boundaries_path.is_file() else {}
        if boundaries_path.is_file():
            hashes["config/event_boundaries.json"] = sha256_file(boundaries_path)

        catalog = cls(events, values, deps, sources, fragments, profile, hashes, boundaries)
        problems += catalog.integrity_problems(settings.root / "prompts")
        if problems:
            raise CatalogError(shared, problems)
        return catalog

    def integrity_problems(self, prompts_dir: Path | None = None) -> list[str]:
        """Проверяет все карточки каталога: каждая карточка в `events/` - событие, доступное фронтенду и генератору.

        Возвращает список всех найденных проблем, чтобы куратор видел их сразу, а не по одной.
        """
        problems: list[str] = []
        for eid, event in sorted(self.events.items()):
            where = f"events/{eid}.json"
            for key in REQUIRED_EVENT_FIELDS:
                if key not in event:
                    problems.append(f"{where}: нет поля {key}")
            if event.get("id") != eid:
                problems.append(f"{where}: id не совпадает с именем файла")
            if event.get("category") not in EVENT_CATEGORIES:
                problems.append(f"{where}: category должна быть одной из {sorted(EVENT_CATEGORIES)}")
            groups = event.get("supported_age_groups") or []
            if not groups or not set(groups) <= AGE_GROUPS:
                problems.append(f"{where}: supported_age_groups пустой или содержит неизвестные группы")
            formats = event.get("supported_formats") or []
            if not formats or not set(formats) <= FORMATS:
                problems.append(f"{where}: supported_formats пустой или содержит неизвестные форматы")
            goals = event.get("educational_goals")
            if not isinstance(goals, list) or not 1 <= len(goals) <= 3 or not all(isinstance(g, str) and g.strip() for g in goals):
                problems.append(f"{where}: educational_goals - от 1 до 3 непустых строк")
            vals = event.get("values")
            if not isinstance(vals, list) or not 1 <= len(vals) <= 3:
                problems.append(f"{where}: values - от 1 до 3 ценностей")
            else:
                for value_id in vals:
                    if value_id not in self.values:
                        problems.append(f"{where}: неизвестная ценность {value_id!r}, допустимы {sorted(self.values)}")
            notes = event.get("age_appropriateness_notes")
            if isinstance(notes, dict):
                for group in groups:
                    if not isinstance(notes.get(group), str) or not notes[group].strip():
                        problems.append(f"{where}: нет возрастного совета для группы {group}")
            facts = event.get("facts_to_verify")
            if "facts_to_verify" in event and (not isinstance(facts, list) or not all(isinstance(f, str) and f.strip() for f in facts)):
                problems.append(f"{where}: facts_to_verify - список непустых строк")
            topics = event.get("regional_topics")
            if "regional_topics" in event and (not isinstance(topics, list) or not all(isinstance(x, str) and "/" in x for x in topics)):
                problems.append(f"{where}: regional_topics - список строк вида RU-SVE/<тема>")
            rule = event.get("date_rule")
            if "date_rule" in event and not (isinstance(rule, dict) and (rule.get("note") or rule.get("value"))):
                problems.append(f"{where}: date_rule без значения и описания")
            if prompts_dir is not None and not (prompts_dir / "events" / f"{eid}.md").is_file():
                problems.append(f"{where}: в сервисе нет блока prompts/events/{eid}.md")
        return problems

    def active_events(self) -> dict[str, dict[str, Any]]:
        """Возвращает события, доступные для генерации: все карточки общего каталога.

        Тот же список отдаёт фронтенду общий бэкенд (`GET /api/v1/catalog/events`), поэтому
        любое событие, которое видит педагог, генератор принимает.
        """
        return dict(self.events)

    def verified_fragments(self, event_id: str, region_id: str, cultural_context: bool = True) -> list[dict[str, Any]]:
        """Проверенные фрагменты для события (ТЗ 17.2). Только status=verified."""
        event = self.events.get(event_id, {})
        topics = {t.split("/", 1)[-1] for t in event.get("regional_topics", [])}
        result = []
        for frag in self.fragments.values():
            if frag.get("verification_status", frag.get("status")) != "verified":
                continue
            if region_id not in frag.get("regions", [region_id]):
                continue
            by_event = event_id in frag.get("events", [])
            by_topic = bool(topics.intersection(frag.get("topics", [])))
            if by_topic and not cultural_context:
                continue
            if by_event or by_topic:
                result.append(frag)
        return result

    @staticmethod
    def profile_has_known_values(profile: dict[str, Any]) -> bool:
        """Проверяет, содержит ли профиль школы данные, которые нужно учитывать при персонализации.

        Параметры:
            `profile`.

        Возвращает:
            bool.
        """
        keys = ("settlement_type", "small_school", "local_context_notes")
        return any(profile.get(k) not in (None, "", False) for k in keys) or bool(profile.get("mixed_grade_classes"))


def path_or_none(path: Path) -> Path | None:
    """Возвращает путь, если он существует, иначе возвращает None.

    Параметры:
        `path`.

    Возвращает:
        Path | None.
    """
    return path if path.exists() else None