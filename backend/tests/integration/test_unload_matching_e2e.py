"""
E2E тест: Матчинг OPC UA unload-событий с данными Excel.

Тестирует полный цикл:
1. Создаём тестовый Excel файл (лист "Подвесы")
2. Подставляем его активной книгой на один прогон
3. Симулируем проход подвеса по линии через значения узлов OPC UA
4. Вызываем GET /api/dashboard/opcua-unload-matched
5. Проверяем результат матчинга

Состояние сервисов подставляется публичными методами (фикстура
``clean_line`` и ``use_file``): тест не записывает приватные поля и ничего
не снимает/восстанавливает в ``finally``.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Вспомогательная функция для создания тестового Excel
# ---------------------------------------------------------------------------


def create_test_excel(filepath: str, rows: list[dict]) -> None:
    """
    Создаёт .xlsx файл с листом «Подвесы» и заполненными данными.

    Первые 2 строки — заголовки (skiprows=[0,1] при чтении pandas).
    Строка 3 — заголовок таблицы (будет прочитана как header).
    Данные начинаются со строки 4 (openpyxl row=4).

    Столбцы (1-indexed):
        D(4)=date, E(5)=number, F(6)=time,
        H(8)=material_type, I(9)=defect,
        K(11)=kpz_number, L(12)=client,
        M(13)=profile, Q(17)=color, T(20)=lamels_qty
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Подвесы"

    # Строки 1-2 — заголовки
    ws.cell(row=1, column=1, value="Заголовок")
    ws.cell(row=2, column=1, value="Подзаголовок")

    # Строка 3 — заголовок таблицы
    ws.cell(row=3, column=4, value="Дата")
    ws.cell(row=3, column=5, value="Номер")
    ws.cell(row=3, column=6, value="Время")

    for i, row_data in enumerate(rows, start=4):
        ws.cell(row=i, column=4, value=row_data.get("date"))  # D
        ws.cell(row=i, column=5, value=row_data.get("number"))  # E
        ws.cell(row=i, column=6, value=row_data.get("time"))  # F
        ws.cell(row=i, column=8, value=row_data.get("material_type", ""))  # H
        ws.cell(row=i, column=9, value=row_data.get("defect", ""))  # I
        ws.cell(row=i, column=11, value=row_data.get("kpz_number", ""))  # K
        ws.cell(row=i, column=12, value=row_data.get("client", ""))  # L
        ws.cell(row=i, column=13, value=row_data.get("profile", ""))  # M
        ws.cell(row=i, column=17, value=row_data.get("color", ""))  # Q
        ws.cell(row=i, column=20, value=row_data.get("lamels_qty", 0))  # T

    wb.save(filepath)


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _setup_excel(filepath: Path) -> None:
    """Сделать тестовый файл активной книгой на один прогон.

    Выбор не запоминается в ``static/active_excel.json``: иначе книга,
    которой уже нет после теста, переключила бы рабочий стенд.
    """
    from app.services.excel_service import excel_service

    excel_service.use_file(str(filepath))


def _clean_state() -> None:
    """Пустая линия и пустой кэш PLC, книга — из настроек."""
    from app.services.excel_service import excel_service
    from app.services.line_monitor import line_monitor
    from app.services.opcua_service import opcua_service

    line_monitor.clear_data()
    opcua_service.clear_cache()
    excel_service.use_file(None)


@pytest.fixture
def clean_line():
    """Подставить пустое состояние линии одним вызовом, до и после теста."""
    _clean_state()
    yield
    _clean_state()


async def trigger_unload(hanger_id: int) -> None:
    """Имитирует полноценный проход подвеса по линии и его выгрузку.

    Выгрузка привязывается к физическому проходу, поэтому подвес должен
    сначала появиться в линии — иначе line_monitor честно сообщает
    ``unload_without_open_cycle``. Поэтому шаг прохода по ваннам 3→4→34
    обязателен: именно он открывает цикл, из которого потом выбирается
    строка книги.
    """
    from app.services.line_monitor import line_monitor
    from app.services.opcua_service import opcua_service

    def occupy(bath: int, pallete: int) -> None:
        opcua_service.set_value(f"ns=4;s=Bath[{bath}].InUse", 1)
        opcua_service.set_value(f"ns=4;s=Bath[{bath}].Pallete", pallete)

    def clear(bath: int) -> None:
        opcua_service.set_value(f"ns=4;s=Bath[{bath}].InUse", 0)
        opcua_service.set_value(f"ns=4;s=Bath[{bath}].Pallete", 0)

    with patch("app.services.line_monitor.websocket_manager") as mock_ws:
        mock_ws.broadcast = AsyncMock(return_value=0)
        mock_ws.connection_count = 0

        # Инициализация: контрольная ванна пуста
        opcua_service.set_value("ns=4;s=Bath[34].Pallete", 0)
        await line_monitor._check_unload()

        # Проход: подвес идёт 3 → 4 и доходит до контрольной ванны
        for bath in (3, 4):
            occupy(bath, hanger_id)
            await line_monitor._scan_baths()
            clear(bath)
        occupy(34, hanger_id)
        await line_monitor._scan_baths()

        # Сход с линии: датчик 0 → N
        clear(34)
        opcua_service.set_value("ns=4;s=Bath[34].Pallete", hanger_id)
        await line_monitor._check_unload()


async def call_matched_api(limit: int = 10) -> list[dict]:
    """GET /api/dashboard/opcua-unload-matched с мок-ом catalog_service."""
    from app.main import app

    with patch("app.api.routes.dashboard.catalog_service") as mock_catalog:
        mock_catalog.get_profiles_photos_batch = AsyncMock(return_value={})

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/dashboard/opcua-unload-matched",
                params={"limit": limit},
            )
            assert resp.status_code == 200, f"API вернул {resp.status_code}: {resp.text}"
            return resp.json()


