"""QA-кейс 19.11: содержательные ошибки из `test_case.docx`.

Сценарий: Праздник Весны и Труда, 7 класс, 19 учеников, 60 минут.
Станции, еда и реквизит уже ловятся (PR #35); дубль финала пока помечен `expectedFailure`.
Когда проверка появится, тест начнёт проходить — декоратор нужно снять.
"""

import unittest

from app.generation.humanize import drop_meta_notes
from app.validation.checks import validate_variant
from app.validation.inner_timing import inner_timing_problems
from tests.helpers import catalog, settings
from tests.test_validation_render import setup

STATION_TEXT = (
    "Итак, ребята, сейчас мы отправимся на нашу ярмарку профессий. Всего у нас три станции: "
    "«Строители», «Флористы» и «Повара». Каждая команда посетит все три станции, потратив примерно "
    "шесть-семь минут на каждой. Сейчас первые пять человек направляются на станцию «Строители», "
    "вторые пять — на станцию «Флористы», третьи пять — на станцию «Повара», а четвёртая группа "
    "отдыхает одну минуту, прежде чем присоединиться ко второй волне. Через семь минут команды "
    "меняются местами."
)


def messages(v, n):
    """Сообщения проверок по этапам сценария."""
    return " ".join(i.message for i in validate_variant(v, n, catalog(), settings().generation())
                    if i.location.startswith("timeline."))


class StationRotationTest(unittest.TestCase):
    """BUG-25: 4 группы, 3 станции, 20 минут, 6-7 минут на станцию."""

    def test_four_groups_three_stations_do_not_fit_twenty_minutes(self):
        block = {"duration_minutes": 20, "teacher_script": STATION_TEXT, "pupil_actions": []}
        problems = inner_timing_problems(
            block, groups_count=4, pairs_count=0, next_duration=15,
            next_title="Коллективное создание плаката", next_text="",
        )
        self.assertTrue(problems, "4 группы × 3 станции × 6-7 минут не помещаются в 20 минут")


class MaterialsConsistencyTest(unittest.TestCase):
    """BUG-26: сувениры и открытки упомянуты в финале, но не заявлены в материалах."""

    def test_souvenirs_mentioned_but_not_declared(self):
        n, v = setup("ex3_labour_day")
        v["timeline"][-1]["teacher_script"] += " В конце педагог раздаёт сувениры и благодарственные открытки."
        text = messages(v, n).lower()
        self.assertIn("сувенир", text, "сервис должен сказать, что реквизит не заявлен в материалах")


class FoodSafetyTest(unittest.TestCase):
    """BUG-27: приготовление еды без условий гигиены и пищевых ограничений."""

    def test_cooking_task_requires_safety_conditions(self):
        n, v = setup("ex3_labour_day")
        v["timeline"][0]["teacher_script"] += " На станции «Повара» приготовьте салат из нарезанных овощей."
        text = messages(v, n).lower()
        self.assertTrue(any(word in text for word in ("гигиен", "аллерг", "пищев")),
                        "сервис должен требовать условия безопасности для задания с едой")


class FinaleDuplicateTest(unittest.TestCase):
    """BUG-28: служебная фраза перехода и дубль финала."""

    def test_technical_phrase_removed_from_script(self):
        n, v = setup("ex3_labour_day")
        v["timeline"][-2]["teacher_script"] += " (Переходит к подготовке следующего блока.)"
        drop_meta_notes(v)
        text = " ".join(b["teacher_script"] for b in v["timeline"]).lower()
        self.assertNotIn("следующего блока", text, "служебная фраза не должна попадать в сценарий")

    @unittest.expectedFailure
    def test_duplicate_finale(self):
        n, v = setup("ex3_labour_day")
        v["timeline"][-2]["title"] = "Подведение итогов и рефлексия"
        v["timeline"][-1]["title"] = "Заключительная церемония"
        text = messages(v, n).lower()
        self.assertIn("дублир", text, "сервис должен замечать дубль финала")


if __name__ == "__main__":
    unittest.main()
