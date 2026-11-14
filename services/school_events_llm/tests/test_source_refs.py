"""Ссылки на источники в тексте и выдуманные документы (прогон 14.11, День Свердловской области, 6 класс).

В карточке для учеников модель вставила служебные ссылки «(fact_claims: src_…/frag_…)» прямо в текст,
а `fact_claims` материалов оставила пустым: в тексте был технический мусор (`TECH-ID-IN-TEXT`), проверенный
факт о 1934 годе считался незарегистрированным (`FACT-UNREGISTERED`), а источник не попал в список.
В той же карточке - «указ губернатора». Сначала он считался выдуманным, но фрагмент о 17 января взят из
«Указа Губернатора Свердловской области № 1022-УГ»: документ подтверждает название источника (прогон 15.11).
"""

import copy
import dataclasses
import json
import unittest

from app.generation.pipeline import Generator
from app.generation.source_refs import document_mentions, move_source_refs
from app.llm.jsonx import extract_json
from app.validation.checks import validate_variant
from tests.helpers import ROOT, catalog, settings
from tests.test_material_ids import ReplayLLM
from tests.test_validation_render import setup

# Текст карточки из прогона 14.11 как есть (номер фрагмента у модели с опечаткой: frag_sverdlov_002).
Q08_CARD = """ФАКТЫ ОБ ИСТОРИИ СВЕРДЛОВСКОЙ ОБЛАСТИ

1. День образования Свердловской области установлен указом губернатора Свердловской области и отмечается ежегодно 17 января.
(fact_claims: src_sverdlovsk_oblast_day_regional_01/frag_sverdlov_001)

2. 17 января 1934 года Уральская область была разделена на три области: Свердловскую, Челябинскую и Обско-Иртышскую.
(fact_claims: src_sverdlovsk_oblast_day_regional_02/frag_sverdlov_002)"""


def fragments(event_id="sverdlovsk_oblast_day"):
    return catalog().verified_fragments(event_id, "RU-SVE")


def bare_variant(content, script=""):
    return {"timeline": [{"block_id": "block_01", "teacher_script": script, "pupil_actions": ["Слушают"]}],
            "materials": [{"material_id": "sources_set", "content": content, "teacher_notes": ""}],
            "teacher_instructions": [], "fact_claims": []}


