"""Кэш книги под блокировкой: ждущий запрос не читает CIFS второй раз (#76).

Книга учёта лежит на сетевой шаре, и чтение может занять секунды. Пока один
запрос читает её в своём потоке, второй уже ждёт на блокировке: когда она
откроется, файл и кэш надо перепроверить и взять готовый разбор. Иначе на
каждый одновременный запрос приходилось бы ещё одно чтение по сети.

Здесь книга подменена: тест проверяет не разбор Excel, а число чтений файла.
"""

import os
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

from app.services.excel_service import ExcelService


def _book(tmp_path: Path) -> Path:
    book = tmp_path / "book.xlsx"
    book.write_bytes(b"not a real workbook")
    return book


def _frame(rows: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-11-01")] * rows,
            "number": list(range(rows)),
            "profile": ["1010"] * rows,
        }
    )


@pytest.fixture
def service(tmp_path: Path) -> ExcelService:
    instance = ExcelService()
    instance.use_file(str(_book(tmp_path)))
    return instance


def _read_in_threads(service: ExcelService, readers: int = 2) -> dict[str, pd.DataFrame]:
    """Два запроса стартуют одновременно и оба читают книгу."""
    barrier = threading.Barrier(readers)
    results: dict[str, pd.DataFrame] = {}

    def read(index: int) -> None:
        barrier.wait()
        results[str(index)] = service.get_dataframe(full_dataset=True)

    threads = [threading.Thread(target=read, args=(index,)) for index in range(readers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "чтение книги зависло"
    return results


def test_waiting_request_takes_the_book_from_the_cache(service, monkeypatch):
    """Второй ждущий запрос с тем же mtime не читает книгу повторно."""
    reads: list[int] = []

    def slow_read(path: Path, sheet_name: str) -> pd.DataFrame:
        reads.append(threading.get_ident())
        time.sleep(0.3)
        return _frame()

    monkeypatch.setattr(service, "_read_dataframe_by_header", slow_read)

    results = _read_in_threads(service)

    assert len(reads) == 1, "книга прочитана повторно, хотя не менялась"
    assert all(not frame.empty for frame in results.values())


def test_book_is_read_again_after_it_changes(service, monkeypatch):
    """Новый mtime — новое чтение: кэш не отдаёт устаревший лист."""
    reads: list[int] = []

    def read(path: Path, sheet_name: str) -> pd.DataFrame:
        reads.append(threading.get_ident())
        return _frame()

    monkeypatch.setattr(service, "_read_dataframe_by_header", read)

    service.get_dataframe(full_dataset=True)
    assert len(reads) == 1

    book = service.current_path
    assert book is not None
    later = book.stat().st_mtime + 10
    os.utime(book, (later, later))

    service.get_dataframe(full_dataset=True)

    assert len(reads) == 2, "изменённая книга обязана читаться заново"
