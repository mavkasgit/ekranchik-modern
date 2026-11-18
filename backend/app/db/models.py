"""
SQLAlchemy ORM Models
"""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Profile(Base):
    """
    Profile model - represents a product profile in the catalog.

    Stores profile information including name, dimensions, photos,
    and usage statistics.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity_per_hanger: Mapped[int | None] = mapped_column(Integer, nullable=True)
    length: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_thumb: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_full: Mapped[str | None] = mapped_column(String(500), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Index for faster search by usage count
    __table_args__ = (Index("idx_profile_usage", "usage_count", postgresql_using="btree"),)

    def __repr__(self) -> str:
        return f"<Profile(id={self.id}, name='{self.name}')>"

    @property
    def has_photo(self) -> bool:
        """Check if profile has any photo"""
        return bool(self.photo_thumb or self.photo_full)


class Color(Base):
    """Цвет покрытия — локальная копия операций анодирования KTM.

    Ключ синка — ``operation_code``. Отображаемый ``code`` может быть пустым:
    у старых ``ANOD_01…08`` кода в книге учёта нет. ``source`` говорит,
    откуда строка пришла последней, ``updated_at`` — когда: синк перекрывает
    строку, только если метка KTM строго новее (тикет 0023).
    """

    __tablename__ = "colors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hex: Mapped[str] = mapped_column(String(7), nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    operation_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="local", server_default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("source IN ('ktm', 'local')", name="ck_colors_source"),
        Index("idx_colors_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Color(id={self.id}, code='{self.code}', name='{self.name}')>"
