"""Форма строки Подвеса, рождающаяся при чтении Excel.

Строка Подвеса собирается один раз — в ``ExcelService._process_dataframe`` — и
уже в этой форме идёт в дашборд, в правила матчинга (``app.services.matching``)
и в метаданные подвеса OPC UA. Ключи формы совпадают с ключами ответа API
(``kpz_number``, ``lamels_qty``): их читают фронтенд и websocket, поэтому
переименование в доменные имена — отдельное решение, а не побочный эффект.

Пустая ячейка — сентинел ``EMPTY``, а не ``None``: книга учёта и правила
матчинга (``matching._EMPTY_TIME_TOKENS``) уже говорят на языке «—».
"""
from dataclasses import dataclass
from typing import List, Union

from app.schemas.dashboard import HangerData
from app.schemas.profile import ProfileInfo

# Значение пустой ячейки в форме строки Подвеса и в ответе API.
EMPTY = "—"


@dataclass(frozen=True)
class HangerRow:
    """Одна строка Подвеса в форме producer'а (``excel_service``)."""

    number: Union[int, str]
    date: str
    time: str
    client: str
    profile: str
    color: str
    lamels_qty: Union[int, str]
    kpz_number: str
    material_type: str
    is_defect: bool


def to_hanger_data(row: HangerRow, profiles_info: List[ProfileInfo]) -> HangerData:
    """Строка Подвеса → строка ответа дашборда (единственный маппинг)."""
    return HangerData(
        number=str(row.number),
        date=str(row.date),
        time=str(row.time),
        client=str(row.client),
        profile=str(row.profile),
        profiles_info=profiles_info,
        color=str(row.color),
        lamels_qty=row.lamels_qty,
        kpz_number=str(row.kpz_number),
        material_type=str(row.material_type),
        is_defect=row.is_defect,
    )
