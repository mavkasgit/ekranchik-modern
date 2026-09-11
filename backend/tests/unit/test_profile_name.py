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
