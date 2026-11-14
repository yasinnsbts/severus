"""Содержание сценария для педагога: технические ID, точность события, время внутри этапов.

Замечания по сценарию «Рождественские традиции мира» (13.11.2026):
- в памятке и репликах были внутренние ID: family_handout, display_board, research_cards, parent_instruction, block_02;
- модель смешивала рождественские и новогодние традиции;
- внутри этапа модель может дать больше действий, чем помещается во время («5 групп по 3 минуты за 10 минут»).

Контрольный прогон на GigaChat-2-Max (13.11.2026, examples/requests/content_check): 4 из 4 completed. По сценариям:
- в читаемой версии (Markdown) оставались ID этапов и материалов в таблице ролей и строках «Материалы»;
- «7 января» в сценарии о Рождестве считалось непроверенной датой, хотя это дата из карточки каталога;
- в карточках материалов - традиции Италии, Мексики, народов Поволжья и Сибири без источника;
- в Рождестве 10 минут работы и выступления 4 команд в 12-минутном этапе;
- «4 групп» вместо «4 группы».
"""

import copy
import dataclasses
import json
import re
import unittest

from app.generation.grouping import describe
from app.generation.humanize import build_names, humanize_text, humanize_variant, leftover_ids
from app.markdown import variant_to_markdown
from app.normalize import normalize
from app.prompting.composer import Composer
from app.validation.checks import _confirmed, _culture_claims, validate_variant
from app.validation.inner_timing import inner_timing_problems
from tests.helpers import ROOT, catalog, minimal_request, settings
from tests.test_gigachat_matrix_replays import replay
from tests.test_material_ids import ReplayLLM
from tests.test_validation_render import setup

FIXTURES = ROOT / "tests" / "fixtures"


def _variant_texts(variant):
    """Все тексты варианта, которые видит педагог."""
    texts = [variant["title"], variant["concept"]["summary"], variant["concept"]["goal"], *variant["teacher_instructions"]]
    for block in variant["timeline"]:
        texts += [block["title"], block["purpose"], block["teacher_script"], *block["pupil_actions"]]
    for material in variant["materials"]:
        texts += [material["title"], material["content"], material["teacher_notes"]]
    return texts


def _issues(variant, n):
    return [(i.code, i.severity, i.location) for i in validate_variant(variant, n, catalog(), settings().generation())]


