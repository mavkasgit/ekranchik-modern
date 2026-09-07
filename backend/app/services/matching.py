"""Shared hanger (подвес) <-> Excel row matching.

Single source of truth for the "newest valid entry" rule used by both:
- dashboard ``/opcua-unload-matched`` (unload event -> Excel row),
- opcua hanger meta (latest profile/color per hanger number).

Rule: among the candidate rows of one hanger number, the newest row with
entry time ``<=`` exit moment + ``EXIT_AFTER_TOLERANCE_SECONDS`` wins.
Candidates are ranked by parsed Excel date+time desc; rows with
unparseable dates (or without time) rank as 0, so a stable sort keeps
them in file order as a fallback. Already matched rows are tracked via
``used_keys`` so one row is never reused by two events.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# A hanger cannot be loaded more than 3h after it was unloaded
# (operator input delay tolerance). Rows past this bound are impossible
# matches and are skipped, ranking still follows date, not time math.
EXIT_AFTER_TOLERANCE_SECONDS = 3 * 3600

# Raw Excel time cells with these values mean "not yet loaded into line".
_EMPTY_TIME_TOKENS = frozenset({"", "—", "nan", "NaT", "None"})


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


def has_entry_time(product: Dict[str, Any]) -> bool:
    """True when the row is a real loaded entry (time cell is filled)."""
    raw = str(product.get("time", "") or "").strip()
    return raw not in _EMPTY_TIME_TOKENS


def product_entry_seconds(product: Dict[str, Any]) -> float:
    """Ranking key of an Excel row: entry epoch seconds, 0.0 if unusable."""
    if not has_entry_time(product):
        return 0.0
    return excel_datetime_to_seconds(
        parse_excel_date(str(product.get("date", ""))),
        parse_excel_time(str(product.get("time", ""))),
    )


def make_product_key(product: Dict[str, Any]) -> str:
    """Unique key of an Excel row to track already matched entries."""
    return f"{product.get('date', '')}|{product.get('time', '')}|{product.get('number', '')}"


def event_exit_seconds(event: Dict[str, Any]) -> float:
    """Exit moment of an unload event as epoch seconds; 0.0 if unparseable."""
    return excel_datetime_to_seconds(
        parse_excel_date(event.get("date") or ""),
        parse_excel_time(event.get("time") or ""),
    )


def select_latest_candidate(
    candidates: List[Dict[str, Any]],
    exit_seconds: Optional[float] = None,
    used_keys: Optional[set] = None,
    require_time: bool = True,
) -> Optional[Dict[str, Any]]:
    """Pick the newest valid row: entry time <= exit + 3h tolerance.

    Ranking is by parsed date desc; unparseable rows keep file order
    (stable sort). Skips already ``used_keys`` rows, rows without time
    (when ``require_time``), and rows loaded more than 3h after the exit.
    With ``exit_seconds=None`` (or 0) the guard is off: newest row wins.
    """
    used = used_keys or set()
    # Stable sort: equal keys (unparseable -> 0.0) keep file order.
    ranked = sorted(candidates, key=product_entry_seconds, reverse=True)
    for product in ranked:
        if make_product_key(product) in used:
            continue
        if require_time and not has_entry_time(product):
            continue
        if exit_seconds:
            if product_entry_seconds(product) - exit_seconds > EXIT_AFTER_TOLERANCE_SECONDS:
                continue
        return product
    return None


def match_unload_events(
    events: List[Dict[str, Any]],
    products_by_hanger: Dict[str, List[Dict[str, Any]]],
) -> List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    """Greedily match unload events to Excel rows, newest exit first.

    Newest-first order guarantees chronological distribution when a hanger
    cycled twice in one shift: the newest exit takes the newest row, the
    older exit keeps the older row. Returns (event, product|None) pairs in
    newest-first order.
    """
    used: set = set()
    ordered = sorted(events, key=event_exit_seconds, reverse=True)
    matched: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]] = []
    for event in ordered:
        candidates = products_by_hanger.get(str(event.get("hanger")), [])
        product = select_latest_candidate(
            candidates,
            exit_seconds=event_exit_seconds(event),
            used_keys=used,
        )
        if product is not None:
            used.add(make_product_key(product))
        matched.append((event, product))
    return matched
