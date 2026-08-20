"""
Column resolution for the «Подвесы» sheet by header NAME.

Mirrors the VBA logic in kpz-uchet/vba/ColRef.bas: the header row is the
sheet's row 3 (1-based) — in Python's 0-based terms that is index 2, i.e. the
first row after skipping the two instruction rows. Matching lowercases and
trims edge whitespace/tabs/newlines (interior kept), and the LAST match wins
on duplicate headers.

Keep this module in sync with vba/ColRef.bas — the two must agree on rules.
"""
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple


@dataclass(frozen=True)
class ColumnField:
    """A single used column: its internal field name, the header texts it
    accepts (canonical first, then aliases), and its legacy 0-based position
    used as a fallback when no header matches."""

    field: str
    canonical: str
    aliases: Tuple[str, ...] = ()
    legacy_position: int = -1

    def header_names(self) -> Tuple[str, ...]:
        return (self.canonical, *self.aliases)


# Single source of truth for the 10 fields the backend reads. FIELDS and
# LEGACY_POSITIONS below are derived from this list, so a field added or
# removed here cannot silently drift from the others.
COLUMN_FIELDS: Tuple[ColumnField, ...] = (
    ColumnField("date", "Дата", legacy_position=3),
    ColumnField("number", "№ по порядку", ("Номер", "№"), 4),
    ColumnField("time", "Время", legacy_position=5),
    ColumnField("material_type", "Вид материалов", ("Тип материала", "Материал"), 7),
    ColumnField("defect", "Годность подвеса", legacy_position=8),
    ColumnField("kpz_number", "НОМЕР КПЗ", ("КПЗ", "№ КПЗ"), 10),
    ColumnField("client", "Заказчик", ("Клиент",), 11),
    ColumnField("profile", "Профиль", legacy_position=12),
    ColumnField("color", "Цвет", legacy_position=16),
    ColumnField("lamels_qty", "Ламели, шт", ("Ламели шт", "Кол-во ламелей", "Ламели"), 19),
)

FIELDS: Tuple[str, ...] = tuple(f.field for f in COLUMN_FIELDS)
LEGACY_POSITIONS: Dict[str, int] = {
    f.field: f.legacy_position for f in COLUMN_FIELDS
}


@dataclass(frozen=True)
class ColumnResolution:
    """Result of resolving a header row: every field mapped to a 0-based
    column index (name match preferred, else its legacy position), plus the
    set of fields that were actually found by header name."""

    positions: Dict[str, int]
    found_by_name: Set[str]

    @property
    def missing(self) -> Set[str]:
        """Fields that had no matching header and fell back to legacy positions."""
        return set(FIELDS) - self.found_by_name


def normalize_header(value) -> str:
    """Lowercase and trim edge whitespace/tabs/newlines (interior kept).

    Mirrors ColRef.Normalize / TrimWs in vba/ColRef.bas.
    """
    if value is None:
        return ""
    return str(value).strip(" \t\r\n").lower()


def find_column(header_row, header_text: str) -> int:
    """Return 0-based column index of the LAST header matching header_text.

    Mirrors ColRef.FindColumn: walks columns right-to-left, so a duplicate
    header (e.g. «№ по порядку» in both A and E) resolves to the rightmost
    occurrence — the one carrying real data. Returns -1 when not found.
    """
    needle = normalize_header(header_text)
    if not needle:
        return -1
    # header_row may be a pandas Series or a plain sequence; materialize to a
    # list so indexing is positional regardless of the Series' index labels.
    values = list(header_row)
    for idx in range(len(values) - 1, -1, -1):
        if normalize_header(values[idx]) == needle:
            return idx
    return -1


def resolve_columns(header_row) -> ColumnResolution:
    """Resolve every field in COLUMN_FIELDS to a 0-based column index.

    For each field, the canonical header is tried first, then its aliases;
    the first header that matches (by find_column) wins. A field with no
    matching header falls back to its legacy position.
    """
    positions: Dict[str, int] = {}
    found_by_name: Set[str] = set()

    for cf in COLUMN_FIELDS:
        idx = -1
        for header in cf.header_names():
            idx = find_column(header_row, header)
            if idx >= 0:
                break
        if idx >= 0:
            positions[cf.field] = idx
            found_by_name.add(cf.field)
        else:
            positions[cf.field] = cf.legacy_position

    return ColumnResolution(positions=positions, found_by_name=found_by_name)