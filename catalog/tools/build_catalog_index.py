"""Проверка каталога и сборка производных файлов.

Источник истины - карточки catalog/events/<id>.json и файлы источников catalog/sources/<id>.json.
Скрипт проверяет их по схемам и пересобирает производные файлы, которые руками не правятся:

- catalog/events_catalog_RU-SVE.json - сводный JSON;
- catalog/catalog_index.csv - сводная таблица;
- поля verified_count и status в catalog/sources/<id>.json.

Запуск из корня репозитория:
    python catalog/tools/build_catalog_index.py           # проверить и пересобрать
    python catalog/tools/build_catalog_index.py --check   # только проверить, ничего не записывать

Код выхода 1, если найдены ошибки. Зависимостей нет, только стандартная библиотека Python 3.10+.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent
REGION_ID = "RU-SVE"
CSV_SEMANTICS = "listed_records_not_verified_publishers"


def read_json(path: Path):
    """Читает JSON-файл каталога в UTF-8 и возвращает десериализованный объект.

    Параметры:
        path: Путь к JSON-файлу.

    Возвращает:
        Десериализованное содержимое JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def validate(value, schema: dict, where: str, errors: list[str]) -> None:
    """Проверка по подмножеству JSON Schema, которое используется в схемах каталога."""
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: значение {value!r} не из списка {schema['enum']}")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: ожидалось {schema['const']!r}")
    types = schema.get("type")
    if types:
        types = types if isinstance(types, list) else [types]
        mapping = {"string": str, "array": list, "object": dict, "integer": int, "boolean": bool, "null": type(None)}
        if not any(isinstance(value, mapping[t]) and not (t == "integer" and isinstance(value, bool)) for t in types):
            errors.append(f"{where}: ожидался тип {'/'.join(types)}")
            return
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{where}: пустая строка")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{where}: {value!r} не соответствует шаблону {schema['pattern']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where}: нужно не меньше {schema['minItems']} элементов")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{where}: нужно не больше {schema['maxItems']} элементов")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append(f"{where}: элементы повторяются")
        for i, item in enumerate(value):
            if "items" in schema:
                validate(item, schema["items"], f"{where}[{i}]", errors)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: нет поля {key}")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                validate(item, props[key], f"{where}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{where}: лишнее поле {key}")
    for sub in schema.get("allOf", []):
        cond_errors: list[str] = []
        validate(value, sub.get("if", {}), where, cond_errors)
        if not cond_errors and "then" in sub:
            validate(value, sub["then"], where, errors)


def load() -> tuple[dict, dict, list[str]]:
    """Загружает карточки и источники каталога и собирает ошибки целостности.

    Возвращает:
        Кортеж из карточек событий, файлов источников и списка найденных ошибок.
    """
    errors: list[str] = []
    card_schema = read_json(CATALOG / "catalog_schema.json")
    sources_schema = read_json(CATALOG / "sources_schema.json")
    cards = {}
    for path in sorted((CATALOG / "events").glob("*.json")):
        card = read_json(path)
        validate(card, card_schema, f"events/{path.name}", errors)
        if card.get("id") != path.stem:
            errors.append(f"events/{path.name}: id {card.get('id')!r} не совпадает с именем файла")
        cards[path.stem] = card
    sources = {}
    for path in sorted((CATALOG / "sources").glob("*.json")):
        data = read_json(path)
        validate(data, sources_schema, f"sources/{path.name}", errors)
        sources[path.stem] = data

    all_source_ids: dict[str, str] = {}
    for eid, data in sources.items():
        for src in data.get("sources", []):
            sid = src.get("source_id")
            if sid in all_source_ids:
                errors.append(f"sources/{eid}.json: source_id {sid} уже есть в sources/{all_source_ids[sid]}.json")
            all_source_ids[sid] = eid
        own = {s.get("source_id") for s in data.get("sources", [])}
        seen_fragments = set()
        for i, frag in enumerate(data.get("fragments", [])):
            where = f"sources/{eid}.json fragments[{i}]"
            if frag.get("fragment_id") in seen_fragments:
                errors.append(f"{where}: повтор fragment_id {frag.get('fragment_id')}")
            seen_fragments.add(frag.get("fragment_id"))
            if frag.get("source_id") not in own:
                errors.append(f"{where}: source_id {frag.get('source_id')} нет в sources этого файла")
            if frag.get("verification_status") == "verified" and frag.get("verified_by") == frag.get("collected_by"):
                errors.append(f"{where}: собрал и проверил один и тот же человек")
            for ev in frag.get("events", []):
                if ev not in cards:
                    errors.append(f"{where}: неизвестное событие {ev}")

    for eid, card in cards.items():
        if eid not in sources:
            errors.append(f"events/{eid}.json: нет файла sources/{eid}.json")
        for sid in card.get("source_ids", []):
            if sid not in all_source_ids:
                errors.append(f"events/{eid}.json: source_id {sid} не найден в sources/")
        notes = card.get("age_appropriateness_notes", {})
        for group in card.get("supported_age_groups", []):
            if not notes.get(group):
                errors.append(f"events/{eid}.json: нет возрастного совета для группы {group}")
    return cards, sources, errors


