"""Засев справочника цветов (спека 0003, тикет 0022).

Справочник — локальная копия операций анодирования KTM. На пустой базе его
наполняет миграция ``003``; здесь лежит сам список, чтобы засев можно было
проверить отдельно от alembic и повторный запуск не создавал дублей.

Ключи:

- ``operation_code`` — ключ синка. У старых операций ``ANOD_01…08`` он есть, а
  отображаемого ``code`` нет: код в книге учёта появился только у веера.
- ``code`` веера равен коду операции KTM, поэтому первый синк найдёт строку,
  а не создаст вторую.
- ``source=local`` у всех: до первого синка строки живут только в Экранчике.
- ``abbreviation`` — привычная подпись в ячейке. Правило «код или первые
  буквы» ломает старые ``брз``/``рст``, поэтому подпись хранится рядом с
  названием, а не выводится из него.
- ``hex`` веера — справочные значения по фото веера ClassicELOX; точный
  оттенок зависит от сплава и освещения, колориметрическая точность вне рамок.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Десять текущих названий: их уже знает панель и книга учёта. Старые операции
# KTM остаются без отображаемого кода, поэтому code=None.
_CURRENT_COLORS: tuple[dict[str, str | None], ...] = (
    {"code": None, "name": "серебро", "hex": "#E7EBEE", "abbreviation": "сер", "operation_code": "ANOD_01"},
    {"code": None, "name": "черный", "hex": "#1C1C1C", "abbreviation": "чер", "operation_code": "ANOD_05"},
    {"code": None, "name": "золото", "hex": "#FFD700", "abbreviation": "зол", "operation_code": "ANOD_02"},
    {"code": None, "name": "шампань", "hex": "#AEA895", "abbreviation": "шам", "operation_code": "ANOD_06"},
    {"code": None, "name": "титан", "hex": "#878681", "abbreviation": "тит", "operation_code": "ANOD_08"},
    {"code": None, "name": "бронза", "hex": "#8B5A2B", "abbreviation": "брз", "operation_code": "ANOD_03"},
    {"code": None, "name": "медь", "hex": "#AE5128", "abbreviation": "мед", "operation_code": "ANOD_07"},
    {"code": "RST", "name": "растрав", "hex": "#B8B8B8", "abbreviation": "рст", "operation_code": "RST"},
    {"code": "RG", "name": "Rose Gold", "hex": "#B76E79", "abbreviation": "RG", "operation_code": None},
    {"code": "RB", "name": "Rose Bronze", "hex": "#800020", "abbreviation": "RB", "operation_code": None},
)

# Двенадцать цветов веера ClassicELOX: кодов в KTM ещё нет, операция заводится
# сразу с прямым кодом C0…C54 (T-378).
_FAN_COLORS: tuple[dict[str, str | None], ...] = (
    {"code": "C0", "name": "Серебро", "hex": "#E7EBEE", "abbreviation": "C0", "operation_code": "C0"},
    {"code": "C35", "name": "Чёрный", "hex": "#1C1C1C", "abbreviation": "C35", "operation_code": "C35"},
    {"code": "S120-0", "name": "Золото", "hex": "#FFD700", "abbreviation": "S120-0", "operation_code": "S120-0"},
    {"code": "S120-2", "name": "Старое золото", "hex": "#D7C04B", "abbreviation": "S120-2", "operation_code": "S120-2"},
    {"code": "C31", "name": "Светлая шампань", "hex": "#DCD6BC", "abbreviation": "C31", "operation_code": "C31"},
    {"code": "C32", "name": "Тёмная шампань", "hex": "#AEA895", "abbreviation": "C32", "operation_code": "C32"},
    {"code": "C33", "name": "Светлая бронза", "hex": "#8F6F4A", "abbreviation": "C33", "operation_code": "C33"},
    {"code": "C34", "name": "Тёмная бронза", "hex": "#8B5A2B", "abbreviation": "C34", "operation_code": "C34"},
    {"code": "C41", "name": "Медь", "hex": "#7F1D1D", "abbreviation": "C41", "operation_code": "C41"},
    {"code": "C44", "name": "Тёмная медь", "hex": "#6E1616", "abbreviation": "C44", "operation_code": "C44"},
    {"code": "C51", "name": "Нержавеющая сталь", "hex": "#A3B3C4", "abbreviation": "C51", "operation_code": "C51"},
    {"code": "C54", "name": "Тёмный титан", "hex": "#766D6D", "abbreviation": "C54", "operation_code": "C54"},
)

# Метка засева — заведомо старая: правка в KTM новее, поэтому первый синк
# перекрывает локальную строку, а не проигрывает ей. Ручная правка (PATCH)
# ставит текущее UTC-время и снова выигрывает у KTM по правилу «новее — правильнее».
SEED_UPDATED_AT = "2000-01-01 00:00:00.000000"

SEED_COLORS: tuple[dict[str, str | None], ...] = _CURRENT_COLORS + _FAN_COLORS

_INSERT_MISSING = text(
    """
    INSERT INTO colors (code, name, hex, operation_code, source, updated_at)
    SELECT :code, :name, :hex, :operation_code, 'local', :updated_at
    WHERE NOT EXISTS (
      SELECT 1 FROM colors
      WHERE (:operation_code IS NOT NULL AND operation_code = :operation_code)
         OR (:operation_code IS NULL AND :code IS NOT NULL AND code = :code)
    )
    """
)


def seed_missing_colors(connection: Connection) -> int:
    """Дописать отсутствующие цвета засева и вернуть число вставленных строк.

    Проверка идёт по ключу синка (``operation_code``, у локальных строк —
    ``code``), а не по названию: переименованная администратором строка не
    должна вставиться второй раз и упасть на уникальном ключе. Повторный
    запуск после сбоя миграции не плодит дубли.
    """
    inserted = 0
    for color in SEED_COLORS:
        result = connection.execute(_INSERT_MISSING, {**color, "updated_at": SEED_UPDATED_AT})
        inserted += result.rowcount or 0
    return inserted


_UPDATE_ABBREVIATION = text(
    """
    UPDATE colors SET abbreviation = :abbreviation
    WHERE abbreviation IS NULL
      AND (
        (:operation_code IS NOT NULL AND operation_code = :operation_code)
        OR (:operation_code IS NULL AND :code IS NOT NULL AND code = :code)
      )
    """
)


def fill_seed_abbreviations(connection: Connection) -> int:
    """Проставить привычные подписи строкам засева, у которых их ещё нет.

    Миграция ``003`` создала таблицу без ``abbreviation``; колонку добавляет
    ``004`` и этой функцией заполняет уже засеянные строки. Сопоставление идёт
    по ключу синка, а не по названию: строку могли переименовать локально.
    Уже заполненную подпись не трогаем — её мог поправить администратор.
    """
    updated = 0
    for color in SEED_COLORS:
        result = connection.execute(_UPDATE_ABBREVIATION, color)
        updated += result.rowcount or 0
    return updated


# Строка не тронута с момента засева, если её updated_at всё ещё равен
# created_at: PATCH и синк двигают только updated_at. Это и есть граница
# «администратор ещё не правил» — чужие правки миграция не перезаписывает.
_RESET_UNTOUCHED_SEED = text(
    """
    UPDATE colors SET hex = :hex, updated_at = :updated_at
    WHERE source = 'local'
      AND updated_at = created_at
      AND (
        (:operation_code IS NOT NULL AND operation_code = :operation_code)
        OR (:operation_code IS NULL AND :code IS NOT NULL AND code = :code)
      )
    """
)


def reset_untouched_seed_colors(connection: Connection) -> int:
    """Вернуть нетронутым строкам засева актуальный hex и старую метку времени.

    Миграция ``003`` успела засеять базы со старыми значениями и
    ``CURRENT_TIMESTAMP``: без этой правки засев всегда был бы новее KTM и
    первый синк не перекрывал бы его. Правленые строки (``updated_at`` уже
    отличается от ``created_at``) и строки из KTM не трогаются.
    """
    updated = 0
    for color in SEED_COLORS:
        result = connection.execute(_RESET_UNTOUCHED_SEED, {**color, "updated_at": SEED_UPDATED_AT})
        updated += result.rowcount or 0
    return updated
