"""Программные проверки варианта (ТЗ 11, 12, 13.3, 14.3, 16, 17.6).

Каждая проблема знает, какой этап конвейера её исправляет (`stage`):
plan / blocks / materials. Критические проблемы не дают варианту статус completed.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from ..catalog import Catalog
from ..generation.timing import check_grid
from ..normalize import NormalizedRequest
from ..script_length import script_min_chars

_YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")
_DATE = re.compile(r"\b\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b", re.I)


# Признаки равноценной альтернативы в задании семье: модели формулируют её по-разному
# («Если поговорить не получается… представь, как ответил бы герой книги»).
FAMILY_ALTERNATIVE = re.compile(
    r"альтернатив|если дома|если некому|можно вместо|вместо этого|если нет возможност|если рядом нет"
    r"|если\s+(?:\w+\s+){0,3}не\s+(?:получа|получит|получил|може|сможе|хоч|успе)"
    r"|если\s+(?:\w+\s+){0,3}нет\b|(?:подумай|придумай)\s+сам"
    r"|если\s+(?:\w+\s+){0,3}(?:сложно|трудно|неудобно|некогда)"
    r"|можешь\s+(?:\w+\s+){0,2}(?:написать|придумать|представить|нарисовать|рассказать|выбрать|вспомнить)"
    r"|или\s+(?:просто\s+)?(?:расскажи|придумай|напиши|нарисуй|представь|выбери)"
    r"|геро\w*\s+(?:\w+\s+){0,2}(?:книг|книж|фильм|мультфильм|мультик|сказк|рассказ|истори)",
    re.I,
)

@dataclass
class Issue:
    code: str
    severity: str  # Допустимые уровни: info, warning, critical.
    location: str
    message: str
    stage: str = "blocks"
    repairable: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект в обычный словарь для сериализации и журналирования.

        Возвращает:
            dict[str, Any].
        """
        return asdict(self)


def _ids(items: list[dict], key: str) -> list[str]:
    """Собирает множество идентификаторов элементов для проверки ссылочной целостности.

    Параметры:
        `items`, `key`.

    Возвращает:
        list[str].
    """
    return [x[key] for x in items]


