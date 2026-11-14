"""Ссылки на источники в тексте для педагога и учеников: убрать из текста, факт зарегистрировать.

Модель иногда пишет ссылку на источник прямо в тексте материала, а `fact_claims` оставляет пустым
(прогон 14.11, День Свердловской области, карточка для учеников):

    2. 17 января 1934 года Уральская область была разделена на три области...
    (fact_claims: src_sverdlovsk_oblast_day_regional_02/frag_sverdlov_002)

Ученик такую строку видеть не должен, а факт при этом настоящий и проверенный. `move_source_refs`
вырезает ссылку из текста. Если она ведёт на проверенный фрагмент события, фраза перед ссылкой
записывается в `fact_claims` с этим источником: тогда источник попадает в список источников сценария,
а проверка `FACT-UNREGISTERED` не срабатывает зря. Номер фрагмента сверяется точно; если модель
ошиблась в номере (`frag_sverdlov_002` вместо `frag_sverdlovsk_002`), берётся единственный фрагмент
этого источника. Фраза регистрируется, только если не добавляет к фрагменту своих дат, годов
и документов. Ссылка на неизвестный источник или неподтверждённая фраза просто убирается из текста:
факт остаётся незарегистрированным, и его увидят обычные проверки.
"""

from __future__ import annotations

import re
from typing import Any

# «(fact_claims: src_x/frag_y)», «(источник: src_x)», «[src_x, frag_y]», «(src_x)», «(frag_y)».
_REF = re.compile(
    r"[ \t]*[(\[]\s*(?:(?:fact_claims?|fact_claim_id|источник\w*|source(?:_id)?|см\.?)\s*[:=\-]?\s*)?"
    r"(?:(?P<src>src_[a-z0-9_]+)(?:\s*[/,;:]\s*(?:fragment_id\s*[:=]\s*)?(?P<frag>frag_[a-z0-9_]+))?"
    r"|(?P<frag_only>frag_[a-z0-9_]+))\s*[)\]]",
    re.I,
)
# Та же ссылка без скобок: «fact_claims: src_x/frag_y», «источник: src_x».
_BARE_REF = re.compile(
    r"[ \t]*(?:fact_claims?|источник\w*|source(?:_id)?)\s*[:=\-]\s*(?P<src>src_[a-z0-9_]+)"
    r"(?:\s*[/,;:]\s*(?P<frag>frag_[a-z0-9_]+))?(?P<frag_only>)",
    re.I,
)
_YEAR = re.compile(r"(?<![\d№])(1[0-9]{3}|20[0-9]{2})(?!\d)")
_DATE = re.compile(r"\b\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b", re.I)
# Ссылка на нормативный документ: слово «указ / постановление / закон / приказ / распоряжение / декрет» вместе
# с номером, датой, годом или тем, кто его издал. Просто «законы дружбы» или «по приказу капитана» - не документ.
_DOC_WORD = re.compile(r"\b(указ|постановлени|закон(?!одат)|приказ|распоряжени|декрет)\w*")
_DOC_SPECIFIC = re.compile(
    r"№\s*\d|\bномер\w*\s+\d|\bот\s+\d{1,2}\s+(?:январ|феврал|март|апрел|ма[яй]|июн|июл|август|сентябр|октябр|ноябр|декабр)"
    r"|\b\d{4}\s*(?:г\b|г\.|год)"
    r"|\b(?:губернатор|президент|правительств|министр|министерств|госдум|дум[аыуое]\b|законодательн|мэр|император|цар[ьяюе]\b)"
    r"|\bглав\w*\s+(?:област|город|администрац)"
    r"|\b(?:федеральн|областн|региональн)\w*\s+закон|\bзакон\w*\s+(?:свердловской|российской|рф\b)"
)


def document_mentions(text: str) -> list[tuple[str, str]]:
    """Ссылки на нормативные документы в тексте: пары (фраза, основа слова «указ», «закон» и т. п.).

    Текст приводится к нижнему регистру; фраза возвращается в исходном виде.
    """
    found = []
    for sentence in re.findall(r"[^.!?\n]+[.!?]?", text):
        low = sentence.lower()
        word = _DOC_WORD.search(low)
        if word and _DOC_SPECIFIC.search(low):
            found.append((sentence.strip(), word.group(1)))
    return found


def _supported(claim: str, fragment: dict[str, Any]) -> bool:
    """Фраза не добавляет к фрагменту своих дат, годов и документов: только тогда её можно записать с этим источником.

    «День образования области установлен указом губернатора…» со ссылкой на фрагмент «День образования
    Свердловской области - 17 января» не регистрируется: указа во фрагменте нет.
    """
    source = str(fragment.get("quote") or fragment.get("text") or fragment.get("text_excerpt") or "").lower()
    tokens = [m.group(0).lower() for m in list(_YEAR.finditer(claim)) + list(_DATE.finditer(claim))]
    if any(token not in source for token in tokens):
        return False
    return all(stem in source for _, stem in document_mentions(claim))


_LIST_MARK = re.compile(r"^\s*(?:[-\u2013\u2014\u2022*]|\d{1,2}[.)])\s*")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def _claim_before(text: str, start: int) -> str:
    """Фраза перед ссылкой: предыдущее предложение в той же строке или предыдущая непустая строка."""
    before = text[:start].rstrip()
    line = before.rsplit("\n", 1)[-1].strip()
    if not line:
        lines = [x for x in before.split("\n") if x.strip()]
        line = lines[-1].strip() if lines else ""
    ends = [m.end() for m in _SENTENCE_END.finditer(line[:-1])]
    sentence = line[ends[-1]:] if ends else line
    return _LIST_MARK.sub("", sentence).strip()


