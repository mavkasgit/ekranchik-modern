"""Связь физического прохода подвеса по линии со строкой книги учёта.

`line_monitor` фиксирует КАЖДЫЙ проход как отдельный объект: ``cycle_id``,
``hanger``, ``first_seen_at``, ``entry_bath``, ``exit_at``. Номера подвесов
повторяются от смены к смены, поэтому номер подвеса НЕ является
идентификатором прохода — им является ``cycle_id``.

Якорь для подбора строки — ``first_seen_at`` (момент, когда монитор впервые
увидел подвес в любой ванне этого прохода), а не время выхода: выход у всех
циклов один и тот же по природе, а вход различает проходы. Дата и время из
книги остаются вторым независимым подтверждением.

Физического входа в линию мы не знаем — знаем только момент обнаружения,
поэтому расхождение ``book_time - first_seen_at`` возвращается в
``CycleMatch.entry_delta_sec``: по нему калибруется допуск на живой линии.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.services.hanger_row import HangerRow

# Допуск между временем входа в книге и моментом, когда монитор увидел
# подвес в линии. Подвес проводит на линии около трёх часов, и разница
# между записью оператора и первым замером настолько же велика: монитор
# видит подвес уже в ванне, то есть позже физического входа. Прежние
# 15 минут помечали бейджем каждый нормальный проход.
#
# Ловит не бытовое расхождение, а настоящую ошибку подбора: строка
# соседней смены отличается на часы, а не на минуты.
MAX_ENTRY_DELTA_SECONDS = 3 * 3600

# Причины, по которым подбор не даёт уверенного попадания. Пустая строка —
# строка подобрана уверенно, бейдж не показывается.
CODE_OK = ""
CODE_SUSPECT = "SUSPECT"
CODE_NO_ROW = "NO_ROW"
CODE_CYCLE_ERROR = "CYCLE_ERROR"

# Raw Excel time cells with these values mean "not yet loaded into line".
_EMPTY_TIME_TOKENS = frozenset({"", "—", "nan", "NaT", "None"})


@dataclass(frozen=True)
class CycleMatch:
    """Результат подбора строки книги к одному проходу подвеса."""

    cycle: Dict[str, Any]
    row: Optional[HangerRow]
    code: str = CODE_OK
    entry_delta_sec: Optional[float] = None
    # Почему подбор сомнителен: строка позже выхода этого прохода, значит
    # она принадлежит более позднему прогону; иначе — само расхождение.
    suspect_reason: str = ""


def parse_excel_date(date_str: str) -> Tuple[int, int, int]:
    """Parse DD.MM.YYYY or DD.MM.YY to (year, month, day); (0, 0, 0) if bad."""
    if not date_str or date_str == "—":
        return (0, 0, 0)
    try:
        parts = date_str.strip().split(".")
        if len(parts) != 3:
            return (0, 0, 0)
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        # 2-digit years: 00-49 -> 2000-2049, 50-99 -> 1950-1999
        if year < 50:
            year += 2000
        elif year < 100:
            year += 1900
        return (year, month, day)
    except (ValueError, IndexError):
        return (0, 0, 0)


def parse_excel_time(time_str: str) -> Tuple[int, int, int]:
    """Parse HH:MM:SS or HH:MM to (hour, minute, second); (0, 0, 0) if bad."""
    if not time_str or time_str == "—":
        return (0, 0, 0)
    try:
        parts = time_str.strip().split(":")
        hour = int(parts[0]) if len(parts) > 0 else 0
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return (hour, minute, second)
    except (ValueError, IndexError):
        return (0, 0, 0)


def excel_datetime_to_seconds(
    date_tuple: Tuple[int, int, int], time_tuple: Tuple[int, int, int]
) -> float:
    """Convert date+time tuples to epoch seconds; 0.0 if not a real date."""
    try:
        year, month, day = date_tuple
        hour, minute, second = time_tuple
        if year == 0 or month == 0 or day == 0:
            return 0.0
        return datetime(year, month, day, hour, minute, second).timestamp()
    except (ValueError, OverflowError):
        return 0.0


def normalize_hanger_key(value: Any) -> str:
    """Normalize a hanger number cell (``'5'``, ``5.0``, ``5``) to ``'5'``."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        numeric = float(raw.replace(",", "."))
        return str(int(numeric))
    except (ValueError, TypeError):
        return raw


def has_entry_time(product: HangerRow) -> bool:
    """True when the row is a real loaded entry (time cell is filled)."""
    raw = str(product.time or "").strip()
    return raw not in _EMPTY_TIME_TOKENS


def product_entry_seconds(product: HangerRow) -> float:
    """Entry moment of an Excel row as epoch seconds; 0.0 if unusable."""
    if not has_entry_time(product):
        return 0.0
    return excel_datetime_to_seconds(
        parse_excel_date(str(product.date)),
        parse_excel_time(str(product.time)),
    )


def make_product_key(product: HangerRow) -> str:
    """Unique key of an Excel row to track already matched entries."""
    return f"{product.date}|{product.time}|{product.number}"


