"""Тестовый сценарий аналитика 20.11: «Праздник Весны и Труда», 7 класс, 19 учеников, 60 минут («Весёлая ярмарка
трудовых талантов»). 4 группы на 3 станции по 6-7 минут в блоке на 20 минут; станция «Повара» с настоящим салатом;
сувениры и открытки в репликах, но не в материалах; ремарка «(Переходит к подготовке следующего блока.)»."""

import tempfile
import unittest
from pathlib import Path

from app.generation.grouping import station_budget
from app.generation.humanize import drop_meta_notes
from app.generation.pipeline import Generator
from app.llm.fixture import FixtureLLM
from app.trace import RunTrace
from app.validation.checks import validate_variant
from app.validation.content_rules import covered_text, food_tasks, missing_props
from app.validation.inner_timing import inner_timing_problems
from app.validation.issue_format import category
from tests.helpers import catalog, golden, request, settings
from tests.test_validation_render import setup

STATIONS = ("Итак, ребята, сейчас мы отправимся на нашу ярмарку профессий. Всего у нас три станции: \"Строители\", \"Флористы\" "
            "и \"Повара\". Каждая команда посетит все три станции, потратив примерно шесть-семь минут на каждой. Сейчас первые пять "
            "человек направляются на станцию \"Строители\", вторые пять - на станцию \"Флористы\", третьи пять - на станцию \"Повара\", "
            "а четвёртая группа отдыхает одну минуту, прежде чем присоединиться ко второй волне. Через семь минут команды меняются местами.")
FINAL = ("(Достаёт небольшие сувениры или благодарственные открытки.) \"А сейчас предлагаю каждому взять сувенир на память о нашем "
         "празднике труда.\" (Раздаёт сувениры, сопровождая это тёплыми словами благодарности каждому ребёнку.)")


def timing(text: str, minutes: int, groups: int) -> list[str]:
    block = {"duration_minutes": minutes, "pupil_actions": [], "teacher_script": text}
    return inner_timing_problems(block, groups_count=groups, pairs_count=0, next_duration=15, next_title="Коллективное создание плаката")


class StationsTest(unittest.TestCase):
    def test_more_groups_than_stations(self):
        self.assertEqual(timing(STATIONS, 20, 4), ["станции по кругу: 4 группы на 3 станции: одна группа всё время ждёт, "
                                                   "смен 4 × 6 мин = 24 мин, а на блок 20 мин"])
        self.assertEqual(timing(STATIONS, 20, 3), [])
        self.assertEqual(timing(STATIONS, 30, 4), [])

    def test_stations_one_by_one_with_whole_class(self):
        """«Первая станция… Переходим ко второй станции» - станции по очереди всем классом, никто не ждёт."""
        text = ("Первая станция нашего квеста называется \"Исторический факт\". Время вышло, послушаем ваши рассказы. "
                "Переходим ко второй станции - \"Символы региона\". Пройдём маршрут по кругу.")
        self.assertFalse(any("ждёт" in p for p in timing(text, 20, 6)))

    def test_hint_in_block_line(self):
        groups = [5, 5, 5, 4]
        self.assertEqual(station_budget("small_groups", groups, {"title": "Ярмарка профессий (работа на станциях)"}, 20),
                         "станции по кругу: 4 группы - 4 станции, не больше 4,5 мин на станцию с переходом")
        self.assertEqual(station_budget("pairs", [2] * 12, {"title": "Прохождение станций"}, 15),
                         "станции по кругу: 12 пар - станций столько же, но на каждую выйдет меньше 2 мин; лучше 4 станции и столько же групп")
        for title in ("Станция Ремёсел", "Объяснение условий квеста", "Представление станций", "Коллективное создание плаката"):
            with self.subTest(title=title):
                self.assertEqual(station_budget("small_groups", groups, {"title": title}, 20), "")
        self.assertEqual(station_budget("whole_class", [19], {"title": "Работа на станциях"}, 20), "")


class FoodTest(unittest.TestCase):
    def test_real_food(self):
        self.assertTrue(food_tasks(["На станциях строят конструкции, составляют цветочную композицию или готовят блюдо."], []))
        self.assertTrue(food_tasks([], ["А на станции \"Повара\" - приготовить простое блюдо из предложенных ингредиентов."]))
        self.assertTrue(food_tasks([], ["Станция \"Повара\": Овощи нарезанные (4 порции), миски и ложки (4 комплекта)."]))

    def test_not_a_task(self):
        """Рассказ о традициях и карточки кухни без готовки - не задание с едой."""
        self.assertEqual(food_tasks([], ["Люди благодарят природу за щедрость, готовят угощения из свежих продуктов."]), [])
        self.assertEqual(food_tasks([], ["Карточка 1: Блюдо: Пироги с ягодами. Ингредиенты: мука, ягоды, сахар, масло."]), [])
        self.assertEqual(food_tasks(["Обсуждают, какие блюда готовят на праздник в семье."], []), [])


class PropsTest(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(missing_props([FINAL], "Карточки с заданиями для станций. Материалы для создания плаката."),
                         ["сувениры", "открытки"])
        self.assertEqual(missing_props([FINAL], "Сувениры для участников: по одному на каждого. Открытки с благодарностью."), [])

    def test_self_made(self):
        self.assertEqual(missing_props(["Давайте аккуратно сложим готовые сувениры вот сюда, чтобы позже вручить их друг другу."], ""), [])

    def test_in_validation(self):
        n, v = setup("ex1_knowledge_day")
        v["timeline"][-1]["teacher_script"] = FINAL
        v["timeline"][1]["pupil_actions"] = ["Готовят блюдо по рецепту на станции «Повара»."]
        issues = {(i.code, i.location) for i in validate_variant(v, n, catalog(), settings().generation())}
        self.assertIn(("PROPS-MISSING", f"timeline.{v['timeline'][-1]['block_id']}"), issues)
        self.assertIn(("FOOD-TASK", f"timeline.{v['timeline'][1]['block_id']}"), issues)
        self.assertEqual((category("FOOD-TASK"), category("PROPS-MISSING")), ("safety", "materials"))
        self.assertIn("Сувениры", covered_text({"materials": [{"title": "Сувениры", "dependencies": []}]}, {}))


class StageDirectionTest(unittest.TestCase):
    def test_removed(self):
        variant = {"timeline": [{"block_id": "block_05", "teacher_script": "Спасибо всем за вашу активность и творчество!\n\n"
                                 "(Переходит к подготовке следующего блока.)", "pupil_actions": []}], "materials": []}
        changes = drop_meta_notes(variant)
        self.assertEqual(variant["timeline"][0]["teacher_script"], "Спасибо всем за вашу активность и творчество!")
        self.assertEqual(changes, [{"field": "timeline.block_05.teacher_script", "removed": ["(Переходит к подготовке следующего блока.)"]}])


class FoodPromptTest(unittest.TestCase):
    def test_rule_in_system_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            trace = RunTrace(run_dir, full_prompts=True, full_responses=False, secrets=[])
            Generator(settings(), catalog(), FixtureLLM([golden("ex1_knowledge_day")]), trace=trace).run(request("ex1_knowledge_day"))
            for call in sorted((run_dir / "calls").iterdir()):
                self.assertIn("Без настоящей еды, готовки и дегустации", (call / "prompt.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()