"""Разрешение пути книги: существующий путь важнее каталога активной книги.

Регрессия: тест записал в ``static/active_excel.json`` путь из pytest-времянки.
Каталог книги стал временным, и дальше реальный UNC-путь оператора мапился
внутрь него — стенд читал несуществующую книгу, хотя путь был верный.
"""

from pathlib import Path


def test_real_path_wins_over_a_stale_book_folder(tmp_path, monkeypatch):
    from app.api.routes import dashboard as routes

    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "Учет КПЗ 2026.xlsm").write_bytes(b"stale")

    monkeypatch.setattr(type(routes.excel_service), "directory", property(lambda self: stale))

    real_exists = routes.path_exists
    unc = "\\\\172.17.11.7\\Оператор\\Учет КПЗ 2026.xlsm"
    monkeypatch.setattr(
        routes,
        "path_exists",
        lambda path: True if str(path).startswith("\\\\172.17.11.7") else real_exists(path),
    )

    resolved, entered = routes._resolve_book_input(unc)

    assert str(resolved).startswith("\\\\172.17.11.7"), resolved
    assert str(resolved) != str(stale / "Учет КПЗ 2026.xlsm")
    assert entered is None, "путь открылся как есть — показывать его же и нужно"


def test_missing_operator_path_is_looked_up_inside_the_book_folder(tmp_path, monkeypatch):
    """Контейнер: путь оператора не разрешается, хвост ищется в каталоге книги."""
    from app.api.routes import dashboard as routes

    mount = tmp_path / "excel"
    mount.mkdir()
    # \\ktm-disk\Оператор — сама шара, поэтому хвост — только имя книги.
    mapped = mount / "Учет КПЗ 2026.xlsm"
    mapped.write_bytes(b"book")

    monkeypatch.setattr(type(routes.excel_service), "directory", property(lambda self: mount))
    monkeypatch.setattr(
        routes, "path_exists", lambda path: False if str(path).startswith("\\\\") else Path(path).exists()
    )

    typed = "\\\\ktm-disk\\Оператор\\Учет КПЗ 2026.xlsm"
    resolved, entered = routes._resolve_book_input(typed)

    assert resolved == mapped.resolve()
    # Книгу сервер нашёл в смонтированном каталоге: оператору показывается
    # его путь, а не ``/app/excel/…``.
    assert entered == typed