def _resolve(src: str | None, frag: str | None, fragments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Проверенный фрагмент, на который ведёт ссылка, или None."""
    by_id = {f["fragment_id"]: f for f in fragments}
    if frag and frag in by_id and (not src or by_id[frag].get("source_id") == src):
        return by_id[frag]
    if src:
        same_source = [f for f in fragments if f.get("source_id") == src]
        if len(same_source) == 1:
            return same_source[0]
    return None


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def move_source_refs(variant: dict[str, Any], fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Убирает ссылки на источники из текстов варианта и регистрирует подтверждённые факты (меняет вариант на месте).

    Параметры:
        variant: собранный вариант контракта 03;
        fragments: проверенные фрагменты события (`Catalog.verified_fragments`).

    Возвращает:
        Список изменений для трассы: поле, найденные ссылки, номера зарегистрированных фактов.
    """
    changes: list[dict[str, Any]] = []
    claims = variant.setdefault("fact_claims", [])
    known = {(c.get("text") or "").strip().lower() for c in claims}

    def fix(text: str, where: str, location: str) -> str:
        refs: list[str] = []
        registered: list[str] = []
        # Сначала ссылки в скобках, потом без скобок: одна ссылка не считается дважды.
        for rx in (_REF, _BARE_REF):
            matches = list(rx.finditer(text))
            for match in matches:
                src, frag = match.group("src"), match.group("frag") or match.group("frag_only") or None
                refs.append("/".join(x for x in (src, frag) if x))
                fragment = _resolve(src, frag, fragments)
                claim = _claim_before(text, match.start())
                if fragment and claim and claim.lower() not in known and _supported(claim, fragment):
                    claim_id = f"fc_{len(claims) + 1:02d}"
                    claims.append({"claim_id": claim_id, "text": claim, "location": location,
                                   "source_id": fragment["source_id"], "fragment_id": fragment["fragment_id"],
                                   "needs_teacher_check": False})
                    known.add(claim.lower())
                    registered.append(claim_id)
            if matches:
                text = rx.sub("", text)
        if not refs:
            return text
        changes.append({"field": where, "refs": refs, "registered": registered})
        return _tidy(text)

    for block in variant.get("timeline") or []:
        bid = block.get("block_id", "")
        if isinstance(block.get("teacher_script"), str):
            block["teacher_script"] = fix(block["teacher_script"], f"timeline.{bid}.teacher_script", bid)
        block["pupil_actions"] = [fix(a, f"timeline.{bid}.pupil_actions.{i}", bid) if isinstance(a, str) else a
                                  for i, a in enumerate(block.get("pupil_actions") or [])]
    for material in variant.get("materials") or []:
        mid = material.get("material_id", "")
        for key in ("content", "teacher_notes"):
            if isinstance(material.get(key), str):
                material[key] = fix(material[key], f"materials.{mid}.{key}", mid)
    variant["teacher_instructions"] = [fix(x, f"teacher_instructions.{i}", "teacher_instructions") if isinstance(x, str) else x
                                       for i, x in enumerate(variant.get("teacher_instructions") or [])]
    return changes


def register_fragment_facts(variant: dict[str, Any], fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Записывает в `fact_claims` фразы с годом или датой, которые подтверждает проверенный фрагмент события.

    Модель берёт факт из справочного фрагмента («начать год с 1 января 1700 года»), но не записывает его
    в `fact_claims`, и проверка `FACT-UNREGISTERED` срабатывает на проверенный факт (замечание QA 14.11).
    Фраза записывается, только если все её годы и даты есть в одном фрагменте и она не добавляет к нему
    документов (`_supported`). Дату самого события из карточки каталога проверка и так не считает фактом.

    Возвращает:
        Список изменений для трассы: место, фраза, фрагмент.
    """
    changes: list[dict[str, Any]] = []
    if not fragments:
        return changes
    claims = variant.setdefault("fact_claims", [])
    claimed = " ".join(str(c.get("text") or "") for c in claims).lower()
    sources = [(f, str(f.get("quote") or f.get("text") or f.get("text_excerpt") or "").lower()) for f in fragments]
    texts = [(b.get("block_id", ""), b.get("teacher_script") or "") for b in variant.get("timeline") or []]
    texts += [(m.get("material_id", ""), m.get("content") or "") for m in variant.get("materials") or []]
    for location, text in texts:
        for sentence in re.findall(r"[^.!?\n]+[.!?]?", text):
            tokens = [m.group(0).lower() for m in list(_YEAR.finditer(sentence)) + list(_DATE.finditer(sentence))]
            if not tokens or all(token in claimed for token in tokens):
                continue
            claim = _LIST_MARK.sub("", sentence).strip()
            fragment = next((f for f, source in sources if all(t in source for t in tokens) and _supported(claim, f)), None)
            if not fragment:
                continue
            claim_id = f"fc_{len(claims) + 1:02d}"
            claims.append({"claim_id": claim_id, "text": claim, "location": location, "source_id": fragment["source_id"],
                           "fragment_id": fragment["fragment_id"], "needs_teacher_check": False})
            claimed += " " + claim.lower()
            changes.append({"location": location, "claim_id": claim_id, "fragment_id": fragment["fragment_id"], "text": claim[:120]})
    return changes