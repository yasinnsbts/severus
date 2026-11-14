"""Третий баг-лист QA 14.11 (сборка с reasoning medium): BUG-16, BUG-20, BUG-21.

- BUG-16: в реплике педагога ID материала с опечаткой в числе: «commitments_book_pages» при материале
  «commitment_book_pages» (трасса job_f37a1bca…, v2, block_04).
- BUG-20: 5-минутный блок объявляет 15-минутную работу следующего этапа и выступления после неё;
  проверка считала, что всё это в нём самом (трасса job_f37a1bca…, v1, block_02). Случай «13 пар × 4 мин»
  из той же заявки закрыт правкой «время на обсуждение - работа» (`test_run_1115.py`).
- BUG-21: GigaChat закрыл реплику экранированной кавычкой и так же экранировал следующий ключ
  («…класса\\",\\n\\"pupil_actions\\": [»); разбор уносил `pupil_actions` и `role_ids` в текст, блок трижды
  не проходил схему, задача падала (трасса job_c7df9e8e…). Ответы из трассы - в `fixtures/bug21_escaped_key_quote`.
"""

import unittest

from app.contracts.llm import STAGE_MODELS
from app.generation.humanize import humanize_text
from app.llm.jsonx import extract_json
from app.validation.inner_timing import inner_timing_problems
from tests.helpers import ROOT

FIXTURES = ROOT / "tests" / "fixtures" / "bug21_escaped_key_quote"

# Реплика блока 2 (5 мин) из трассы; следующий блок - «Работа в командах над проектом» на 15 мин.
ANNOUNCE_BLOCK = """Отлично! Теперь посмотрите, кто в вашей команде. Вы будете работать вместе, помогать друг другу и делиться идеями.

На ваших рабочих листах (показывает рабочие листы) вы запишите ваши идеи, а потом воспользуетесь наборами для конструирования, чтобы воплотить эти идеи в жизнь. У вас будет 15 минут на всю эту работу, после чего каждая команда представит свой проект всему классу.

Есть ли вопросы по организации работы?"""


class Bug16PluralIdTest(unittest.TestCase):
    NAMES = {"commitment_book_pages": "«Странички для книги личных обязательств»", "station_cards": "«Карточки станций»"}

    def test_plural_typo_replaced(self):
        text, ids = humanize_text("Учитель раздаёт commitments_book_pages и просит подписать.", self.NAMES)
        self.assertEqual(text, "Учитель раздаёт «Странички для книги личных обязательств» и просит подписать.")
        self.assertEqual(ids, ["commitments_book_pages"])
        self.assertEqual(humanize_text("Возьмите station_card.", self.NAMES)[0], "Возьмите «Карточки станций».")

    def test_trace_paren_keeps_verb(self):
        """Скобка из трассы: слово «странички» повторяет название и уходит, глагол остаётся."""
        text, _ = humanize_text("…на весь учебный год.\" (раздает странички commitments_book_pages)", self.NAMES)
        self.assertEqual(text, "…на весь учебный год.\" (раздает «Странички для книги личных обязательств»)")

    def test_ambiguous_shape_not_guessed(self):
        """Если под форму подходят два ID, программа не угадывает: ID остаётся, его покажет TECH-ID-IN-TEXT."""
        names = {"team_card": "«Карточка команды»", "team_cards": "«Карточки команд»"}
        self.assertEqual(humanize_text("Раздайте teams_card.", names), ("Раздайте teams_card.", []))


class Bug20AnnounceBlockTest(unittest.TestCase):
    def test_trace_block(self):
        block = {"duration_minutes": 5, "teacher_script": ANNOUNCE_BLOCK, "pupil_actions": []}
        self.assertEqual(inner_timing_problems(block, groups_count=5, pairs_count=0, next_duration=15,
                                               next_title="Работа в командах над проектом 'Класс мечты'",
                                               next_text="Сейчас у вас 10 минут на выполнение задания."), [])

    def test_short_work_then_presentations_still_flagged(self):
        """Работа короче блока и выступления всех групп без времени на них - по-прежнему предупреждение."""
        block = {"duration_minutes": 12, "teacher_script": "У вас есть 10 минут на коллаж. Затем каждая команда представит коллаж.",
                 "pupil_actions": []}
        self.assertEqual(inner_timing_problems(block, groups_count=4, pairs_count=0),
                         ["после 10 мин работы на выступления 4 групп остаётся 2 мин"])


class Bug21EscapedKeyQuoteTest(unittest.TestCase):
    def test_trace_responses_pass_schema(self):
        """Оба ответа из трассы (первый и повтор) разбираются целиком и проходят схему этапа."""
        for name in ("call_0006_scenario_block.txt", "call_0007_scenario_block.txt"):
            with self.subTest(name=name):
                data = extract_json((FIXTURES / name).read_text(encoding="utf-8"))
                block = data["block"]
                self.assertTrue(block["teacher_script"].endswith("презентация общих работ и украшение класса"))
                self.assertEqual(block["role_ids"], ["teacher_1", "pupils_all"])
                self.assertEqual(len(block["pupil_actions"]), 3)
                STAGE_MODELS["scenario_block"].model_validate(data)

    def test_quotes_inside_text_untouched(self):
        """Обычные экранированные кавычки в реплике («Начинайте!», «Книга наших обещаний») не трогаются."""
        raw = '{"teacher_script": "Скажите: \\"Начинайте!\\", а потом \\"Книга наших обещаний\\".", "role_ids": ["teacher_1"]}'
        self.assertEqual(extract_json(raw)["teacher_script"], 'Скажите: "Начинайте!", а потом "Книга наших обещаний".')
        broken = '{"teacher_script": "Начинаем!\\",\\n\\"role_ids\\": ["teacher_1"]}'
        self.assertEqual(extract_json(broken), {"teacher_script": "Начинаем!", "role_ids": ["teacher_1"]})


if __name__ == "__main__":
    unittest.main()