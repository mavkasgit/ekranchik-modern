"""Initial profiles table

Revision ID: 001
Revises: 
Create Date: 2024-12-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('quantity_per_hanger', sa.Integer(), nullable=True),
        sa.Column('length', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('photo_thumb', sa.String(length=500), nullable=True),
        sa.Column('photo_full', sa.String(length=500), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('idx_profile_name', 'profiles', ['name'], unique=False)
    op.create_index('idx_profile_usage', 'profiles', ['usage_count'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_profile_usage', table_name='profiles')
    op.drop_index('idx_profile_name', table_name='profiles')
    op.drop_table('profiles')
