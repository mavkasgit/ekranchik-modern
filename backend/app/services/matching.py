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
Считается оно только для проходов, чей первый замер достоверен
(``first_seen_source == TRUSTED_FIRST_SEEN``): после старта монитора и после
разрыва связи замер равен моменту, когда монитор посмотрел, и расхождение по
нему ничего не значит. Такие проходы всё равно получают строку — по номеру и
ближайшей строке, но без дельты.

Строка, время которой позже выхода прохода, кандидатом не становится вовсе:
она описывает другой прогон. Это структурный запрет, а не оценка близости,
поэтому подмена строки следующего прогона невозможна по построению, а не
«возможна, но с бейджем».
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
# соседней смены отличается на часы, а не на минуты. По допуску ставится
# только пометка в журнале — на экран она не выводится, пока не откалибрована
# по живой линии (``entry_delta_sec`` пишется в журнал на каждой выгрузке).
MAX_ENTRY_DELTA_SECONDS = 3 * 3600

# Достоверный первый замер: монитор наблюдал линию непрерывно. Значение
# ставит line_monitor (``FIRST_SEEN_*``); ``start`` и ``gap`` — замер равен
# моменту, когда монитор посмотрел на линию, а не появлению подвеса.
TRUSTED_FIRST_SEEN = "watched"

# Вердикт подбора. Пустая строка — строка подобрана; на экране живут только
# ``NO_ROW`` и ``CYCLE_ERROR``, остальное разбирается в журнале.
CODE_OK = ""
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
    # Расхождение ``book_time - first_seen_at`` в секундах; ``None`` — первый
    # замер недостоверен или отсчёта нет, считать нечего. Поле остаётся
    # сырыми данными для калибровки допуска по живой линии.
    entry_delta_sec: Optional[float] = None
    # Пометка для журнала: ``entry_delta`` — расхождение больше допуска.
    # На экран не выводится, пока допуск не откалиброван.
    suspect_reason: str = ""
    # Сколько строк этого номера отброшено как записанные позже выхода.
    # Ноль — обычный случай; больше нуля значит, что допущение «строка не
    # позже выхода» на этих данных не выполняется, и это видно в журнале.
    rows_after_exit: int = 0


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

    Кандидаты — неиспользованные строки того же номера с заполненным временем,
    время которых НЕ позже выхода прохода. Из них берётся ближайшая к
    ``first_seen_at``:

    - сколько строк отброшено по выходу — в ``rows_after_exit`` (журнал);
    - расхождение больше допуска — ``suspect_reason``: это пометка для журнала,
      на экран она не идёт, пока допуск не откалиброван;
    - первый замер недостоверен (``first_seen_source`` монитора) — строка
      подбирается по номеру и близости, а ``entry_delta_sec`` не считается.

    Если строк по номеру нет вовсе (или все они позже выхода) — ``NO_ROW``.
    Проход, у которого ``line_monitor`` не нашёл открытого цикла, остаётся
    ``CYCLE_ERROR`` и строки не получает вовсе.
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
        candidates = []
        rows_after_exit = 0

        for row in rows_by_hanger.get(normalize_hanger_key(cycle.get("hanger")), []):
            if not has_entry_time(row) or make_product_key(row) in used:
                continue
            # Строка позже выхода этого прохода описывает другой прогон: она
            # не кандидат, а сколько таких — видно в журнале.
            if exit_at and product_entry_seconds(row) > exit_at:
                rows_after_exit += 1
                continue
            candidates.append(row)

        if not candidates:
            matches.append(
                CycleMatch(
                    cycle=cycle,
                    row=None,
                    code=CODE_NO_ROW,
                    rows_after_exit=rows_after_exit,
                )
            )
            continue

        # Ближайшая по модулю разности. При first_seen = 0 (нет данных о
        # начале прохода) порядок не определён — берём самую позднюю строку.
        trusted = cycle.get("first_seen_source") == TRUSTED_FIRST_SEEN
        if first_seen == 0.0:
            best = max(candidates, key=product_entry_seconds)
            delta = None
        else:
            best = min(
                candidates,
                key=lambda row: abs(product_entry_seconds(row) - first_seen),
            )
            delta = product_entry_seconds(best) - first_seen if trusted else None

        used.add(make_product_key(best))

        reason = ""
        if delta is not None and abs(delta) > MAX_ENTRY_DELTA_SECONDS:
            reason = "entry_delta"

        matches.append(
            CycleMatch(
                cycle=cycle,
                row=best,
                code=CODE_OK,
                entry_delta_sec=delta,
                suspect_reason=reason,
                rows_after_exit=rows_after_exit,
            )
        )

    order = sorted(range(len(matches)), key=lambda i: positions[i])
    return [matches[i] for i in order]


def match_log_line(match: CycleMatch, hanger: str) -> str:
    """Строка журнала на одну выгрузку: весь проход и вердикт сопоставления.

    Пишется по КАЖДОЙ выгрузке, а не только по спорной: расхождение входа
    калибруют по распределению, а по одному хвосту границу не поставить.
    Формат — ``ключ=значение``, чтобы строку можно было разобрать скриптом.
    """
    cycle = match.cycle

    def clock(value: Any) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%H:%M:%S")
        except (TypeError, ValueError):
            return "—"

    delta = match.entry_delta_sec
    delta_text = "—" if delta is None else f"{delta:+.0f}s({delta / 60:+.0f}m)"
    path = " ".join(
        f"{entry.get('bath')}@{clock(entry.get('in'))}->{clock(entry.get('out'))}"
        for entry in cycle.get("path") or []
    )
    return (
        f"[Matching] cycle={cycle.get('cycle_id')} hanger={hanger} "
        f"code={match.code or 'OK'} source={cycle.get('first_seen_source') or '—'} "
        f"bath={cycle.get('entry_bath')} first_seen={clock(cycle.get('first_seen_at'))} "
        f"exit={clock(cycle.get('exit_at'))} "
        f"row={f'{match.row.date} {match.row.time}' if match.row else '—'} "
        f"delta={delta_text} rows_after_exit={match.rows_after_exit} "
        f"note={match.suspect_reason or '—'} path={path or '—'}"
    )
