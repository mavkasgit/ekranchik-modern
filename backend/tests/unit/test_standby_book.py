"""Правило запасной книги учёта (тикет 0009, спека 0001, ADR 0009).

Смысл режима: книгу открыли на другом компьютере и сохранили с машины
оператора нельзя, поэтому автосохранение продолжает писать обе книги. Время
сохранения и размер файла этого не различают — различает только
наполненность: в основной строки перестают прибавляться, в запасной растут.

Решение принимает чистая функция ``decide``: здесь по одному тесту на каждую
строку таблицы правила. Время во всех тестах монотонное — календарные
переводы часов правило не касаются.

Фоновую задачу проверяют два теста ``tick``: она обязана звать
``set_active_file`` именно с тем путём, на который указало правило, и не
трогать активную книгу, когда роста нет.
"""

from pathlib import Path

import openpyxl
import pytest

from app.services.excel_service import ExcelService, excel_service
from app.services.standby_book import (
    FROZEN_SECONDS,
    BookSample,
    Role,
    StandbyBook,
    decide,
)

MAIN_PATH = Path("//host/share/Учет КПЗ 2026.xlsm")
RESERVE_PATH = Path("//host/share/Учет КПЗ 2026 запасная.xlsm")
NOW = 10_000.0


def _main(rows: int | None, *, present: bool = True) -> BookSample:
    return BookSample(path=MAIN_PATH, present=present, rows=rows)


def _reserve(rows: int | None, *, present: bool = True) -> BookSample:
    return BookSample(path=RESERVE_PATH, present=present, rows=rows)


def _decide(
    active: Role,
    main: BookSample,
    reserve: BookSample,
    *,
    main_grew: bool = False,
    main_grown_at: float | None = None,
    reserve_grown_at: float | None = None,
    now: float = NOW,
) -> Role | None:
    """Правило с явно заданными моментами роста: рост — не «сколько строк»."""
    return decide(
        active,
        main,
        reserve,
        main_grew=main_grew,
        main_grown_at=now - FROZEN_SECONDS if main_grown_at is None else main_grown_at,
        reserve_grown_at=reserve_grown_at,
        now=now,
    )


# --- Таблица правила: по тесту на строку спеки ------------------------------


def test_main_growth_keeps_reading_main():
    """Строка «основная растёт»: остаёмся на основной.

    Даже когда обе книги растут и в запасной строк больше — приоритет у
    основной (ADR 0009).
    """
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            _reserve(200),
            main_grew=True,
            main_grown_at=NOW,
            reserve_grown_at=NOW,
        )
        is None
    )


def test_main_frozen_for_less_than_half_an_hour_keeps_main():
    """Строка «основная не растёт 30 минут»: 29 минут — ещё ждём."""
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            _reserve(200),
            main_grown_at=NOW - FROZEN_SECONDS + 1,
            reserve_grown_at=NOW - 60,
        )
        is None
    )


def test_frozen_main_gives_way_to_growing_reserve():
    """Строка «основная не растёт 30 мин, запасная росла и обошла»."""
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            _reserve(120),
            main_grown_at=NOW - FROZEN_SECONDS,
            reserve_grown_at=NOW - 60,
        )
        is Role.RESERVE
    )


def test_frozen_main_with_frozen_reserve_keeps_main():
    """Строка «обе не растут»: обычное предупреждение, переключения нет."""
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            _reserve(200),
            main_grown_at=NOW - FROZEN_SECONDS,
            reserve_grown_at=NOW - FROZEN_SECONDS - 1,
        )
        is None
    )


def test_reserve_never_grown_does_not_take_over():
    """Запасная не росла при нас — она не «работающая», даже если полнее.

    Разница с предыдущей строкой принципиальная: после рестарта запасная
    может быть полнее основной, но это не повод читать её — работать в ней
    начали не сейчас.
    """
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            _reserve(200),
            main_grown_at=NOW - FROZEN_SECONDS,
            reserve_grown_at=None,
        )
        is None
    )


@pytest.mark.parametrize("reserve_rows", [100, 99], ids=["same", "fewer"])
def test_growing_reserve_that_is_not_fuller_does_not_take_over(reserve_rows):
    """Строка «запасная растёт, но строк не больше»: обойти надо строго."""
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            _reserve(reserve_rows),
            main_grown_at=NOW - FROZEN_SECONDS,
            reserve_grown_at=NOW - 60,
        )
        is None
    )


