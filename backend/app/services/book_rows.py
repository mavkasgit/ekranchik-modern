"""Строки книги учёта: одно окно, один разбор, один кэш.

Три потребителя читали книгу каждый по-своему: карточки OPC UA — с лимитом
3000 строк, панель «Выход» и журнал — с лимитом 1000. Одна и та же строка
для одного экрана существовала, а для другого уже нет, и каждый держал свою
копию разбора.

Здесь окно объявлено один раз: всем нужны последние строки книги (3000
строк — примерно месяц на живой линии), сгруппированные по номеру подвеса.
Кэш держит и сами строки, и группировку, и «последнюю строку на подвес»:
пересборка идёт только когда меняется файл или разобранный лист, а не на
каждый запрос панели «Выход».
"""

from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.services.excel_service import excel_service
from app.services.hanger_row import HangerRow
from app.services.matching import normalize_hanger_key, select_latest_candidate

# Окно книги для всех потребителей. 3000 строк — примерно месяц на живой
# линии; этого хватает и журналу, и карточкам OPC UA, и панели «Выход».
BOOK_ROWS_LIMIT = 3000


@dataclass(frozen=True)
class BookRows:
    """Разобранные строки книги в трёх формах, которые нужны потребителям."""

    products: list[HangerRow]
    by_hanger: dict[str, list[HangerRow]]
    latest_by_hanger: dict[str, dict[str, str]]


def _meta_text(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text else "—"


def _latest_meta(by_hanger: dict[str, list[HangerRow]]) -> dict[str, dict[str, str]]:
    """Профиль и цвет последней строки на номер подвеса.

    Правило выбора живёт в ``matching.select_latest_candidate``: самая
    поздняя строка с заполненным временем, а черновик без времени — только
    если реальных загрузок у номера нет.
    """
    latest: dict[str, dict[str, str]] = {}
    for hanger_key, candidates in by_hanger.items():
        best = select_latest_candidate(candidates)
        if best is None:
            best = select_latest_candidate(candidates, require_time=False)
        if best is None:
            continue
        latest[hanger_key] = {
            "article": _meta_text(best.profile),
            "color": _meta_text(best.color),
        }
    return latest


_lock = Lock()
_cached: BookRows | None = None
_cached_version: tuple | None = None


def get_book_rows() -> BookRows:
    """Строки книги из общего кэша; пересборка — при смене файла или листа."""
    global _cached, _cached_version

    version = excel_service.data_version
    if _cached is not None and _cached_version == version:
        return _cached

    with _lock:
        # Пока ждали блокировку, другой поток мог уже собрать этот же файл.
        version = excel_service.data_version
        if _cached is not None and _cached_version == version:
            return _cached

        products = excel_service.get_products(
            limit=BOOK_ROWS_LIMIT,
            from_end=True,
            loading_only=False,
        )
        by_hanger: dict[str, list[HangerRow]] = {}
        for product in products:
            hanger_key = normalize_hanger_key(product.number)
            if hanger_key:
                by_hanger.setdefault(hanger_key, []).append(product)

        _cached = BookRows(
            products=products,
            by_hanger=by_hanger,
            latest_by_hanger=_latest_meta(by_hanger),
        )
        # Версию читаем после разбора: первый вызов заполняет mtime, и кэш
        # должен совпасть со следующим обращением, а не с пустым стартом.
        _cached_version = excel_service.data_version
        return _cached


def reset_book_rows_cache() -> None:
    """Сбросить кэш (тесты и смена активной книги в одном процессе)."""
    global _cached, _cached_version
    with _lock:
        _cached = None
        _cached_version = None