def parse_iso_seconds(value: Any) -> float:
    """Epoch seconds of an ISO timestamp; 0.0 when missing or unparseable."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _cycle_first_seen(cycle: Dict[str, Any]) -> float:
    return parse_iso_seconds(cycle.get("first_seen_at"))


def _cycle_exit(cycle: Dict[str, Any]) -> float:
    return parse_iso_seconds(cycle.get("exit_at"))


def select_latest_candidate(
    candidates: List[HangerRow],
    used_keys: Optional[set] = None,
    require_time: bool = True,
) -> Optional[HangerRow]:
    """Самая поздняя строка номера — для метаданных профиля и цвета.

    Используется эндпоинтом api/routes/opcua.py, где нужно «что сейчас
    загружено», а не «какая строка соответствует выгрузке»: там номер
    подвеса и есть ключ, потому что показывается текущий проход.

    ``require_time=True`` — самая поздняя строка с заполненным и
    распарсенным временем. ``False`` — черновик, у которого время в книге
    ещё не проставлено: сравнивать нечем, поэтому берётся нижняя строка
    файла, её дописывают последней.
    """
    used = used_keys or set()
    if not require_time:
        for product in candidates:
            if make_product_key(product) not in used:
                return product
        return None

    best, best_seconds = None, 0.0
    for product in candidates:
        if make_product_key(product) in used:
            continue
        if not has_entry_time(product):
            continue
        seconds = product_entry_seconds(product)
        if seconds == 0.0:
            continue
        if best is None or seconds > best_seconds:
            best, best_seconds = product, seconds
    return best


def match_cycles_to_rows(
    cycles: List[Dict[str, Any]],
    rows_by_hanger: Dict[str, List[HangerRow]],
) -> List[CycleMatch]:
    """Привязать строку книги к каждому проходу подвеса.

    Проходы ОБРАБАТЫВАЮТСЯ по времени ``first_seen_at`` — от ранних к
    поздним, поэтому ранний проход забирает свою строку, а не более позднюю.
    Одна строка книги не достаётся двум проходам.

    Порядок ВОЗВРАТА — входной, а не порядок подбора: ранние проходы разбираются
    первыми, но в ответе остаются там, где их передал вызывающий. Иначе только
    что сошедший подвес оказывался бы внизу таблицы выхода.

    Для обычного прохода берётся неиспользованная строка того же номера,
    ближайшая к ``first_seen_at``:

    - бейдж не показывается;
    - строка позже выхода этого прохода — она принадлежит более позднему
      прогону; строка всё равно показывается, но с ``SUSPECT``;
    - расхождение больше допуска — ``SUSPECT``: причина может быть любой,
      решение за оператором.

    Если строк по номеру нет вовсе — ``NO_ROW``. Проход, у которого
    ``line_monitor`` не нашёл открытого цикла, остаётся ``CYCLE_ERROR`` и
    строки не получает вовсе.
    """
    matches: List[CycleMatch] = []
    # Позиция каждого подбора во входном списке — её восстановим в конце.
    positions: List[int] = []
    used: set = set()

    # Разбираем проходы по времени first_seen_at, от ранних к поздним, чтобы
    # ранний проход забирал свою строку, а не более позднюю. Это порядок
    # ПОДБОРА, а не выдачи: результат возвращается в порядке вызывающего
    # (см. get_unload_events — новые выходы сверху), потому что таблица
    # выхода читается сверху вниз.
    for position, cycle in sorted(
        enumerate(cycles), key=lambda pair: _cycle_first_seen(pair[1])
    ):
        positions.append(position)
        if cycle.get("type") == "cycle_error":
            matches.append(CycleMatch(cycle=cycle, row=None, code=CODE_CYCLE_ERROR))
            continue

        first_seen = _cycle_first_seen(cycle)
        exit_at = _cycle_exit(cycle)
        candidates = [
            row
            for row in rows_by_hanger.get(normalize_hanger_key(cycle.get("hanger")), [])
            if has_entry_time(row) and make_product_key(row) not in used
        ]

        if not candidates:
            matches.append(CycleMatch(cycle=cycle, row=None, code=CODE_NO_ROW))
            continue

        # Ближайшая по модулю разности. При first_seen = 0 (нет данных о
        # начале прохода) порядок не определён — берём самую позднюю строку.
        if first_seen == 0.0:
            best = max(candidates, key=product_entry_seconds)
            delta = None
        else:
            best = min(
                candidates,
                key=lambda row: abs(product_entry_seconds(row) - first_seen),
            )
            delta = product_entry_seconds(best) - first_seen

        used.add(make_product_key(best))

        code, reason = CODE_OK, ""
        if exit_at and product_entry_seconds(best) > exit_at:
            code = CODE_SUSPECT
            reason = "later_run"
        elif delta is not None and abs(delta) > MAX_ENTRY_DELTA_SECONDS:
            code = CODE_SUSPECT
            reason = "entry_delta"

        matches.append(
            CycleMatch(
                cycle=cycle,
                row=best,
                code=code,
                entry_delta_sec=delta,
                suspect_reason=reason,
            )
        )

    order = sorted(range(len(matches)), key=lambda i: positions[i])
    return [matches[i] for i in order]