def test_reserve_reading_returns_to_main_on_its_growth():
    """Строка «читаем запасную, в основной снова выросло»: возврат сразу."""
    assert (
        _decide(
            Role.RESERVE,
            _main(101),
            _reserve(500),
            main_grew=True,
            main_grown_at=NOW,
            reserve_grown_at=NOW,
        )
        is Role.MAIN
    )


def test_reserve_reading_continues_while_main_is_quiet():
    """Строка «читаем запасную, основная молчит»: не дёргаем чтение."""
    assert (
        _decide(
            Role.RESERVE,
            _main(100),
            _reserve(500),
            main_grown_at=NOW - FROZEN_SECONDS * 10,
            reserve_grown_at=NOW - 60,
        )
        is None
    )


def test_missing_main_switches_to_reserve_at_once():
    """Строка «основная пропала»: это отказ, а не заморозка — без 30 минут."""
    assert (
        _decide(
            Role.MAIN,
            _main(None, present=False),
            _reserve(120),
            main_grown_at=NOW,
            reserve_grown_at=None,
        )
        is Role.RESERVE
    )


def test_unreadable_main_is_waited_out():
    """Строка «основная есть, но не читается (сохраняется)»: остаёмся, ждём."""
    assert (
        _decide(
            Role.MAIN,
            _main(None),
            _reserve(500),
            main_grown_at=NOW - FROZEN_SECONDS * 5,
            reserve_grown_at=NOW - 60,
        )
        is None
    )


def test_missing_reserve_while_reading_it_returns_to_main():
    """Строка «запасная пропала»: режим выключается, читается основная."""
    assert (
        _decide(
            Role.RESERVE,
            _main(100),
            _reserve(None, present=False),
            reserve_grown_at=None,
        )
        is Role.MAIN
    )


def test_no_reserve_keeps_mode_off():
    """Строка «запасная не задана»: только основная, переключать некуда."""
    assert (
        _decide(
            Role.MAIN,
            _main(100),
            BookSample(path=None, present=False, rows=None),
            main_grown_at=NOW - FROZEN_SECONDS * 5,
        )
        is None
    )


def test_missing_main_and_unreadable_reserve_stays_put():
    """Уходить некуда: обе книги недоступны — остаёмся и ждём следующего опроса."""
    assert (
        _decide(
            Role.MAIN,
            _main(None, present=False),
            _reserve(None),
            reserve_grown_at=None,
        )
        is None
    )


# --- Фоновая задача: замер, решение, переключение ---------------------------


@pytest.fixture
def books(tmp_path, monkeypatch):
    """Две книги на диске и подменённые ответы сервиса о них.

    Читать настоящую шару тест не имеет права: ``count_book_rows`` — разбор
    Excel по сети. Поэтому сервис отвечает числами из ``state``, а наличие
    файлов проверяется по ``tmp_path``.
    """
    main = tmp_path / "Учет КПЗ 2026.xlsm"
    main.write_bytes(b"main")
    reserve = tmp_path / "Учет КПЗ 2026 запасная.xlsm"
    reserve.write_bytes(b"reserve")

    state = {
        "main": main,
        "reserve": reserve,
        "rows": {str(main): 100, str(reserve): 50},
        "role": "main",
    }
    switched: list[str] = []

    def set_active(self, path: str) -> None:
        switched.append(path)
        state["role"] = "reserve" if path == str(state["reserve"]) else "main"

    monkeypatch.setattr(ExcelService, "main_path", property(lambda self: state["main"]))
    monkeypatch.setattr(ExcelService, "reserve_path", property(lambda self: state["reserve"]))
    monkeypatch.setattr(ExcelService, "current_role", property(lambda self: state["role"]))
    monkeypatch.setattr(ExcelService, "count_book_rows", lambda self, path: state["rows"].get(str(path)))
    monkeypatch.setattr(ExcelService, "set_active_file", set_active)

    book = StandbyBook()
    return state, switched, book


def test_tick_switches_to_the_reserve_book(books):
    """Рост запасной при замершей основной — переключение ровно на её путь."""
    state, switched, book = books

    assert book.tick(now=0) is None, "первый замер ничего не решает"
    assert book.tick(now=FROZEN_SECONDS - 60) is None, "основная ещё не замерла"

    state["rows"][str(state["reserve"])] = 120
    assert book.tick(now=FROZEN_SECONDS - 30) is None, "30 минут ещё не прошло"

    switch = book.tick(now=FROZEN_SECONDS)

    assert switch is not None
    assert switch.role is Role.RESERVE
    assert switched == [str(state["reserve"])], "переключение — через владельца активной книги"
    assert excel_service.current_role == "reserve"


