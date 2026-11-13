"""
Pydantic schemas for Profile
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileBase(BaseModel):
    """Base schema for Profile"""

    name: str = Field(..., min_length=1, max_length=255, description="Profile name")
    quantity_per_hanger: int | None = Field(None, ge=0, description="Quantity per hanger")
    length: float | None = Field(None, ge=0, description="Length in mm")
    notes: str | None = Field(None, max_length=2000, description="Additional notes")


class ProfileNotesUpdate(BaseModel):
    """Schema for updating a profile note - the only locally owned catalog field"""

    notes: str | None = Field(..., max_length=2000, description="Local note, null or empty clears it")


class ProfileResponse(ProfileBase):
    """Schema for profile response"""

    id: int
    description: str | None = Field(None, max_length=500, description="Article description from the source catalog")
    photo_thumb: str | None = None
    photo_full: str | None = None
    # Версии файлов для `?v=` в URL: считаются из mtime и размера файла,
    # поэтому замена фото мимо API тоже сбрасывает кэш.
    photo_thumb_version: str | None = None
    photo_full_version: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @property
    def has_photo(self) -> bool:
        """Check if profile has any photo"""
        return bool(self.photo_thumb or self.photo_full)


class ProfileInfo(BaseModel):
    """Profile info for display in dashboard"""

    name: str
    canonical_name: str | None = None
    processing: list[str] = Field(default_factory=list)
    has_photo: bool = False
    photo_thumb: str | None = None
    photo_full: str | None = None
    photo_thumb_version: str | None = None
    photo_full_version: str | None = None
    updated_at: str | None = None


class ProfileSearchResult(ProfileResponse):
    """Profile with search metadata"""

    similarity: float | None = None
    match_priority: int | None = None
