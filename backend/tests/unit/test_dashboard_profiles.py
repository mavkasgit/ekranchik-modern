"""Строка дашборда: длина из книги доходит до ответа отдельным полем.

Контракт один на обе таблицы: очередь загрузки (``GET /api/dashboard``) и
выгрузку (``GET /api/dashboard/opcua-unload-matched``) собирает
``_build_profiles_info``, поэтому проверяется и маппинг, и HTTP-путь очереди.
Каталожная длина (``profiles.length``, мм) не подставляется: бейдж показывает
только то, что написано в книге (ADR 0012).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.hanger_row import HangerRow


def test_profiles_info_carries_book_length():
    """Длина из ячейки уходит в поля бейджа, имя остаётся как записано."""
    from app.api.routes.dashboard import _build_profiles_info

    info = _build_profiles_info("ЮП-2083 2,75 метра", {})

    assert len(info) == 1
    assert info[0].name == "ЮП-2083 2,75 метра"
    assert info[0].canonical_name == "ЮП-2083"
    assert info[0].length_m == pytest.approx(2.75)
    assert info[0].length_text == "2,75 м"


def test_profiles_info_keeps_length_per_profile_and_none_without_length():
    """У каждого профиля свой бейдж; без длины поля пустые, а не выдуманные."""
    from app.api.routes.dashboard import _build_profiles_info

    info = _build_profiles_info("ЮП-2083(1.8м)+ ЮП-4863", {})

    assert [item.length_text for item in info] == ["1,8 м", None]
    assert [item.length_m for item in info] == [pytest.approx(1.8), None]


def test_unload_event_schema_serializes_length():
    """Выгрузка использует тот же ``ProfileInfo``: поля длины видны в JSON."""
    from app.api.routes.dashboard import _build_profiles_info
    from app.schemas.dashboard import MatchedUnloadEvent

    event = MatchedUnloadEvent(
        exit_date="18.11.2026",
        exit_time="10:00",
        hanger=5,
        profiles_info=_build_profiles_info("ЮП-2083 2,75 метра", {}),
    )

    profile = event.model_dump()["profiles_info"][0]
    assert profile["length_m"] == pytest.approx(2.75)
    assert profile["length_text"] == "2,75 м"


async def test_dashboard_endpoint_returns_length(monkeypatch):
    """GET /api/dashboard собирает строку тем же маппингом, что и всё остальное."""
    from app.api.routes import dashboard as dashboard_route
    from app.main import app
    from app.services.excel_service import excel_service

    row = HangerRow(
        number=5,
        date="18.11.26",
        time="—",
        client="Клиент",
        profile="ЮП-2083 2,75 метра",
        color="чёрный",
        lamels_qty=10,
        kpz_number="101",
        material_type="Профиль",
        sheet_row=4,
        is_defect=False,
    )
    monkeypatch.setattr(excel_service, "get_products", lambda **kwargs: [row])

    async def no_photos(names, session=None):
        return {}

    monkeypatch.setattr(dashboard_route.catalog_service, "get_profiles_photos_batch", no_photos)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/dashboard")

    assert response.status_code == 200, response.text
    profile = response.json()["products"][0]["profiles_info"][0]
    assert profile["name"] == "ЮП-2083 2,75 метра"
    assert profile["canonical_name"] == "ЮП-2083"
    assert profile["length_m"] == pytest.approx(2.75)
    assert profile["length_text"] == "2,75 м"
