"""Читаемая версия варианта (Markdown) - для педагогов и экспертной оценки."""

from __future__ import annotations

from typing import Any

FORMAT = {"class_hour": "классный час", "school_event": "общешкольное мероприятие", "interactive_lesson": "интерактивное занятие"}
PARTICIPANTS = {"teacher": "педагог", "pupil": "ученик", "pupils_group": "ученики", "parent": "родители", "guest": "гость"}
ROLE_MODES = {"helper": "помощники", "active_participant": "активные участники", "audience": "зрители", "evaluator": "жюри"}
MATERIAL_TYPES = {
    "teacher_instruction": "памятка педагогу", "worksheet": "рабочий лист", "activity_card": "карточки заданий",
    "slide_outline": "план слайдов", "quiz": "викторина", "discussion_questions": "вопросы для обсуждения",
    "handout": "раздаточный материал", "props_checklist": "реквизит", "parent_instruction": "памятка для родителей",
    "audience_ballot": "бюллетень", "jury_scorecard": "лист жюри", "award_instruction": "награждение",
}
QUALITY_STATUS = {"passed": "замечаний нет", "warning": "есть замечания", "failed": "есть критические ошибки"}
SEVERITY = {"critical": "Критично", "warning": "Замечание", "info": "Справка"}


def issue_place(v: dict[str, Any], location: str) -> str:
    """Переводит место проблемы (`timeline.block_02`, `materials.card_task`, `roles.parent_helpers`) в понятное название.

    Параметры:
        v: вариант; location: поле `location` проблемы.

    Возвращает:
        Например «блок «Встреча и цель» (0-5 мин)»; пустую строку, если место не относится к блоку, материалу или роли.
    """
    kind, _, key = location.partition(".")
    key = key.split(".")[0]
    if kind == "timeline":
        for b in v.get("timeline", []):
            if b["block_id"] == key:
                end = b["start_minute"] + b["duration_minutes"]
                return f"блок «{b['title']}» ({b['start_minute']}-{end} мин)"
    if kind == "materials":
        for m in v.get("materials", []):
            if m["material_id"] == key:
                return f"материал «{m['title']}»"
    if kind == "roles":
        for r in v.get("roles", []):
            if r["role_id"] == key:
                return f"роль «{r['title']}»"
    return ""


def _blocks_text(v: dict[str, Any], block_ids: list[str]) -> str:
    """Этапы по названиям, а не по ID: «все этапы» или «Станции знаний», «Карта целей»."""
    titles = {b["block_id"]: b["title"] for b in v.get("timeline", [])}
    if block_ids and len(block_ids) == len(titles) and set(block_ids) == set(titles):
        return "все этапы"
    return ", ".join(f"«{titles.get(bid, bid)}»" for bid in block_ids) or "-"


def variant_to_markdown(v: dict[str, Any], inp: dict[str, Any] | None = None, event_title: str | None = None) -> str:
    """Формирует читаемую Markdown-проекцию готового варианта для локальной диагностики.

    Параметры:
        `v`, `inp`, `event_title`.

    Возвращает:
        str.
    """
    out: list[str] = [f"# {v['title']}", ""]
    if inp:
        p = inp.get("participants", {})
        parents = f", родителей: {p.get('parents_count')}" if p.get("parents_enabled") else ", без родителей"
        grade = f"{inp['grade']} класс" if inp.get("grade") else f"{inp.get('grade_group')} классы"
        out += [f"**{event_title or inp['event_id']}** · {grade} · {inp['pupils_count']} учеников{parents} · "
                f"{inp['duration_minutes']} минут · {FORMAT.get(inp['format'], inp['format'])}", ""]
    c = v["concept"]
    out += ["## Концепция", c["summary"], "", f"**Цель:** {c['goal']}", "", "**Задачи:**"]
    out += [f"- {t}" for t in c["tasks"]]
    out += ["", "**Результат:**"] + [f"- {t}" for t in c["expected_outcomes"]] + [""]
    out += ["## Роли", "| Роль | Кто | Сколько | Этапы |", "|---|---|---|---|"]
    for r in v["roles"]:
        who = PARTICIPANTS.get(r["participant_type"], r["participant_type"])
        if r.get("role_mode"):
            who += f" ({ROLE_MODES.get(r['role_mode'], r['role_mode'])})"
        out.append(f"| {r['title']} | {who} | {r['count']} | {_blocks_text(v, r['block_ids'])} |")
    out += ["", "## Сценарий"]
    for b in v["timeline"]:
        end = b["start_minute"] + b["duration_minutes"]
        out += ["", f"### {b['start_minute']}–{end} мин · {b['title']} ({b['duration_minutes']} мин)", f"*{b['purpose']}*", "",
                b["teacher_script"], "", "**Что делают ученики:**"] + [f"- {a}" for a in b["pupil_actions"]]
        if b["material_ids"]:
            titles = {m["material_id"]: m["title"] for m in v["materials"]}
            out.append(f"\n**Материалы:** {', '.join(titles.get(mid, mid) for mid in b['material_ids'])}")
    out += ["", "## Материалы"]
    for m in v["materials"]:
        flags = " · печать" if m["print_required"] else ""
        out += ["", f"### {m['title']} ({MATERIAL_TYPES.get(m['type'], m['type'])}{flags})", "", m["content"].replace("\n", "  \n"), "",
                f"*Педагогу:* {m['teacher_notes']}"]
    plan = v.get("parent_participation_plan")
    if plan and plan.get("enabled"):
        out += ["", "## Участие родителей", f"Родителей: {plan['parents_count']} ({plan['parent_size_group']})"]
        out += [f"- {ROLE_MODES.get(a['role_mode'], a['role_mode'])}: {a['count']} - {_blocks_text(v, a['block_ids'])}" for a in plan["assignments"]]
        if plan.get("voting"):
            vt = plan["voting"]
            out += [f"- Голосование: {vt.get('award_title') or 'без приза'}; критерий - {vt['criterion']}; ничья - {vt['tie_rule']}"]
        out += [f"- Если родители не придут: {plan['teacher_fallback']}"]
    out += ["", "## Подготовка и проведение"] + [f"- {t}" for t in v["teacher_instructions"]]
    if v.get("sources"):
        out += ["", "## Источники"] + [f"- {s['title']} - {s['publisher']} ({s['url']})" for s in v["sources"]]
    qr = v.get("quality_report")
    if qr:
        status = QUALITY_STATUS.get(qr["status"], qr["status"])
        out += ["", f"## Проверка качества: {status}"]
        for i in qr.get("issues", []):
            where = issue_place(v, i.get("location", ""))
            out.append(f"- {SEVERITY.get(i['severity'], i['severity'])}{' · ' + where if where else ''}: {i['message']} (`{i['code']}`)")
    return "\n".join(out) + "\n"