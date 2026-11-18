"""Add colors.abbreviation

Привычная подпись цвета в ячейке (``брз``, ``рст``, ``C32``) хранится рядом с
названием, а не выводится из кода или названия: правило «первые буквы» ломало
старые подписи. Колонка необязательная — строки из синка могут прийти без неё,
тогда клиент показывает запасной вариант.

Revision ID: 004
Revises: 003
Create Date: 2026-11-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.color_seed import fill_seed_abbreviations

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("colors", sa.Column("abbreviation", sa.String(length=16), nullable=True))
    # Заполняем уже засеянные строки (на dev-базе ``003`` применена раньше).
    fill_seed_abbreviations(op.get_bind())


def downgrade() -> None:
    # SQLite не умеет DROP COLUMN напрямую — batch-режим пересобирает таблицу.
    with op.batch_alter_table("colors") as batch_op:
        batch_op.drop_column("abbreviation")