def validate_variant(v: dict[str, Any], n: NormalizedRequest, catalog: Catalog, gen_cfg: dict[str, Any]) -> list[Issue]:
    """Выполняет программные проверки готового внутреннего варианта по ограничениям запроса и ТЗ.

    Параметры:
        `v`, `n`, `catalog`, `gen_cfg`.

    Возвращает:
        list[Issue].
    """
    issues: list[Issue] = []

    def add(code, severity, location, message, stage="blocks", repairable=True):
        """Добавляет найденную проблему в общий список валидации с кодом, серьёзностью и местом ошибки.

        Параметры:
            `code`, `severity`, `location`, `message`, `stage`, `repairable`.
        """
        issues.append(Issue(code, severity, location, message, stage, repairable))

    roles, timeline, materials = v["roles"], v["timeline"], v["materials"]
    block_ids = _ids(timeline, "block_id")
    role_ids = _ids(roles, "role_id")
    material_ids = _ids(materials, "material_id")
    role_by_id = {r["role_id"]: r for r in roles}
    mat_by_id = {m["material_id"]: m for m in materials}

    # Проверка уникальности идентификаторов.
    for name, ids, stage in (("block_id", block_ids, "plan"), ("role_id", role_ids, "plan"), ("material_id", material_ids, "materials")):
        dup = [k for k, c in Counter(ids).items() if c > 1]
        if dup:
            add("ID-DUP", "critical", name, f"Повторяющиеся {name}: {', '.join(dup)}", stage)

    # Проверка тайминга.
    for problem in check_grid(timeline, n.duration_minutes):
        add("TIME-GRID", "critical", "timeline", problem, "local", repairable=False)

    # Проверка ссылок между сущностями.
    for b in timeline:
        for rid in b["role_ids"]:
            if rid not in role_by_id:
                add("REF-ROLE", "critical", f"timeline.{b['block_id']}", f"Роль {rid} не описана в roles", "blocks")
        for mid in b["material_ids"]:
            if mid not in mat_by_id:
                add("REF-MATERIAL", "critical", f"timeline.{b['block_id']}", f"Материал `{mid}` из плана не создан: добавь материал с material_id `{mid}` без изменений", "materials")
    for r in roles:
        for bid in r.get("block_ids", []):
            if bid not in block_ids:
                add("REF-BLOCK", "critical", f"roles.{r['role_id']}", f"Блок {bid} не существует", "plan")
        if not any(r["role_id"] in b["role_ids"] for b in timeline):
            add("ROLE-UNUSED", "warning", f"roles.{r['role_id']}", "Роль не участвует ни в одном блоке", "plan")
    for m in materials:
        for bid in m["used_in_blocks"]:
            if bid not in block_ids:
                add("REF-BLOCK", "critical", f"materials.{m['material_id']}", f"Блок {bid} не существует", "materials")
            elif m["material_id"] not in next(b for b in timeline if b["block_id"] == bid)["material_ids"]:
                add("REF-MATERIAL-USE", "warning", f"materials.{m['material_id']}", f"Материал указан для {bid}, но блок на него не ссылается", "materials")
        if not any(m["material_id"] in b["material_ids"] for b in timeline):
            add("MAT-UNUSED", "warning", f"materials.{m['material_id']}", "Материал не используется ни в одном блоке", "materials")

    # Проверка состава и количества участников.
    pupils_roles = [r for r in roles if r["participant_type"] in ("pupils_group", "pupil")]
    if not any(r["participant_type"] == "pupils_group" and r["count"] == n.pupils_count for r in roles):
        add("PUPILS-COUNT", "critical", "roles", f"Нет роли всех учащихся с count={n.pupils_count}", "plan")
    for r in pupils_roles:
        if r["count"] > n.pupils_count:
            add("PUPILS-OVER", "critical", f"roles.{r['role_id']}", f"Учеников в роли больше, чем в классе ({r['count']} > {n.pupils_count})", "plan")
    teachers = sum(r["count"] for r in roles if r["participant_type"] == "teacher")
    if teachers > n.teachers_count:
        add("TEACHERS-OVER", "critical", "roles", f"Ролей педагогов на {teachers} человек, доступно {n.teachers_count}", "plan")
    if teachers == 0:
        add("TEACHER-MISSING", "critical", "roles", "Нет роли ведущего педагога", "plan")

    parent_roles = [r for r in roles if r["participant_type"] == "parent"]
    plan = v.get("parent_participation_plan")
    if not n.parents_enabled:
        if parent_roles:
            add("PARENTS-DISABLED", "critical", "roles", "Назначены роли родителей, хотя родители отключены", "plan")
        if plan and plan.get("enabled"):
            add("PARENTS-DISABLED", "critical", "parent_participation_plan", "План участия родителей при отключённых родителях", "local")
        for m in materials:
            if m["type"] in ("parent_instruction", "audience_ballot", "jury_scorecard", "award_instruction"):
                add("PARENTS-DISABLED", "critical", f"materials.{m['material_id']}", f"Материал {m['type']} при отключённых родителях", "materials")
    else:
        for r in parent_roles:
            if r.get("role_mode") not in n.parent_roles:
                add("PARENT-ROLE", "critical", f"roles.{r['role_id']}", f"Роль родителя {r.get('role_mode')} не разрешена", "plan")
        for b in timeline:
            busy = sum(role_by_id[x]["count"] for x in b["role_ids"] if x in role_by_id and role_by_id[x]["participant_type"] == "parent")
            if busy > n.parents_count:
                add("PARENTS-OVER", "critical", f"timeline.{b['block_id']}", f"Одновременно занято родителей {busy} > {n.parents_count}", "plan")
        if not plan or not plan.get("enabled"):
            add("PARENT-PLAN", "critical", "parent_participation_plan", "Нет плана участия родителей", "materials")
        elif not plan.get("teacher_fallback"):
            add("PARENT-FALLBACK", "critical", "parent_participation_plan", "Нет запасного плана без родителей", "materials")
        eng = n.parent_audience_engagement
        types = {m["type"] for m in materials}
        if eng in ("vote", "audience_award"):
            voting = (plan or {}).get("voting")
            if not voting or not voting.get("enabled"):
                add("VOTING-MISSING", "critical", "parent_participation_plan.voting", "Выбрано голосование, но регламента нет", "materials")
            else:
                if voting.get("block_id") not in block_ids:
                    add("VOTING-BLOCK", "critical", "parent_participation_plan.voting", "Блок голосования не существует", "materials")
                for mid in voting.get("material_ids", []):
                    if mid not in mat_by_id:
                        add("VOTING-MATERIAL", "critical", "parent_participation_plan.voting", f"Бланк {mid} не создан", "materials")
                if not voting.get("voters_count_planned"):
                    add("VOTING-NO-VOTERS", "warning", "parent_participation_plan.voting", "В блоке голосования нет родителей-зрителей", "plan")
            if "audience_ballot" not in types:
                add("BALLOT-MISSING", "critical", "materials", "Нет бюллетеня для голосования зрителей", "materials")
            if eng == "audience_award" and "award_instruction" not in types:
                add("AWARD-INSTRUCTION", "warning", "materials", "Нет инструкции к награждению (award_instruction)", "materials")
        else:
            # Инструкция к награждению уместна и по итогам оценки жюри (как и сказано в промпте этапа материалов).
            jury = any(r.get("role_mode") == "evaluator" for r in parent_roles)
            for m in materials:
                if m["type"] == "audience_ballot" or (m["type"] == "award_instruction" and not jury):
                    add("BALLOT-NOT-ALLOWED", "critical", f"materials.{m['material_id']}", "Бюллетень/приз без выбранного режима голосования", "materials")
        if any(r.get("role_mode") == "helper" for r in parent_roles) and "parent_instruction" not in types:
            add("PARENT-INSTRUCTION", "warning", "materials", "Есть родители-помощники, но нет памятки для них (parent_instruction)", "materials")
        if "evaluator" not in n.parent_roles and "jury_scorecard" in types:
            add("JURY-NOT-ALLOWED", "critical", "materials", "Лист жюри без роли evaluator", "materials")
        if "evaluator" in n.parent_roles and any(r.get("role_mode") == "evaluator" for r in parent_roles) and "jury_scorecard" not in types:
            add("JURY-SCORECARD", "critical", "materials", "Есть жюри, но нет листа критериев", "materials")

    # Проверка деления школьников на группы.
    g = v.get("pupil_grouping") or {}
    if g:
        if sum(g.get("group_sizes", [])) != n.pupils_count:
            add("GROUP-SUM", "critical", "pupil_grouping", f"Сумма групп {sum(g.get('group_sizes', []))} ≠ {n.pupils_count}", "local", False)
        if not n.group_work and g.get("mode") in ("small_groups", "mixed"):
            add("GROUP-WORK-FORBIDDEN", "critical", "pupil_grouping", "Обязательные малые группы при group_work=false", "plan")
    if not n.group_work:
        for b in timeline:
            text = " ".join([b["teacher_script"], *b["pupil_actions"]])
            if re.search(r"(раздел|раздели|делим|делятся|поделите)\w*\s+(класс\s+)?на\s+\d+\s+(групп|команд)", text, re.I):
                add("GROUP-WORK-FORBIDDEN", "critical", f"timeline.{b['block_id']}", "Деление на малые группы при group_work=false", "blocks")

    # Проверка ресурсов и материалов.
    deps = catalog.dependencies
    res = n.resources
    for m in materials:
        loc = f"materials.{m['material_id']}"
        for d in m["dependencies"]:
            item = deps.get(d)
            if item is None:
                add("DEP-UNKNOWN", "critical", loc, f"Зависимость «{d}» вне словаря", "materials")
                continue
            flag = item.get("resource_flag")
            if flag and res.get(flag) is False:
                add("RESOURCE-UNAVAILABLE", "critical", loc, f"Материал требует «{item['label']}», которого нет", "materials")
            elif flag and res.get(flag) is None and "без" not in m["teacher_notes"].lower():
                add("RESOURCE-UNKNOWN", "warning", loc, f"Наличие «{item['label']}» не подтверждено - нужен вариант без него в teacher_notes", "materials")
        if m["print_required"] and res.get("printer") is False:
            add("PRINT-UNAVAILABLE", "critical", loc, "print_required=true при отсутствии принтера", "materials")
        if m["type"] == "slide_outline" and res.get("projector") is False:
            add("SLIDES-NO-PROJECTOR", "critical", loc, "Слайды при отсутствии проектора", "materials")
        if m["type"] == "quiz" and not re.search(r"ответ|ключ", m["content"], re.I):
            add("QUIZ-KEY", "warning", loc, "У викторины нет ключа ответов", "materials")
        if m.get("family_task"):
            if "family" not in n.values:
                add("VAL-005", "critical", loc, "Задание семье без ценности «Семья»", "materials")
            if m["type"] != "handout" or "по желанию" not in m["title"].lower():
                add("VAL-005", "critical", loc, "Задание семье: тип handout и пометка «(по желанию, до мероприятия)»", "materials")
            if not FAMILY_ALTERNATIVE.search(m["content"]):
                add("VAL-005", "critical", loc, "Задание семье без равноценной альтернативы", "materials")
    if res.get("internet") is False:
        for b in timeline:
            if re.search(r"\b(онлайн|интернет|сайт|QR|приложени)", b["teacher_script"], re.I) and not re.search(r"без интернета", b["teacher_script"], re.I):
                add("RESOURCE-INTERNET", "warning", f"timeline.{b['block_id']}", "Похоже на онлайн-активность при отсутствии интернета", "blocks")

    # Проверка содержимого сценарных блоков.
    detail = n.teacher_preferences["script_detail"]
    for b in timeline:
        min_chars = script_min_chars(gen_cfg, detail, b["duration_minutes"])
        if len(b["teacher_script"]) < min_chars:
            add("SCRIPT-SHORT", "warning", f"timeline.{b['block_id']}",
                f"Реплики педагога короче {min_chars} символов для блока на {b['duration_minutes']} мин ({len(b['teacher_script'])})", "blocks")
        if len(b["pupil_actions"]) < 2:
            add("PUPIL-ACTIONS-FEW", "warning", f"timeline.{b['block_id']}", f"Действий учеников меньше двух ({len(b['pupil_actions'])})", "blocks")

    # Проверка связи ценностей с механиками по правилам VAL-001..VAL-004.
    vtm = v["concept"].get("values_to_mechanics", [])
    by_value = {x["value_id"]: x for x in vtm}
    for value_id in n.values:
        rec = by_value.get(value_id)
        if rec is None:
            add("VAL-001", "critical", "concept.values_to_mechanics", f"Ценность {value_id} не реализована", "plan")
            continue
        if not rec.get("block_ids"):
            add("VAL-002", "critical", "concept.values_to_mechanics", f"Для {value_id} не указаны блоки", "plan")
        for bid in rec.get("block_ids", []):
            if bid not in block_ids:
                add("VAL-002", "critical", "concept.values_to_mechanics", f"{value_id}: блок {bid} не существует", "plan")
        allowed = catalog.values[value_id].get("allowed_mechanic_types", [])
        if allowed and rec.get("mechanic_type") not in allowed:
            add("VAL-004", "warning", "concept.values_to_mechanics", f"{value_id}: механика {rec.get('mechanic_type')} не из допустимых {allowed}", "plan")
    for value_id in by_value:
        if value_id not in n.values:
            add("VAL-001", "warning", "concept.values_to_mechanics", f"Лишняя ценность {value_id}", "plan")

    # Проверка фактологических утверждений по требованиям раздела 17.6.
    claims = v.get("fact_claims", [])
    for c in claims:
        loc = f"fact_claims.{c['claim_id']}"
        if c.get("needs_teacher_check"):
            add("FACT-CHECK", "warning", loc, f"Требует проверки педагогом: «{c['text']}»", "blocks", repairable=False)
            continue
        frag = catalog.fragments.get(c.get("fragment_id") or "")
        if not frag or frag.get("source_id") != c.get("source_id") or frag.get("verification_status", frag.get("status")) != "verified":
            add("FACT-SOURCE", "critical", loc, f"Утверждение без проверенного фрагмента: «{c['text']}»", "blocks")
    texts = [(f"timeline.{b['block_id']}", b["teacher_script"] + " " + " ".join(b["pupil_actions"])) for b in timeline]
    texts += [(f"materials.{m['material_id']}", m["content"]) for m in materials]
    claimed = " ".join(c["text"] for c in claims)
    for loc, text in texts:
        for match in list(_YEAR.finditer(text)) + list(_DATE.finditer(text)):
            token = match.group(0)
            if token not in claimed:
                add("FACT-UNREGISTERED", "warning", loc, f"Дата/год «{token}» не зарегистрирован в fact_claims", "blocks")
                break
    src_ids = {c.get("source_id") for c in claims if c.get("source_id")}
    for s in v.get("sources", []):
        if s["source_id"] not in src_ids:
            add("SOURCE-UNUSED", "warning", "sources", f"Источник {s['source_id']} не подтверждает ни одного утверждения", "local", False)

    if not v.get("teacher_instructions"):
        add("INSTRUCTIONS", "critical", "teacher_instructions", "Нет инструкции педагогу", "materials")
    return issues