# ===========================================================================
# ТЕСТЫ
# ===========================================================================


async def test_correct_match_same_day(tmp_path: Path, clean_line):
    """
    Подвес 42 с данными в Excel (дата=сегодня, 2 часа назад).
    После выгрузки API должен вернуть event с правильными полями.
    """
    now = datetime.now()
    entry_time = now - timedelta(hours=2)

    filepath = tmp_path / "test_same_day.xlsx"
    create_test_excel(
        str(filepath),
        [
            {
                "date": datetime(entry_time.year, entry_time.month, entry_time.day),
                "number": 42,
                "time": datetime(
                    entry_time.year,
                    entry_time.month,
                    entry_time.day,
                    entry_time.hour,
                    entry_time.minute,
                    0,
                ),
                "material_type": "Пороги",
                "kpz_number": "101",
                "client": "ТестКТМ",
                "profile": "4040",
                "color": "серебро",
                "lamels_qty": 29,
            }
        ],
    )

    _setup_excel(filepath)
    await trigger_unload(42)
    data = await call_matched_api()

    assert len(data) == 1, f"Ожидался 1 event, получили {len(data)}"
    event = data[0]

    assert event["hanger"] == 42
    assert event["client"] == "ТестКТМ"
    assert event["profile"] == "4040"
    assert event["color"] == "серебро"
    assert event["lamels_qty"] == 29
    assert event["kpz_number"] == "101"
    assert event["material_type"] == "Пороги"

    # entry_time должен содержать корректное время (HH:MM)
    assert event["entry_time"] is not None
    assert ":" in event["entry_time"]


async def test_correct_match_cross_day(tmp_path: Path, clean_line):
    """
    Подвес 15 загружен вчера в 22:00.
    Выгрузка сегодня → API должен смотчить через переход дня.
    """
    yesterday = datetime.now() - timedelta(days=1)

    filepath = tmp_path / "test_cross_day.xlsx"
    create_test_excel(
        str(filepath),
        [
            {
                "date": datetime(yesterday.year, yesterday.month, yesterday.day),
                "number": 15,
                "time": datetime(yesterday.year, yesterday.month, yesterday.day, 22, 0, 0),
                "material_type": "Профиль",
                "kpz_number": "202",
                "client": "РП",
                "profile": "ЮП-1401",
                "color": "белый",
                "lamels_qty": 15,
            }
        ],
    )

    _setup_excel(filepath)
    await trigger_unload(15)
    data = await call_matched_api()

    assert len(data) == 1, f"Ожидался 1 event, получили {len(data)}"
    event = data[0]

    assert event["hanger"] == 15
    assert event["client"] == "РП"
    assert event["profile"] == "ЮП-1401"
    # entry_date должен быть вчерашним
    assert event["entry_date"] is not None


async def test_no_match_different_hanger(tmp_path: Path, clean_line):
    """
    Excel содержит только подвес 42.
    Триггерим выгрузку подвеса 99 — матч не найден.
    """
    now = datetime.now()
    entry_time = now - timedelta(hours=1)

    filepath = tmp_path / "test_no_match.xlsx"
    create_test_excel(
        str(filepath),
        [
            {
                "date": datetime(entry_time.year, entry_time.month, entry_time.day),
                "number": 42,
                "time": datetime(
                    entry_time.year,
                    entry_time.month,
                    entry_time.day,
                    entry_time.hour,
                    entry_time.minute,
                    0,
                ),
                "material_type": "Пороги",
                "kpz_number": "101",
                "client": "ТестКТМ",
                "profile": "4040",
                "color": "серебро",
                "lamels_qty": 29,
            }
        ],
    )

    _setup_excel(filepath)
    await trigger_unload(99)
    data = await call_matched_api()

    assert len(data) == 1, f"Ожидался 1 event, получили {len(data)}"
    event = data[0]

    assert event["hanger"] == 99
    assert event["client"] == "—"
    assert event["profile"] == "—"


async def test_closest_match_wins(tmp_path: Path, clean_line):
    """
    Две записи для подвеса 42: 5 часов назад («Старый») и 1 час назад («Новый»).
    Матчинг должен выбрать ближайшую по времени → «Новый».
    """
    now = datetime.now()
    old_time = now - timedelta(hours=5)
    new_time = now - timedelta(hours=1)

    filepath = tmp_path / "test_closest.xlsx"
    create_test_excel(
        str(filepath),
        [
            {
                "date": datetime(old_time.year, old_time.month, old_time.day),
                "number": 42,
                "time": datetime(
                    old_time.year,
                    old_time.month,
                    old_time.day,
                    old_time.hour,
                    old_time.minute,
                    0,
                ),
                "material_type": "Пороги",
                "kpz_number": "100",
                "client": "Старый",
                "profile": "1010",
                "color": "чёрный",
                "lamels_qty": 10,
            },
            {
                "date": datetime(new_time.year, new_time.month, new_time.day),
                "number": 42,
                "time": datetime(
                    new_time.year,
                    new_time.month,
                    new_time.day,
                    new_time.hour,
                    new_time.minute,
                    0,
                ),
                "material_type": "Пороги",
                "kpz_number": "200",
                "client": "Новый",
                "profile": "2020",
                "color": "золото",
                "lamels_qty": 20,
            },
        ],
    )

    _setup_excel(filepath)
    await trigger_unload(42)
    data = await call_matched_api()

    assert len(data) == 1, f"Ожидался 1 event, получили {len(data)}"
    event = data[0]

    assert event["hanger"] == 42
    assert event["client"] == "Новый", f"Ожидали клиента 'Новый' (ближайший), получили '{event['client']}'"
    assert event["profile"] == "2020"
