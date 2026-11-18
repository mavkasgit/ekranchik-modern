"""Unit tests for profile_name: single source of «Профиль» parsing.

The module turns one book cell into ParsedProfiles (clean name + canonical
processing tokens) and is shared by both dashboard paths and photo lookup, so
these tests pin the parsing contract both consumers rely on: keyword
normalization, no de-duplication, segment folding, and empty-cell handling.
"""

import pytest

from app.services.profile_name import parse_profile, split_profiles


def test_single_segment_splits_name_and_processing():
    """«Чистое» имя и канонический токен обработки для одного сегмента."""
    parsed = parse_profile("СРП228 окно")

    assert parsed.raw == "СРП228 окно"
    assert parsed.name == "СРП228"
    assert parsed.processing == ["окно"]


def test_operator_spelling_normalizes_to_canonical_token():
    """Запись оператора «гребенка» даёт канонический токен «греб»."""
    parsed = parse_profile("ЮП-460 гребенка")

    assert parsed.name == "ЮП-460"
    assert parsed.processing == ["греб"]


def test_processing_has_no_deduplication():
    """Два совпадения («греб» и «гребенка») дают два токена, не один."""
    assert parse_profile("греб гребенка").processing == ["греб", "греб"]


def test_new_keyword_otv_is_recognized():
    """«отв» — новое ключевое слово задачи, вырезается как обработка."""
    parsed = parse_profile("УП-1 отв")

    assert parsed.name == "УП-1"
    assert parsed.processing == ["отв"]


def test_otv_does_not_fire_inside_a_longer_word():
    """Границы слова: «отвертка» не теряет «отв» (нет ложного срабатывания)."""
    parsed = parse_profile("отвертка")

    assert parsed.name == "отвертка"
    assert parsed.processing == []


def test_slash_splits_cell_into_separate_profiles():
    """«3473/2902/2016» — три Профиля без обработок, raw совпадает с name."""
    profiles = split_profiles("3473/2902/2016")

    assert [p.name for p in profiles] == ["3473", "2902", "2016"]
    assert all(p.raw == p.name for p in profiles)


def test_processing_only_segment_folds_into_previous_profile():
    """Реальная ячейка: «окно» без имени сворачивается в «ЮП-460»."""
    profiles = split_profiles("ЮП-460 гребенка+окно")

    assert len(profiles) == 1
    assert profiles[0].raw == "ЮП-460 гребенка"
    assert profiles[0].name == "ЮП-460"
    assert profiles[0].processing == ["греб", "окно"]


def test_leading_processing_segment_folds_into_next_profile():
    """Ведущая обработка без имени уходит в следующий Профиль."""
    profiles = split_profiles("окно + ЮП-460")

    assert len(profiles) == 1
    assert profiles[0].name == "ЮП-460"
    assert profiles[0].processing == ["окно"]


def test_two_real_profiles_keep_their_own_processing():
    """Две записи одного Профиля: у каждой остаётся своя обработка."""
    profiles = split_profiles("АТ-4893 окно + АТ-4893 греб")

    assert len(profiles) == 2
    assert [p.name for p in profiles] == ["АТ-4893", "АТ-4893"]
    assert profiles[0].processing == ["окно"]
    assert profiles[1].processing == ["греб"]


def test_cell_of_processing_words_only_yields_no_profile():
    """Ячейка целиком из обработок — Профиля в ней нет."""
    assert split_profiles("окно + греб") == []


@pytest.mark.parametrize("value", [None, "", "—", "nan", float("nan")])
def test_empty_inputs_yield_no_profiles(value):
    """Пустая ячейка (в т.ч. pandas NaN) не бросает и даёт пустой список."""
    assert split_profiles(value) == []


