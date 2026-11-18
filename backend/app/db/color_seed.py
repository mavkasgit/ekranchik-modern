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
- ``hex`` веера — справочные значения по фото веера ClassicELOX; точный
  оттенок зависит от сплава и освещения, колориметрическая точность вне рамок.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Десять текущих названий: их уже знает панель и книга учёта. Старые операции
# KTM остаются без отображаемого кода, поэтому code=None.
_CURRENT_COLORS: tuple[dict[str, str | None], ...] = (
    {"code": None, "name": "серебро", "hex": "#C0C0C0", "operation_code": "ANOD_01"},
    {"code": None, "name": "черный", "hex": "#1C1C1C", "operation_code": "ANOD_05"},
    {"code": None, "name": "золото", "hex": "#FFD700", "operation_code": "ANOD_02"},
    {"code": None, "name": "шампань", "hex": "#F7E7CE", "operation_code": "ANOD_06"},
    {"code": None, "name": "титан", "hex": "#878681", "operation_code": "ANOD_08"},
    {"code": None, "name": "бронза", "hex": "#8B5A2B", "operation_code": "ANOD_03"},
    {"code": None, "name": "медь", "hex": "#CD5C5C", "operation_code": "ANOD_07"},
    {"code": "RST", "name": "растрав", "hex": "#D3D3D3", "operation_code": None},
    {"code": "RG", "name": "Rose Gold", "hex": "#B76E79", "operation_code": None},
    {"code": "RB", "name": "Rose Bronze", "hex": "#800020", "operation_code": None},
)

# Двенадцать цветов веера ClassicELOX: кодов в KTM ещё нет, операция заводится
# сразу с прямым кодом C0…C54 (T-378).
_FAN_COLORS: tuple[dict[str, str | None], ...] = (
    {"code": "C0", "name": "Серебро", "hex": "#C9CCCE", "operation_code": "C0"},
    {"code": "C35", "name": "Чёрный", "hex": "#2A2A2A", "operation_code": "C35"},
    {"code": "S120-0", "name": "Золото", "hex": "#D4AF37", "operation_code": "S120-0"},
    {"code": "S120-2", "name": "Старое золото", "hex": "#B08D57", "operation_code": "S120-2"},
    {"code": "C31", "name": "Светлая шампань", "hex": "#E9D9BC", "operation_code": "C31"},
    {"code": "C32", "name": "Тёмная шампань", "hex": "#C8B184", "operation_code": "C32"},
    {"code": "C33", "name": "Светлая бронза", "hex": "#B0895C", "operation_code": "C33"},
    {"code": "C34", "name": "Тёмная бронза", "hex": "#7B5A38", "operation_code": "C34"},
    {"code": "C41", "name": "Медь", "hex": "#B87333", "operation_code": "C41"},
    {"code": "C44", "name": "Тёмная медь", "hex": "#8C5230", "operation_code": "C44"},
    {"code": "C51", "name": "Нержавеющая сталь", "hex": "#A8A9AD", "operation_code": "C51"},
    {"code": "C54", "name": "Тёмный титан", "hex": "#5C5D60", "operation_code": "C54"},
)

SEED_COLORS: tuple[dict[str, str | None], ...] = _CURRENT_COLORS + _FAN_COLORS

_INSERT_MISSING = text(
    """
    INSERT INTO colors (code, name, hex, operation_code, source)
    SELECT :code, :name, :hex, :operation_code, 'local'
    WHERE NOT EXISTS (SELECT 1 FROM colors WHERE name = :name)
    """
)


def seed_missing_colors(connection: Connection) -> int:
    """Дописать отсутствующие цвета засева и вернуть число вставленных строк.

    Проверка по названию делает засев идемпотентным: повторный запуск после
    сбоя миграции не плодит дубли. Переименованные локально строки не
    восстанавливаются — это уже данные администратора, а не засев.
    """
    inserted = 0
    for color in SEED_COLORS:
        result = connection.execute(_INSERT_MISSING, color)
        inserted += result.rowcount or 0
    return inserted