class MoveSourceRefsTest(unittest.TestCase):
    def test_q08_card(self):
        """Ссылки убраны из текста; факт о 1934 годе записан с верным фрагментом. Фраза с указом не записывается:
        в цитате фрагмента указа нет, он только в названии источника."""
        variant = bare_variant(Q08_CARD)
        changes = move_source_refs(variant, fragments())
        content = variant["materials"][0]["content"]
        self.assertNotIn("src_", content)
        self.assertNotIn("fact_claims", content)
        self.assertIn("17 января 1934 года Уральская область была разделена", content)
        self.assertEqual([(c["fragment_id"], c["location"]) for c in variant["fact_claims"]], [("frag_sverdlovsk_002", "sources_set")])
        self.assertTrue(variant["fact_claims"][0]["text"].startswith("17 января 1934 года"))
        self.assertEqual(changes[0]["field"], "materials.sources_set.content")
        self.assertEqual(len(changes[0]["refs"]), 2)

    def test_bare_ref_in_block(self):
        """Ссылка без скобок в реплике педагога; фраза с датой из фрагмента регистрируется."""
        variant = bare_variant("", "Сегодня особый день. 17 января - День образования Свердловской области. "
                                   "источник: src_sverdlovsk_oblast_day_regional_01 Давайте начнём!")
        move_source_refs(variant, fragments())
        script = variant["timeline"][0]["teacher_script"]
        self.assertNotIn("src_", script)
        self.assertIn("Свердловской области. Давайте начнём!", script)
        self.assertEqual(variant["fact_claims"][0]["fragment_id"], "frag_sverdlovsk_001")
        self.assertEqual(variant["fact_claims"][0]["location"], "block_01")

    def test_unknown_or_unsupported_only_removed(self):
        """Неизвестный источник и фраза со своими датами просто вырезаются из текста, факт не записывается."""
        for text in ("В 1723 году основан Екатеринбург. (источник: src_unknown_01)",
                     "Область создана 17 января 1934 года, а 5 марта 1935 года появился герб. [src_sverdlovsk_oblast_day_regional_02]"):
            with self.subTest(text=text):
                variant = bare_variant(text)
                move_source_refs(variant, fragments())
                self.assertNotIn("src_", variant["materials"][0]["content"])
                self.assertEqual(variant["fact_claims"], [])

    def test_fragment_ids_in_block_script(self):
        """Второй баг-лист 14.11 (BUG-16, job_20261114_173643_41aa2f): `frag_new_year_001`, `frag_new_year_005`
        в реплике педагога - несколько ID в скобках, подпись «fragment_id:», ссылка без скобок."""
        cases = {
            "Пётр I перенёс Новый год на 1 января 1700 года (frag_new_year_001, frag_new_year_005). Давайте обсудим.":
                "Пётр I перенёс Новый год на 1 января 1700 года. Давайте обсудим.",
            "Пётр I перенёс Новый год на 1 января 1700 года (fragment_id: frag_new_year_001).":
                "Пётр I перенёс Новый год на 1 января 1700 года.",
            "Ребята! Согласно frag_new_year_001, Пётр I постановил начать год с 1 января 1700 года.":
                "Ребята! Пётр I постановил начать год с 1 января 1700 года.",
            "Пётр I постановил начать год с 1 января 1700 года [источники: frag_new_year_001; frag_new_year_005].":
                "Пётр I постановил начать год с 1 января 1700 года.",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                variant = bare_variant("", text)
                move_source_refs(variant, fragments("new_year"))
                self.assertEqual(variant["timeline"][0]["teacher_script"], expected)
                self.assertEqual([c["fragment_id"] for c in variant["fact_claims"]], ["frag_new_year_001"])

    def test_parentheses_with_meaning_kept(self):
        """Скобки, где есть смысл кроме ссылки, остаются без ID; фраза без года и даты фактом не записывается."""
        variant = bare_variant("", "Раздайте карточки (по одной на команду, см. frag_new_year_002). Начинаем. Это дата (в 1700 году).")
        move_source_refs(variant, fragments("new_year"))
        self.assertEqual(variant["timeline"][0]["teacher_script"], "Раздайте карточки (по одной на команду). Начинаем. Это дата (в 1700 году).")
        self.assertEqual(variant["fact_claims"], [])

    def test_text_without_refs_untouched(self):
        variant = bare_variant("Карточка: герб области.\n\nОбсудите в группе.")
        before = copy.deepcopy(variant)
        self.assertEqual(move_source_refs(variant, fragments()), [])
        self.assertEqual(variant, before)

    def test_validation_after_move(self):
        """После переноса нет TECH-ID-IN-TEXT и FACT-UNREGISTERED. DOC-UNSOURCED тоже нет: указ губернатора -
        источник проверенного фрагмента о 17 января (прогон 15.11)."""
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.event_id = "sverdlovsk_oblast_day"
        material = v["materials"][0]
        material["content"] = Q08_CARD
        move_source_refs(v, fragments())
        issues = {(i.code, i.location) for i in validate_variant(v, n, catalog(), settings().generation())}
        loc = f"materials.{material['material_id']}"
        self.assertNotIn(("TECH-ID-IN-TEXT", loc), issues)
        self.assertNotIn(("FACT-UNREGISTERED", loc), issues)
        self.assertNotIn(("DOC-UNSOURCED", loc), issues)


class DocumentMentionsTest(unittest.TestCase):
    def test_documents_found(self):
        for text in ("Карточка с выдержкой из указа губернатора Свердловской области №1022-УГ от 23 сентября 2008 г.",
                     "День области установлен указом губернатора Свердловской области.",
                     "Копия указа губернатора Свердловской области о празднике.",
                     "Президент подписал указ.", "ПОСТАНОВЛЕНИЕ ПРАВИТЕЛЬСТВА 2012 ГОДА.", "Федеральный закон о праздниках.",
                     "Закон Свердловской области о символах."):
            with self.subTest(text=text):
                self.assertTrue(document_mentions(text))

    def test_not_documents(self):
        for text in ("Знайте законы дружбы.", "По приказу капитана команды начинаем.", "Законодательное собрание области заседает.",
                     "Указатель стоит у двери.", "Распоряжения педагога выполняются быстро."):
            with self.subTest(text=text):
                self.assertFalse(document_mentions(text))

    def test_document_in_fragment_not_flagged(self):
        """Документ подтверждают цитата проверенного фрагмента или название его источника. Издатель и номер из фразы
        тоже должны там быть: «указ губернатора» и «№ 1022-УГ» есть в названии источника, «указ Президента»
        и «№ 555-УГ» - нет."""
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.event_id = "sverdlovsk_oblast_day"
        loc = f"materials.{v['materials'][0]['material_id']}"

        def codes(text, cat=None):
            v["materials"][0]["content"] = text
            return {(i.code, i.location) for i in validate_variant(v, n, cat or catalog(), settings().generation())}

        self.assertNotIn(("DOC-UNSOURCED", loc), codes("День области установлен указом губернатора Свердловской области."))
        self.assertNotIn(("DOC-UNSOURCED", loc), codes("Праздник назван в указе губернатора № 1022-УГ."))
        self.assertIn(("DOC-UNSOURCED", loc), codes("Праздник назван в указе губернатора № 555-УГ."))
        self.assertIn(("DOC-UNSOURCED", loc), codes("День области установлен указом Президента."))
        frag = {"fragment_id": "frag_test_decree", "source_id": "src_test", "verification_status": "verified",
                "events": ["sverdlovsk_oblast_day"], "regions": ["RU-SVE"],
                "quote": "Указом Президента установлен День Свердловской области."}
        with_decree = dataclasses.replace(catalog(), fragments={**catalog().fragments, frag["fragment_id"]: frag})
        self.assertNotIn(("DOC-UNSOURCED", loc), codes("День области установлен указом Президента.", with_decree))

    def test_run_1115_decree_from_source_title(self):
        """Прогон 15.11 (День Свердловской области, 9 класс): фраза верна, ложного предупреждения нет."""
        n, v = setup("ex1_knowledge_day")
        n = copy.copy(n)
        n.event_id = "sverdlovsk_oblast_day"
        v["timeline"][1]["teacher_script"] = "Согласно указу губернатора, этот праздник отмечается ежегодно 17 января."
        codes = {(i.code, i.location) for i in validate_variant(v, n, catalog(), settings().generation())}
        self.assertNotIn("DOC-UNSOURCED", {code for code, _ in codes})


class SourceRefsReplayTest(unittest.TestCase):
    def test_pipeline_moves_refs(self):
        """Записанный прогон о Дне Свердловской области, в ответ материалов вставлена карточка из прогона 14.11:
        текст чистый, факт и его источник в варианте, повторного вызова материалов нет."""

        class WithRefs(ReplayLLM):
            def generate(self, **kwargs):
                response = super().generate(**kwargs)
                if kwargs["task_name"] != "materials":
                    return response
                data = extract_json(response.text)
                data["materials"][0]["content"] = Q08_CARD
                data["fact_claims"] = []
                return dataclasses.replace(response, text=json.dumps(data, ensure_ascii=False))

        directory = ROOT / "tests" / "fixtures" / "replay_gigachat_content_sverdlovsk_v2"
        client = WithRefs(directory)
        outcome = Generator(settings(), catalog(), client).run(json.loads((directory / "request.json").read_text(encoding="utf-8")))
        variant = outcome.project["variants"][0]
        self.assertEqual(client.calls.count("materials"), 1)
        card = variant["materials"][0]
        self.assertNotIn("src_", card["content"])
        self.assertIn("src_sverdlovsk_oblast_day_regional_02", {s["source_id"] for s in variant["sources"]})
        codes = {(i["code"], i["location"]) for i in variant["quality_report"]["issues"]}
        self.assertNotIn(("TECH-ID-IN-TEXT", f"materials.{card['material_id']}"), codes)
        self.assertNotIn(("DOC-UNSOURCED", f"materials.{card['material_id']}"), codes)


if __name__ == "__main__":
    unittest.main()