def source_stats(card: dict, sources: dict) -> dict:
    """Считает показатели покрытия источниками для одной карточки события.

    Параметры:
        card: Карточка события.
        sources: Реестр файлов источников по событиям.

    Возвращает:
        Словарь агрегированных показателей источников и фрагментов.
    """
    by_id = {s["source_id"]: s for d in sources.values() for s in d.get("sources", [])}
    listed = [by_id[s] for s in card["source_ids"] if s in by_id]
    frags = [f for d in sources.values() for f in d.get("fragments", []) if card["id"] in f.get("events", [])]
    return {
        "source_count": len(listed),
        "verified_source_count": sum(1 for s in listed if s.get("verification_status") == "verified"),
        "verified_direct_content_count": sum(1 for s in listed if s.get("content_relevance_checked") and s.get("url_access_checked_in_this_revision")),
        "fragments_verified": sum(1 for f in frags if f.get("verification_status") == "verified"),
        "fragments_draft": sum(1 for f in frags if f.get("verification_status") == "draft"),
    }


def build(cards: dict, sources: dict) -> dict[Path, str]:
    """Формирует производные JSON/CSV-файлы из проверенного каталога.

    Параметры:
        cards: Карточки событий по ``event_id``.
        sources: Файлы источников по ``event_id``.

    Возвращает:
        Словарь ``путь -> текст``, который должен быть записан в производные файлы.
    """
    out: dict[Path, str] = {}
    for eid, data in sources.items():
        data = dict(data)
        verified = len({
            s["publisher"].strip().casefold()
            for s in data.get("sources", [])
            if s.get("verification_status") == "verified"
            and s.get("content_relevance_checked") is True
            and s.get("url_access_checked_in_this_revision") is True
            and isinstance(s.get("publisher"), str)
            and s["publisher"].strip()
        })
        data["verified_count"] = verified
        if "required_minimum" in data:
            data["status"] = "verified_minimum_met" if verified >= data["required_minimum"] else "incomplete"
        sources[eid] = data
        out[CATALOG / "sources" / f"{eid}.json"] = json.dumps(data, ensure_ascii=False, indent=2)

    metadata = read_json(CATALOG / "regions" / REGION_ID / "metadata.json")
    versions = sorted({c["catalog_version"] for c in cards.values()}, key=lambda v: [int(x) for x in v.split(".")])
    aggregate = {
        "catalog_id": f"{REGION_ID}-school-events",
        "catalog_version": versions[-1],
        "generated_by": "catalog/tools/build_catalog_index.py - файл производный, руками не править",
        "region": {k: metadata[k] for k in ("region_id", "title", "admin_center") if k in metadata},
        "events": [cards[k] for k in sorted(cards)],
        "sources": [sources[k] for k in sorted(sources)],
        "source_quality_note": "source_count counts source records, not independent verified publishers; see acceptance report and source audits.",
    }
    out[CATALOG / f"events_catalog_{REGION_ID}.json"] = json.dumps(aggregate, ensure_ascii=False, indent=2)

    header = ["event_id", "title", "category", "date_rule_type", "date_rule_value", "date_rule_note", "supported_age_groups",
              "supported_formats", "educational_goals_count", "educational_goals", "values", "regional_topics", "facts_to_verify_count",
              "review_historical", "review_age", "review_cultural", "source_collection", "source_ids", "source_count",
              "regional_variants", "catalog_version", "updated_at", "verified_source_count", "verified_direct_content_count",
              "fragments_verified", "fragments_draft", "source_registry_status", "source_count_semantics"]
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow(header)
    for eid in sorted(cards):
        c, st = cards[eid], source_stats(cards[eid], sources)
        review = c.get("review", {})
        writer.writerow([
            eid, c["title"], c["category"], c["date_rule"]["type"], c["date_rule"]["value"], c["date_rule"]["note"],
            "|".join(c["supported_age_groups"]), "|".join(c["supported_formats"]), len(c["educational_goals"]),
            " | ".join(c["educational_goals"]), "|".join(c["values"]), "|".join(c["regional_topics"]), len(c["facts_to_verify"]),
            str(review.get("historical_accuracy_required", False)).lower(), str(review.get("age_appropriateness_required", False)).lower(),
            str(review.get("cultural_review_required", False)).lower(), c["source_collection"], "|".join(c["source_ids"]),
            st["source_count"], "|".join(c["regional_variants"]), c["catalog_version"], c["updated_at"], st["verified_source_count"],
            st["verified_direct_content_count"], st["fragments_verified"], st["fragments_draft"],
            sources.get(eid, {}).get("status", "incomplete"), CSV_SEMANTICS,
        ])
    out[CATALOG / "catalog_index.csv"] = "﻿" + buf.getvalue().rstrip("\n")
    return out


def main(argv: list[str]) -> int:
    """Проверяет каталог и при необходимости обновляет его производные файлы.

    Параметры:
        argv: Аргументы командной строки без имени программы.

    Возвращает:
        0 при успешной проверке/сборке, 1 при ошибках или устаревших производных файлах.
    """
    cards, sources, errors = load()
    if errors:
        print("Ошибки каталога:")
        for e in errors:
            print(f"  - {e}")
        return 1
    files = build(cards, sources)
    stale = [p for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if "--check" in argv:
        if stale:
            print("Производные файлы устарели, запустите скрипт без --check:")
            for p in stale:
                print(f"  - {p.relative_to(CATALOG.parent)}")
            return 1
        print(f"Каталог в порядке: событий {len(cards)}.")
        return 0
    for p in stale:
        p.write_text(files[p], encoding="utf-8")
    print(f"Каталог в порядке: событий {len(cards)}. Обновлено файлов: {len(stale)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))