class HumanizeTextTest(unittest.TestCase):
    """Замена ID работает при разных формулировках модели."""

    def setUp(self):
        variant = {
            "timeline": [{"block_id": "block_02", "title": "Знакомство с традициями"},
                         {"block_id": "block_03", "title": "Мастерская открытки"}],
            "materials": [{"material_id": "family_handout", "title": "Задание для семьи (по желанию, до мероприятия)"},
                          {"material_id": "research_cards", "title": "Карточки исследователя"},
                          {"material_id": "parent_instruction", "title": "Памятка для родителей-помощников"},
                          {"material_id": "capsule_box", "title": "«Капсула пожеланий»"},
                          {"material_id": "audience_ballot", "title": "Бюллетень для голосования"}],
            "roles": [{"role_id": "parent_helpers", "title": "Родители-помощники"}],
        }
        planned = [{"material_id": "display_board", "type": "handout", "title": "Стенд «Традиции мира»"}]
        self.names = build_names(variant, catalog().dependencies, planned)

    def fix(self, text):
        return humanize_text(text, self.names)[0]

    def test_formulations(self):
        cases = {
            "Раздайте family_handout за неделю до мероприятия.":
                "Раздайте «Задание для семьи (по желанию, до мероприятия)» за неделю до мероприятия.",
            "Перед началом работы в блоке block_03 раздайте research_cards.":
                "Перед началом работы в блоке «Мастерская открытки» раздайте «Карточки исследователя».",
            "(Раздаёт materials: research_cards.) Начинаем!": "(Раздаёт «Карточки исследователя».) Начинаем!",
            "Сложите их в коробку. (Показывает коробку-capsule_box.)": "Сложите их в коробку. (Показывает коробку «Капсула пожеланий».)",
            "Подготовьте бюллетени для голосования (audience_ballot).": "Подготовьте бюллетени для голосования.",
            "Выдайте родителям `parent_instruction`, как в «block_02».":
                "Выдайте родителям «Памятка для родителей-помощников», как в «Знакомство с традициями».",
            "Повесьте display_board у доски.": "Повесьте Стенд «Традиции мира» у доски.",
            "Для этапа нужны paper и whatman.": "Для этапа нужны «Бумага А4» и «Ватман или плакатная бумага».",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                result = self.fix(source)
                self.assertEqual(result, expected)
                self.assertEqual(leftover_ids(result), [])

    def test_urls_emails_and_words_untouched(self):
        for text in ("Источник: https://example.org/family_handout/block_02", "Почта a_b@school.ru", "путь docs/research_cards"):
            with self.subTest(text=text):
                self.assertEqual(self.fix(text), text)

    def test_unknown_id_left_for_check(self):
        result = self.fix("Повесьте world_map_poster на доску.")
        self.assertEqual(leftover_ids(result), ["world_map_poster"])


class MetaNotesTest(unittest.TestCase):
    def test_size_note_removed(self):
        """Прогон 14.11 (Рождество 7 кл): «Объём текста сценария для педагога составляет около 780 символов.» в реплике."""
        from app.generation.humanize import drop_meta_notes
        block = json.loads((FIXTURES / "qa_v3_christmas_presentations_block.json").read_text(encoding="utf-8"))
        variant = {"timeline": [block], "materials": [{"material_id": "m", "content": "Символы области: герб и флаг. Герб - символ края.",
                                                     "teacher_notes": "Раздайте 25 карточек."}], "teacher_instructions": []}
        changes = drop_meta_notes(variant)
        self.assertEqual(changes, [{"field": "timeline.block_03.teacher_script",
                                    "removed": ["Объём текста сценария для педагога составляет около 780 символов."]}])
        script = variant["timeline"][0]["teacher_script"]
        self.assertNotIn("символов", script)
        self.assertIn("итого шесть минут.\nУчитель следит за временем", script)
        self.assertEqual(variant["materials"][0]["content"], "Символы области: герб и флаг. Герб - символ края.")


class HumanizeVariantTest(unittest.TestCase):
    def test_replay_with_ids_in_model_text(self):
        """Модель пишет ID в репликах, действиях и памятке - в готовом варианте их нет, предупреждений тоже."""

        class LeakyReplay(ReplayLLM):
            def generate(self, **kwargs):
                response = super().generate(**kwargs)
                text = response.text
                if kwargs["task_name"] == "scenario_block":
                    text = text.replace('"teacher_script": "', '"teacher_script": "(Раздаёт materials: source_cards, затем `worksheet`, как в block_02.) ', 1)
                    text = text.replace('"pupil_actions": ["', '"pupil_actions": ["Берут source_cards и ', 1)
                if kwargs["task_name"] == "materials":
                    text = text.replace('"teacher_instructions": ["', '"teacher_instructions": ["Распечатайте jury_scorecard (jury_scorecard) для жюри. ', 1)
                return dataclasses.replace(response, text=text)

        directory = FIXTURES / "replay_gigachat_matrix_m3_jury"
        client = LeakyReplay(directory)
        from app.generation.pipeline import Generator
        outcome = Generator(settings(), catalog(), client).run(json.loads((directory / "request.json").read_text(encoding="utf-8")))
        variant = outcome.project["variants"][0]
        joined = "\n".join(_variant_texts(variant))
        self.assertIn("(Раздаёт «", joined)
        for token in ("source_cards", "worksheet", "jury_scorecard", "block_02", "materials:"):
            self.assertNotIn(token, joined)
        codes = {i["code"] for i in variant["quality_report"]["issues"]}
        self.assertNotIn("TECH-ID-IN-TEXT", codes)

    def test_reference_fields_untouched(self):
        """Поля-ссылки остаются ID: фронт и проверки работают по ним."""
        outcome, _ = replay("replay_gigachat_matrix_m3_jury")
        variant = outcome.project["variants"][0]
        self.assertTrue(all(re.fullmatch(r"block_\d\d", b["block_id"]) for b in variant["timeline"]))
        for material in variant["materials"]:
            self.assertTrue(all(re.fullmatch(r"block_\d\d", x) for x in material["used_in_blocks"]))

    def test_unknown_id_gives_warning(self):
        n, v = setup("ex1_knowledge_day")
        v["timeline"][0]["teacher_script"] += " Повесьте world_map_poster на доску."
        humanize_variant(v, catalog().dependencies)
        self.assertIn(("TECH-ID-IN-TEXT", "warning", f"timeline.{v['timeline'][0]['block_id']}"), _issues(v, n))


class InnerTimingTest(unittest.TestCase):
    @staticmethod
    def problems(duration, text, groups=5, pairs=0, next_duration=0):
        return inner_timing_problems({"duration_minutes": duration, "teacher_script": text, "pupil_actions": []},
                                     groups_count=groups, pairs_count=pairs, next_duration=next_duration)

    def test_obvious_contradictions(self):
        self.assertTrue(self.problems(10, "Пять групп выступают по три минуты."))
        self.assertTrue(self.problems(10, "Команды по очереди выступают, по 3 минуты на каждую команду."))
        self.assertTrue(self.problems(8, "Каждая команда представит свой раздел. На выступление у вас будет 2 минуты."))
        self.assertTrue(self.problems(12, "Каждая команда получит 4 минуты на выступление: 3 минуты на рассказ и 1 минуту на вопросы."))
        self.assertTrue(self.problems(10, "У вас 7 минут на рисунок. Потом у вас есть 5 минут на выставку.", groups=1))
        self.assertTrue(self.problems(10, "Каждая пара представит открытку, по 1 минуте на пару.", groups=1, pairs=13))

    def test_time_per_group_phrasings(self):
        """Формы «N минут на группу» и «время выступления - N минут» (прогон QA c2, BUG-03)."""
        self.assertEqual(self.problems(10, "Каждая группа представит лист. (4 минуты на группу)", groups=4),
                         ["выступления: 4 групп × 4 мин = 16 мин, а на блок 10 мин"])
        self.assertTrue(self.problems(10, "Группы по очереди рассказывают, по 3-4 минуты на группу.", groups=4))
        self.assertTrue(self.problems(10, "Каждая группа рассказывает о плакате. Время выступления - 4 минуты.", groups=4))
        self.assertTrue(self.problems(10, "Пары по очереди показывают открытки, по 1 минуте на пару.", groups=1, pairs=13))
        self.assertFalse(self.problems(10, "Каждая группа представит плакат. Время выступления - 2 минуты.", groups=4))
        self.assertFalse(self.problems(10, "Две-три группы по желанию представят работу, по 4 минуты на группу.", groups=4))
        self.assertFalse(self.problems(10, "Время на выступления - 8 минут. Каждая группа представит плакат.", groups=4))

    def test_qa_run_c2_presentations_block(self):
        """Блок из прогона QA c2 (День единства, 10 класс): 4 группы по 3 минуты в 10-минутном этапе."""
        block = {
            "duration_minutes": 10,
            "teacher_script": ("Каждая группа представит свой информационный лист. Группа номер один, готовы? "
                               "У вас три минуты. (Аналогично проходят презентации остальных трёх групп.)"),
            "pupil_actions": ["Выступающие представляют информационный лист своей группы, рассказывают о традициях "
                              "выбранного народа (3 минуты на группу)",
                              "Остальные учащиеся внимательно слушают"],
        }
        self.assertEqual(inner_timing_problems(block, groups_count=4, pairs_count=0),
                         ["выступления: 4 групп × 3 мин = 12 мин, а на блок 10 мин"])

    def test_speaker_time_and_per_minute(self):
        """Прогон 14.11 (Рождество 7 кл): 6 команд, «Спикеру даётся одна минута», «по минуте на каждую группу» в 6-минутном
        этапе - всё сходится, предупреждения нет. Две минуты спикеру при тех же 6 командах - уже 12 минут."""
        block = json.loads((FIXTURES / "qa_v3_christmas_presentations_block.json").read_text(encoding="utf-8"))
        self.assertEqual(inner_timing_problems(block, groups_count=6, pairs_count=0, next_duration=5, next_title="Подведение итогов"), [])
        self.assertEqual(self.problems(6, "Каждая команда выберет спикера, он расскажет о коллаже. Спикеру даётся две минуты.", groups=6),
                         ["выступления: 6 групп × 2 мин = 12 мин, а на блок 6 мин"])
        self.assertTrue(self.problems(4, "Команды по очереди представляют коллажи, по минуте на каждую группу.", groups=6))

    def test_work_then_all_groups_present(self):
        text = "На выполнение задания вам даётся 10 минут. Затем каждая команда представит свой коллаж всему классу."
        self.assertTrue(self.problems(12, text, groups=4))
        self.assertFalse(self.problems(16, text, groups=4))
        # Выступления в следующем этапе - не часть текущего.
        self.assertFalse(inner_timing_problems({"duration_minutes": 12, "teacher_script": text, "pupil_actions": []},
                                               groups_count=4, pairs_count=0, next_title="Представление коллажей"))

    def test_good_scenarios_not_flagged(self):
        """Параллельная работа, выступления по желанию и объявление времени следующего этапа - не противоречия."""
        self.assertFalse(self.problems(15, "У вас 15 минут. Каждая группа работает над своим заданием, потом представит результат."))
        self.assertFalse(self.problems(10, "Выступают 2-3 группы по желанию, по 3 минуты."))
        self.assertFalse(self.problems(10, "Спикерам даётся максимум две минуты на каждую идею."))
        self.assertFalse(self.problems(5, "На выполнение задания у вас будет 15 минут. Готовы?", groups=1, next_duration=15))
        self.assertFalse(self.problems(10, "У вас 10 минут. (через 5 минут) Осталось пять минут.", groups=1))
        self.assertFalse(self.problems(10, "Каждая команда представит свой раздел. На выступление у вас будет 2 минуты."))
        self.assertFalse(self.problems(20, "Каждая группа получит три-четыре минуты, чтобы представить своё выступление."))

    def test_recorded_runs_not_flagged(self):
        """Записанные прогоны GigaChat проходят без INNER-TIMING: проверка не мешает хорошим сценариям."""
        for name in ("replay_gigachat_matrix_m1", "replay_gigachat_matrix_m2_vote", "replay_gigachat_matrix_m3_jury",
                     "replay_gigachat_unescaped_quote"):
            with self.subTest(name=name):
                outcome, _ = replay(name)
                codes = {i["code"] for v in outcome.project["variants"] for i in v["quality_report"]["issues"]}
                self.assertNotIn("INNER-TIMING", codes)

    def test_warning_does_not_block(self):
        n, v = setup("ex1_knowledge_day")
        v["pupil_grouping"] = {"total_pupils": 25, "mode": "small_groups", "group_sizes": [5, 5, 5, 5, 5], "block_ids": []}
        block = v["timeline"][-1]
        block["teacher_script"] += f" Каждая группа выступает по {block['duration_minutes']} минуты."
        issues = _issues(v, n)
        self.assertIn(("INNER-TIMING", "warning", f"timeline.{block['block_id']}"), issues)
        self.assertNotIn("critical", {severity for code, severity, _ in issues if code == "INNER-TIMING"})


class EventAccuracyTest(unittest.TestCase):
    @staticmethod
    def prompt(event_id, grade_group="5-8", **overrides):
        raw = minimal_request(event_id=event_id, grade_group=grade_group, **overrides)
        n = normalize(raw, catalog(), settings())
        return Composer(settings(), catalog()).compose("scenario_plan", n).messages[1]["content"], n

    def test_card_names_event_and_close_holiday(self):
        text, _ = self.prompt("christmas")
        self.assertIn("**Событие:** Рождество Христово", text)
        self.assertIn("Не путать с праздником «Новый год»", text)
        self.assertIn("Без Деда Мороза, Снегурочки", text)
        text, _ = self.prompt("new_year")
        self.assertIn("Не путать с праздником «Рождество»", text)

    def test_regional_topics_named(self):
        text, _ = self.prompt("victory_day", grade_group="9-11")
        self.assertIn("Уральский добровольческий танковый корпус", text)
        self.assertNotIn("RU-SVE/ural_volunteer_tank_corps", text)

    def test_no_fragments_means_no_specific_history(self):
        text, n = self.prompt("knowledge_day", grade_group="1-4")
        if not catalog().verified_fragments(n.event_id, n.region_id, n.cultural_context):
            self.assertIn("без годов, веков, чисел, имён", text)

    def test_every_event_has_boundary_hint(self):
        events = catalog().boundaries["events"]
        for event_id in catalog().events:
            with self.subTest(event_id=event_id):
                self.assertTrue(events.get(event_id, {}).get("hint"))
                for marker in events[event_id].get("markers", []):
                    re.compile(marker)

    def test_mixup_warning(self):
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.event_id = "christmas"
        v["timeline"][1]["teacher_script"] += " А теперь позовём Деда Мороза и Снегурочку!"
        self.assertIn(("EVENT-MIXUP", "warning", f"timeline.{v['timeline'][1]['block_id']}"), _issues(v, n))
        n.event_id = "new_year"
        self.assertNotIn("EVENT-MIXUP", {code for code, _, _ in _issues(v, n)})

    def test_country_list_in_material(self):
        """Факты списком под страной-заголовком (прогон QA E2E-13, BUG-11): «Италия:» и ниже «- Украшают вертеп»."""
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.event_id = "christmas"
        material = v["materials"][0]
        material["content"] = ("На каждой карточке - традиции одной страны. Например:\n\nИталия:\n"
                               "- Украшают вертеп\n- Дарят подарки утром\n\n**Германия:**\n- Пекут штоллен")
        self.assertIn(("CULTURE-UNSOURCED", "warning", f"materials.{material['material_id']}"), _issues(v, n))
        # Заголовок не страна и обычный текст без страны - не сведения о традициях страны.
        material["content"] = "Индивидуальная работа:\n- Готовят ответы\n\nРоссия - наша общая страна.\n- Ставят задачи"
        self.assertNotIn("CULTURE-UNSOURCED", {code for code, _, _ in _issues(v, n)})

    def test_goal_with_year_must_be_covered(self):
        """Задача «Знакомство с событиями 1612 года» из карточки, а о 1612 годе в сценарии ни слова (QA c2, повтор)."""
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.educational_goals = ["Воспитание гражданской идентичности", "Знакомство с событиями 1612 года"]
        issues = _issues(v, n)
        self.assertIn(("GOAL-UNCOVERED", "warning", "concept"), issues)
        self.assertEqual(1, sum(code == "GOAL-UNCOVERED" for code, _, _ in issues))
        v["timeline"][1]["teacher_script"] += " Вспомним, что произошло в 1612 году."
        self.assertNotIn("GOAL-UNCOVERED", {code for code, _, _ in _issues(v, n)})

    def test_century_needs_source(self):
        n, v = setup("ex1_knowledge_day")
        v["timeline"][1]["teacher_script"] += " Этот обычай появился в XVII веке."
        self.assertIn(("FACT-UNREGISTERED", "warning", f"timeline.{v['timeline'][1]['block_id']}"), _issues(v, n))



# Проверенные цитаты о Рождестве из обновлённого каталога (PR #28): дата и православные традиции, о других странах ни слова.
CHRISTMAS_FRAGMENTS = [
    {"fragment_id": "frag_test_christmas_001", "source_id": "src_test_christmas", "verification_status": "verified",
     "events": ["christmas"], "topics": [], "regions": ["RU"],
     "quote": "Рождество Христово отмечается в ночь с 6 на 7 января. Традиции включают сочельник, приготовление кутьи и колядование."},
    {"fragment_id": "frag_test_christmas_002", "source_id": "src_test_christmas", "verification_status": "verified",
     "events": ["christmas"], "topics": [], "regions": ["RU"],
     "quote": "Рождество Христово, которое православные верующие отмечают в ночь с 6 на 7 января, - особенный, торжественный день."},
]


def catalog_with(fragments):
    """Каталог, в котором у события уже есть проверенные фрагменты (как после обновления каталога)."""
    base = catalog()
    return dataclasses.replace(base, fragments={**base.fragments, **{f["fragment_id"]: f for f in fragments}})


class CultureSourcesTest(unittest.TestCase):
    """Один проверенный источник у события не отключает проверку остальных утверждений о традициях (QA 14.11)."""

    def issues(self, text, fragments=(), event_id="christmas", where="material"):
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.event_id = event_id
        if where == "material":
            v["materials"][0]["content"] = text
            loc = f"materials.{v['materials'][0]['material_id']}"
        else:
            v["timeline"][1]["teacher_script"] += " " + text
            loc = f"timeline.{v['timeline'][1]['block_id']}"
        found = validate_variant(v, n, catalog_with(list(fragments)), settings().generation())
        return [i for i in found if i.code == "CULTURE-UNSOURCED" and i.location == loc]

    def test_federal_fragment_applies_to_region(self):
        """Фрагменты с регионом `RU` подходят запросу из Свердловской области (`RU-SVE`)."""
        found = {f["fragment_id"] for f in catalog_with(CHRISTMAS_FRAGMENTS).verified_fragments("christmas", "RU-SVE")}
        self.assertLessEqual({f["fragment_id"] for f in CHRISTMAS_FRAGMENTS}, found)

    def test_other_countries_flagged_with_sources(self):
        """Источник о дате Рождества есть, а традиции Японии и Италии он не подтверждает."""
        for text in ("В Японии традиционно едят рождественский торт.",
                     "Италия:\n- Украшают вертеп\n- Дарят подарки утром",
                     "Во многих итальянских домах ставят вертеп.",
                     "Рождественские традиции Германии: пекут штоллен и украшают дом венками."):
            with self.subTest(text=text):
                self.assertTrue(self.issues(text, CHRISTMAS_FRAGMENTS))
        self.assertTrue(self.issues("В Японии традиционно едят рождественский торт.", CHRISTMAS_FRAGMENTS, where="block"))

    def test_capital_letters(self):
        """«В Японии традиционно…» ловится так же, как «в Японии традиционно…»: текст приводится к нижнему регистру."""
        for text in ("в Японии традиционно едят торт.", "В Японии традиционно едят торт.", "В ЯПОНИИ ТРАДИЦИОННО ЕДЯТ ТОРТ.",
                     "Во Франции принято дарить подарки.", "У Татар принято печь чак-чак.", "ИТАЛИЯ:\n- Украшают вертеп"):
            with self.subTest(text=text):
                self.assertTrue(self.issues(text))
                self.assertTrue(self.issues(text, CHRISTMAS_FRAGMENTS))

    def test_confirmed_by_source(self):
        """Утверждение о стране, которая есть в проверенном фрагменте, не помечается."""
        russia = dict(CHRISTMAS_FRAGMENTS[0], fragment_id="frag_test_christmas_003",
                      quote="В России в сочельник готовят кутью, а дети ходят колядовать.")
        self.assertFalse(self.issues("В России в сочельник готовят кутью.", [russia]))
        self.assertTrue(self.issues("В России в сочельник готовят кутью.", CHRISTMAS_FRAGMENTS))
        # «У народов Сибири» не подтверждается фрагментом, где есть только слово «народ».
        unity = {"fragment_id": "frag_test_unity", "source_id": "src_test_unity", "verification_status": "verified",
                 "events": ["unity_day"], "regions": ["RU"], "quote": "Праздник посвящён событиям 1612 года, когда народное ополчение освободило Москву."}
        self.assertTrue(self.issues("У народов Сибири принято устраивать праздник.", [unity], event_id="unity_day"))

    def test_not_a_tradition_claim(self):
        """Без страны или без утверждения о традиции предупреждения нет, и с источником, и без."""
        for text in ("Индивидуальная работа:\n- Готовят ответы", "Россия - наша общая страна.\n- Ставят задачи",
                     "В индивидуальном порядке ученики готовят ответы.", "Подумайте, как праздник отмечают в вашей семье."):
            with self.subTest(text=text):
                self.assertFalse(self.issues(text))
                self.assertFalse(self.issues(text, CHRISTMAS_FRAGMENTS))

    def test_quote_is_a_claim_not_a_task(self):
        """Прогон 14.11 (Рождество 5-8): в цитату попадает утверждение «Почему в Италии популярны вертепы?»,
        а не задание «Изучите, как итальянцы отмечают Рождество» и не открытый вопрос."""
        text = ("Группа 1: Италия\nИзучите, как итальянцы отмечают Рождество. Найдите ответы на вопросы:\n"
                "- Какой традиционный ужин готовят итальянцы?\n- Почему в Италии популярны вертепы?")
        self.assertEqual(_culture_claims(text)[0][0], "Почему в Италии популярны вертепы?")
        found = self.issues(text)
        self.assertIn("Почему в Италии популярны вертепы?", found[0].message)
        self.assertFalse(self.issues("Изучите, как итальянцы отмечают Рождество.\n- Какой ужин готовят итальянцы?\n- Когда дарят подарки в Италии?"))

    def test_recorded_runs_with_updated_catalog(self):
        """Записанные прогоны о Рождестве: с цитатами из обновлённого каталога традиции других стран по-прежнему помечаются."""
        sources_text = " ".join(f["quote"] for f in CHRISTMAS_FRAGMENTS).lower()
        for name, material_id in (("replay_gigachat_content_christmas", "research_cards"),
                                  ("replay_gigachat_content_christmas_v2", "country_cards")):
            with self.subTest(name=name):
                outcome, _ = replay(name)
                material = next(m for m in outcome.project["variants"][0]["materials"] if m["material_id"] == material_id)
                claims = _culture_claims(material["content"])
                self.assertTrue(claims)
                self.assertTrue([quote for quote, places in claims if not _confirmed(places, sources_text)])


class ContentCheckRunTest(unittest.TestCase):
    """Записанные контрольные прогоны 13.11: что теперь видно в отчёте качества и в читаемой версии."""

    def test_christmas(self):
        outcome, client = replay("replay_gigachat_content_christmas")
        self.assertEqual(outcome.project["status"], "completed")
        variant = outcome.project["variants"][0]
        issues = {(i["code"], i["location"]) for i in variant["quality_report"]["issues"]}
        collage = next(b["block_id"] for b in variant["timeline"] if "коллаж" in b["title"].lower())
        self.assertIn(("INNER-TIMING", f"timeline.{collage}"), issues)
        self.assertIn(("CULTURE-UNSOURCED", "materials.research_cards"), issues)
        self.assertNotIn("FACT-UNREGISTERED", {code for code, _ in issues})
        self.assertNotIn("EVENT-MIXUP", {code for code, _ in issues})

    def test_unity_day(self):
        outcome, _ = replay("replay_gigachat_content_unity_day")
        variant = outcome.project["variants"][0]
        codes = {i["code"] for i in variant["quality_report"]["issues"]}
        # О 1612 годе в прогоне ни слова, а задача из карточки его обещает (замечание QA 14.11).
        self.assertEqual(codes, {"CULTURE-UNSOURCED", "GOAL-UNCOVERED"})
        joined = "\n".join(_variant_texts(variant))
        self.assertNotIn("culture_cards", joined)
        self.assertNotIn("project_template", joined)

    def test_markdown_without_ids(self):
        for name in ("replay_gigachat_content_christmas", "replay_gigachat_content_unity_day", "replay_gigachat_matrix_m2_vote"):
            with self.subTest(name=name):
                outcome, _ = replay(name)
                text = variant_to_markdown(outcome.project["variants"][0])
                self.assertEqual(re.findall(r"\bblock_\d+\b", text), [])
                for material in outcome.project["variants"][0]["materials"]:
                    self.assertNotIn(material["material_id"], text)

    def test_christmas_v2_without_extra_materials_calls(self):
        """Повторный прогон 13.11: альтернатива «если поговорить не с кем…» распознаётся, лишних вызовов нет."""
        outcome, client = replay("replay_gigachat_content_christmas_v2")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("materials"), 1)
        issues = {(i["code"], i["location"]) for i in outcome.project["variants"][0]["quality_report"]["issues"]}
        # «Немцы любят украшать…», «Во многих итальянских домах…» - тоже сведения о традициях без источника.
        self.assertIn(("CULTURE-UNSOURCED", "materials.country_cards"), issues)

    def test_sverdlovsk_v2_fact_claims_shape(self):
        """Факты вида {"claim": ..., "source_id", "fragment_id"} принимаются без повтора этапа и сохраняют источник."""
        outcome, client = replay("replay_gigachat_content_sverdlovsk_v2")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("scenario_block"), len(outcome.project["variants"][0]["timeline"]))
        sources = {s["source_id"] for s in outcome.project["variants"][0]["sources"]}
        self.assertIn("src_sverdlovsk_oblast_day_regional_02", sources)

    def test_family_alternatives_from_runs(self):
        from app.validation.checks import FAMILY_ALTERNATIVE
        for text in ("Если поговорить не с кем, ничего страшного - просто подумай, что тебе самому интересно узнать об этом празднике.",
                     "Если поговорить не с кем или хочется узнать что-то другое, прочитай книгу или посмотри фильм о Рождестве."):
            self.assertTrue(FAMILY_ALTERNATIVE.search(text), text)
        self.assertFalse(FAMILY_ALTERNATIVE.search("Заполни анкету вместе с родителями и принеси её."))

    def test_family_task_fixed_without_model(self):
        """Задание семье без альтернативы и пометки чинится программой: этап материалов не повторяется."""

        class NoAlternative(ReplayLLM):
            def generate(self, **kwargs):
                response = super().generate(**kwargs)
                if kwargs["task_name"] != "materials":
                    return response
                from app.llm.jsonx import extract_json
                data = extract_json(response.text)
                for m in data["materials"]:
                    if m.get("family_task"):
                        m["type"] = "activity_card"
                        m["title"] = "Узнай деталь о празднике"
                        m["content"] = "Дорогие ребята! Спросите у близкого взрослого, как в вашей семье отмечают праздник, и запишите."
                return dataclasses.replace(response, text=json.dumps(data, ensure_ascii=False))

        directory = FIXTURES / "replay_gigachat_content_christmas_v2"
        client = NoAlternative(directory)
        from app.generation.pipeline import Generator
        outcome = Generator(settings(), catalog(), client).run(json.loads((directory / "request.json").read_text(encoding="utf-8")))
        variant = outcome.project["variants"][0]
        self.assertEqual(client.calls.count("materials"), 1)
        self.assertNotIn("VAL-005", {i["code"] for i in variant["quality_report"]["issues"]})
        family = next(m for m in variant["materials"] if m["material_id"] == "family_handout")
        self.assertEqual(family["type"], "handout")
        self.assertIn("(по желанию, до мероприятия)", family["title"])
        self.assertIn("выполни задание сам", family["content"])

    def test_family_task_rules(self):
        from app.generation.pipeline import fix_family_tasks
        from app.validation.checks import FAMILY_ALTERNATIVE
        materials = [
            {"material_id": "a", "type": "worksheet", "title": "Интервью", "content": "Спроси дома и запиши.", "family_task": True},
            {"material_id": "b", "type": "handout", "title": "Письмо (по желанию)", "content": "Уважаемые родители! Расскажите ребёнку.", "family_task": True},
            {"material_id": "c", "type": "handout", "title": "Задание (по желанию)", "content": "Спроси дома. Если не с кем, придумай сам.", "family_task": True},
        ]
        fixes = {f["material_id"]: f["fixed"] for f in fix_family_tasks(materials, ["family"])}
        self.assertEqual(fixes, {"a": ["type", "title", "alternative"], "b": ["alternative"]})
        self.assertTrue(all(FAMILY_ALTERNATIVE.search(m["content"]) for m in materials))
        self.assertIn("ребёнок может сделать его сам", materials[1]["content"])
        other = [{"material_id": "d", "type": "handout", "title": "t", "content": "c", "family_task": True}]
        fix_family_tasks(other, ["citizenship"])
        self.assertFalse(other[0]["family_task"])

    def test_group_count_words(self):
        self.assertEqual(describe([6, 6, 6, 6]), "4 группы: 6, 6, 6, 6")
        self.assertEqual(describe([5, 5, 5, 5, 5]), "5 групп: 5, 5, 5, 5, 5")
        self.assertEqual(describe([2, 2, 2]), "3 пары")


if __name__ == "__main__":
    unittest.main()