"""Add profiles.description

Наименование артикула приходит из каталога-источника (спека 0002): в киоске
поле только читается, поэтому колонка nullable и без значения по умолчанию.

Revision ID: 002
Revises: 001
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    # SQLite не умеет DROP COLUMN напрямую на старых версиях — batch-режим
    # пересобирает таблицу, оставаясь корректным для остальных СУБД.
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.drop_column("description")
