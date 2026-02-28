"""tests/test_glossary.py — Glossary normalization tests.

Port of apps/worker/test/summary_glossary.test.ts.
"""

from __future__ import annotations

import pytest

from summary.glossary import apply_glossary


def test_normalizes_цахал_lower():
    assert apply_glossary("Силы цахал провели операцию") == "Силы ЦАХАЛ провели операцию"


def test_normalizes_цахал_already_correct():
    assert apply_glossary("ЦАХАЛ сообщил") == "ЦАХАЛ сообщил"


def test_normalizes_шабак():
    assert apply_glossary("По данным шабак") == "По данным ШАБАК"


def test_normalizes_кнесет_single_с():
    assert apply_glossary("заседание кнесета") == "заседание Кнессета"


def test_normalizes_кнессет_double_с():
    assert apply_glossary("заседание кнессета") == "заседание Кнессета"


def test_normalizes_тель_авив_space():
    assert apply_glossary("жители тель авива") == "жители Тель-Авива"


def test_normalizes_тель_авив_hyphen_lower():
    assert apply_glossary("в тель-авиве") == "в Тель-Авиве"


def test_normalizes_иерусалим():
    assert apply_glossary("премьер иерусалима") == "премьер Иерусалима"


def test_normalizes_хайфа():
    assert apply_glossary("порт хайфы") == "порт Хайфы"


def test_does_not_mutate_unrelated_text():
    text = "Правительство обсудило бюджет на 2026 год."
    assert apply_glossary(text) == text


def test_normalizes_цахал_in_sentence():
    result = apply_glossary("Представитель цАхАл заявил")
    assert "ЦАХАЛ" in result


def test_normalizes_multiple_terms_in_one_text():
    text = "цахал вошёл в тель-авив, кнесет одобрил."
    result = apply_glossary(text)
    assert "ЦАХАЛ" in result
    assert "Тель-Авив" in result
    assert "Кнессет" in result
