"""Add colors dictionary

Справочник цветов — локальная копия операций анодирования KTM (спека 0003,
тикет 0022). Таблица засевается двадцатью двумя строками: десять текущих
названий и двенадцать цветов веера ClassicELOX. ``operation_code`` —
уникальный ключ синка, ``source``/``updated_at`` — поля правила «новее —
правильнее».

Revision ID: 003
Revises: 002
Create Date: 2026-11-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.color_seed import seed_missing_colors

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "colors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("hex", sa.String(length=7), nullable=False),
        sa.Column("operation_code", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=16), server_default="local", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("source IN ('ktm', 'local')", name="ck_colors_source"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_code", name="uq_colors_operation_code"),
    )
    op.create_index("idx_colors_name", "colors", ["name"], unique=False)

    # Засев идемпотентен: повторный запуск после сбоя не создаёт дублей.
    seed_missing_colors(op.get_bind())


def downgrade() -> None:
    op.drop_index("idx_colors_name", table_name="colors")
    op.drop_table("colors")