# Написания длины из книги учёта (замер 18.11.2026, последние 10 000 строк,
# плюс форматы, найденные полным пробегом). Список — данные, а не пересказ
# правила: если книга начнёт писать иначе, параметр должен вырасти вместе с ней.
LENGTH_SPELLINGS = [
    ("ЮП-1880 2.5м", "ЮП-1880", 2.5),
    ("ЮП-2083 (1.8)", "ЮП-2083", 1.8),
    ("2525 2.7м", "2525", 2.7),
    ("ЮП-1401 (3.05м)", "ЮП-1401", 3.05),
    ("Лайн 3,0м", "Лайн", 3.0),
    ("2626(2.7м)", "2626", 2.7),
    ("ЮП-2083 1.8м", "ЮП-2083", 1.8),
    ("Бинокль 3,0м", "Бинокль", 3.0),
    ("ЮП-2083 2,75 метра", "ЮП-2083", 2.75),
    ("юп-2083 2.75м", "юп-2083", 2.75),
    ("2525(2.7м)", "2525", 2.7),
    ("ЮП-3658  2.5м", "ЮП-3658", 2.5),
    ("ЮП-2083 (2.7)", "ЮП-2083", 2.7),
    ("2525   2,7м", "2525", 2.7),
    ("У5050 (3.05м)", "У5050", 3.05),
    ("1515 (2.75м)", "1515", 2.75),
    ("ПТ80(юп-1880) 2.7м", "ПТ80(юп-1880)", 2.7),
    ("У2525 (3.05м)", "У2525", 3.05),
    ("371 (2.7м)", "371", 2.7),
    ("У2020 (3.05м)", "У2020", 3.05),
    ("юп-2083 1,85м", "юп-2083", 1.85),
    ("ЮП-2083 1,8 метра", "ЮП-2083", 1.8),
    ("ЮП-3658 (2.5м)", "ЮП-3658", 2.5),
    ("1515(3,05м)", "1515", 3.05),
    ("профиль S41x39,s40x29,s5x32 3,35м", "профиль S41x39,s40x29,s5x32", 3.35),
    ("У3030(3,05)", "У3030", 3.05),
    ("371 2.7м", "371", 2.7),
    ("2525 (2.75м)", "2525", 2.75),
    ("1515(2,7м)", "1515", 2.7),
    ("389 2.7м", "389", 2.7),
    ("профиль S46х16 3м", "профиль S46х16", 3.0),
    ("2525 (3,05м)", "2525", 3.05),
    ("2525 (3.05м)", "2525", 3.05),
    ("1515 (3.05м)", "1515", 3.05),
    ("60    2.75м", "60", 2.75),
    ("ЮП-2083(1.8м)", "ЮП-2083", 1.8),
    ("Профиль RE7444 0,6м", "Профиль RE7444", 0.6),
    ("2525 (2.7м)", "2525", 2.7),
    ("профиль 94х52 (часть2) 2.11м", "профиль 94х52 (часть2)", 2.11),
    ("крышка 30 (2.11м)", "крышка 30", 2.11),
    ("2525  2.5м", "2525", 2.5),
    ("ПТ-100    2.5м", "ПТ-100", 2.5),
    ("3418   1.8м", "3418", 1.8),
    ("Профиль RE7444 3м", "Профиль RE7444", 3.0),
    ("профиль АВД4324, 3м", "профиль АВД4324", 3.0),
    ("Труба 18мм 3.0м", "Труба 18мм", 3.0),
    ("ЮП-009 (2м)", "ЮП-009", 2.0),
    ("лайн 3м", "лайн", 3.0),
    # Написания, которые нашёл полный пробег по книге (19 818 строк), а не
    # окно последних 10 000: форматы те же, артикулы другие.
    ("СРЛ10 (1.35м)", "СРЛ10", 1.35),
    ("Труба 32мм 3.0м", "Труба 32мм", 3.0),
    ("ЮП-009 (3м)", "ЮП-009", 3.0),
    ("ЮП-009 3 метра", "ЮП-009", 3.0),
    ("s24x12 длина 3.0м", "s24x12 длина", 3.0),
    ("ЮП-3019(2.75м)", "ЮП-3019", 2.75),
]


@pytest.mark.parametrize(("raw", "name", "length_m"), LENGTH_SPELLINGS)
def test_length_leaves_the_article_and_becomes_its_own_field(raw, name, length_m):
    """Длина — отдельный признак: имя чистится, метры уходят в ``length_m``."""
    parsed = parse_profile(raw)

    assert parsed.name == name
    assert parsed.length_m == pytest.approx(length_m)


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        ("ЮП-2083 2,75 метра", "2,75 м"),
        ("Лайн 3,0м", "3 м"),
        ("ЮП-1401 (3.05м)", "3,05 м"),
        ("Профиль RE7444 0,6м", "0,6 м"),
        ("юп-2083 1,85м", "1,85 м"),
    ],
)
def test_length_text_is_the_display_form(raw, text):
    """Показ: запятая, без лишних нулей, пробел перед «м»."""
    assert parse_profile(raw).length_text == text


@pytest.mark.parametrize(
    "raw",
    [
        "Кр.труба 10мм",
        "труба 45мм",
        "1500х3000х2.0",
        "0.8x1000x600",
        "ЮП-2900 (381)",
        "ЮП-2464-1",
        # Марка материала: «5М»/«2М» — не метры, а буква перед числом —
        # не начало длины (найдено пробегом по всей книге).
        "Лист ПВС 1 А5М",
        "Лист ПВС 1 АМг2М",
        "Лист ПВС 1.2 АМГ2М",
    ],
)
def test_non_length_numbers_stay_in_the_article(raw):
    """Миллиметры, размеры листов и скобка-номер длиной не считаются."""
    parsed = parse_profile(raw)

    assert parsed.name == raw
    assert parsed.length_m is None
    assert parsed.length_text is None


def test_processing_and_length_are_removed_together():
    """Обработка и длина в одной ячейке: обе уходят, имя — артикул."""
    parsed = parse_profile("ЮП-460 гребенка 3м")

    assert parsed.name == "ЮП-460"
    assert parsed.processing == ["греб"]
    assert parsed.length_m == pytest.approx(3.0)
    assert parsed.length_text == "3 м"


def test_length_belongs_to_its_own_profile_after_split():
    """Разбиение по «+» идёт до разбора: длина не переезжает на соседа."""
    profiles = split_profiles("ЮП-2083(1.8м)+ ЮП-4863")

    assert [p.name for p in profiles] == ["ЮП-2083", "ЮП-4863"]
    assert profiles[0].length_m == pytest.approx(1.8)
    assert profiles[0].length_text == "1,8 м"
    assert profiles[1].length_m is None
    assert profiles[1].length_text is None


def test_removing_processing_leaves_no_empty_parentheses():
    """Скобка из одного слова-обработки не оставляет «()» в артикуле."""
    parsed = parse_profile("Профиль алюминевый 314(Гребенка)")

    assert parsed.name == "Профиль алюминевый 314"
    assert parsed.processing == ["греб"]