def report_status(issues: list[Issue]) -> str:
    """Вычисляет итоговый статус проверки по серьёзности найденных проблем.

    Параметры:
        `issues`.

    Возвращает:
        str.
    """
    if any(i.severity == "critical" for i in issues):
        return "blocked"
    if any(i.severity == "warning" for i in issues):
        return "warning"
    return "passed"


def diversity_issues(concepts: list[dict[str, Any]]) -> list[Issue]:
    """ТЗ 9.4: концепции не должны совпадать по механике и набору активностей."""
    issues: list[Issue] = []
    if len(concepts) < 2:
        return issues
    titles = [c["title"].strip().lower() for c in concepts]
    if len(set(titles)) != len(titles):
        issues.append(Issue("DIV-TITLE", "critical", "concepts", "Повторяющиеся названия концепций", "concepts"))
    signatures = [(c["primary_mechanic"], frozenset(a["activity_type"] for a in c["key_activities"])) for c in concepts]
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            if signatures[i][0] == signatures[j][0] and signatures[i][1] == signatures[j][1]:
                issues.append(Issue("DIV-MECHANIC", "critical", f"concepts.{concepts[j]['variant_id']}",
                                    f"Концепции {concepts[i]['variant_id']} и {concepts[j]['variant_id']} совпадают по механике и активностям", "concepts"))
    if len({c["primary_mechanic"] for c in concepts}) == 1:
        issues.append(Issue("DIV-PRIMARY", "warning", "concepts", "У всех концепций одна основная механика", "concepts"))
    vm = [frozenset((x["value_id"], x["mechanic_type"]) for x in c["values_to_mechanics"]) for c in concepts]
    if len(set(vm)) == 1:
        issues.append(Issue("DIV-VALUES", "warning", "concepts", "Ценности реализуются одинаковыми механиками во всех концепциях", "concepts"))
    return issues