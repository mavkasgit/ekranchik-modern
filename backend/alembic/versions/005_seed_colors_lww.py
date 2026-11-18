"""Normalize seeded colors for last-write-wins

Засев ``003`` ставил ``updated_at = CURRENT_TIMESTAMP``: локальная строка
оказывалась новее операций KTM, и первый синк её не перекрывал. Здесь
нетронутые строки засева получают старую метку ``2000-01-01``, а hex веера
приводится к значениям T-378, чтобы локальная копия и KTM не расходились.

Правленые строки (``updated_at`` уже не равен ``created_at``) и строки из KTM
не трогаются: их время — это время правки, а не засева.

Revision ID: 005
Revises: 004
Create Date: 2026-11-18

"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op
from app.db.color_seed import SEED_COLORS, SEED_UPDATED_AT, reset_untouched_seed_colors

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Прежние справочные значения веера — только для честного отката миграции.
_LEGACY_FAN_HEX = {
    "C0": "#C9CCCE",
    "C35": "#2A2A2A",
    "S120-0": "#D4AF37",
    "S120-2": "#B08D57",
    "C31": "#E9D9BC",
    "C32": "#C8B184",
    "C33": "#B0895C",
    "C34": "#7B5A38",
    "C41": "#B87333",
    "C44": "#8C5230",
    "C51": "#A8A9AD",
    "C54": "#5C5D60",
}

_REVERT_UNTOUCHED_SEED = text(
    """
    UPDATE colors SET hex = :hex, updated_at = CURRENT_TIMESTAMP
    WHERE source = 'local'
      AND updated_at = :updated_at
      AND (
        (:operation_code IS NOT NULL AND operation_code = :operation_code)
        OR (:operation_code IS NULL AND :code IS NOT NULL AND code = :code)
      )
    """
)


def upgrade() -> None:
    reset_untouched_seed_colors(op.get_bind())


def downgrade() -> None:
    """Вернуть старые hex веера и метку текущего времени у нетронутых строк."""
    bind = op.get_bind()
    for color in SEED_COLORS:
        legacy = _LEGACY_FAN_HEX.get(color["code"] or "", color["hex"])
        bind.execute(_REVERT_UNTOUCHED_SEED, {**color, "hex": legacy, "updated_at": SEED_UPDATED_AT})