def test_tick_without_growth_does_not_switch(books):
    """Запасная полнее, но не растёт — чтение остаётся на основной."""
    state, switched, book = books
    state["rows"][str(state["reserve"])] = 500

    assert book.tick(now=0) is None
    assert book.tick(now=FROZEN_SECONDS - 1) is None
    assert book.tick(now=FROZEN_SECONDS * 3) is None

    assert switched == []


def test_tick_brings_a_selection_outside_the_roles_back_to_main(books):
    """Старая запись выбора: активная книга вне ролей — приводим к основной."""
    state, switched, book = books
    state["role"] = None

    assert book.tick(now=0) is None

    assert switched == [str(state["main"])]
    assert excel_service.current_role == "main"


def test_main_last_growth_is_the_moment_rows_appeared(books):
    """Баннер «основная не пополняется с …»: до первого роста данных нет."""
    state, _, book = books

    assert book.main_last_growth() is None
    assert book.tick(now=0) is None
    assert book.main_last_growth() is None, "первый замер — не рост"

    state["rows"][str(state["main"])] = 101
    assert book.tick(now=60) is None

    grown_at = book.main_last_growth()
    assert grown_at is not None and grown_at.tzinfo is not None


# --- Вход правила: число строк с реальными данными --------------------------


def _book_with_rows(tmp_path: Path, rows: list[tuple[str | None, int | None]]) -> Path:
    """Книга с боевой шапкой: две строки инструкций и строка заголовков."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Подвесы"
    ws.cell(row=1, column=1, value="инструкция")
    ws.cell(row=2, column=1, value="инструкция")
    headers = {
        4: "Дата",
        5: "Номер",
        6: "Время",
        8: "Вид материалов",
        9: "Годность подвеса",
        11: "НОМЕР КПЗ",
        12: "Заказчик",
        13: "Профиль",
        17: "Цвет",
        20: "Ламели, шт",
    }
    for column, title in headers.items():
        ws.cell(row=3, column=column, value=title)
    for index, (date, number) in enumerate(rows, start=4):
        ws.cell(row=index, column=4, value=date)
        ws.cell(row=index, column=5, value=number)
        ws.cell(row=index, column=6, value="08:00")
    path = tmp_path / "book.xlsx"
    wb.save(path)
    return path


def test_count_book_rows_counts_rows_with_date_or_number(tmp_path):
    """Наполненность — строки с датой ИЛИ номером подвеса, как на дашборде."""
    path = _book_with_rows(
        tmp_path,
        [
            ("2026-09-29", 5),
            (None, 6),
            ("2026-09-30", None),
            (None, None),
        ],
    )

    assert ExcelService().count_book_rows(path) == 3


def test_count_book_rows_is_none_when_the_book_is_unreadable(tmp_path):
    """Нечитаемая книга — ``None``, а не «ноль строк»: это разные решения."""
    broken = tmp_path / "broken.xlsm"
    broken.write_bytes(b"not an excel book")

    assert ExcelService().count_book_rows(broken) is None
    assert ExcelService().count_book_rows(None) is None
    assert ExcelService().count_book_rows(tmp_path / "missing.xlsm") is None


# --- Статистика для экрана: почему читается именно эта книга -----------------


def test_status_explains_disabled_reserve(monkeypatch):
    """Режим выключен — так и написано, а не «основная» без причины."""
    service = StandbyBook()
    monkeypatch.setattr(type(excel_service), "reserve_path", property(lambda self: None))

    assert "запасная не задана" in service.reason(now=NOW)


def test_status_reports_rows_presence_and_observation_time(monkeypatch):
    """Модалка получает строки, наличие файлов и момент начала наблюдения."""
    from app.services import standby_book as module

    service = StandbyBook()
    monkeypatch.setattr(type(excel_service), "main_path", property(lambda self: MAIN_PATH))
    monkeypatch.setattr(type(excel_service), "reserve_path", property(lambda self: None))
    monkeypatch.setattr(type(excel_service), "current_role", property(lambda self: "main"))
    monkeypatch.setattr(excel_service, "count_book_rows", lambda path: 100)
    monkeypatch.setattr(module, "path_exists", lambda path: True)

    service.tick(now=NOW)
    status = service.status(now=NOW)

    assert status["main_rows"] == 100
    assert status["main_present"] is True
    assert status["observed_since"] is not None
    assert status["reason"] == "запасная не задана — читается только основная"
