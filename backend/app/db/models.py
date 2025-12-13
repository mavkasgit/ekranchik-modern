"""
SQLAlchemy ORM Models
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, DateTime, func, Index
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
    quantity_per_hanger: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_thumb: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    photo_full: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Index for faster search by usage count
    __table_args__ = (
        Index('idx_profile_usage', 'usage_count', postgresql_using='btree'),
    )
    
    def __repr__(self) -> str:
        return f"<Profile(id={self.id}, name='{self.name}')>"
    
    @property
    def has_photo(self) -> bool:
        """Check if profile has any photo"""
        return bool(self.photo_thumb or self.photo_full)
