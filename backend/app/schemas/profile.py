"""
Pydantic schemas for Profile
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class ProfileBase(BaseModel):
    """Base schema for Profile"""
    name: str = Field(..., min_length=1, max_length=255, description="Profile name")
    quantity_per_hanger: Optional[int] = Field(None, ge=0, description="Quantity per hanger")
    length: Optional[float] = Field(None, ge=0, description="Length in mm")
    notes: Optional[str] = Field(None, max_length=2000, description="Additional notes")


class ProfileCreate(ProfileBase):
    """Schema for creating a new profile"""
    pass


class ProfileUpdate(BaseModel):
    """Schema for updating a profile"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    quantity_per_hanger: Optional[int] = Field(None, ge=0)
    length: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=2000)
    photo_thumb: Optional[str] = None
    photo_full: Optional[str] = None
    usage_count: Optional[int] = Field(None, ge=0)


class ProfileResponse(ProfileBase):
    """Schema for profile response"""
    id: int
    photo_thumb: Optional[str] = None
    photo_full: Optional[str] = None
    usage_count: int = 0
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
    canonical_name: Optional[str] = None
    processing: List[str] = Field(default_factory=list)
    has_photo: bool = False
    photo_thumb: Optional[str] = None
    photo_full: Optional[str] = None
    updated_at: Optional[str] = None


class ProfileSearchResult(ProfileResponse):
    """Profile with search metadata"""
    similarity: Optional[float] = None
    match_priority: Optional[int] = None


class ProfileMissing(BaseModel):
    """Profile without photo for analysis page"""
    profile: str
    date: str
    number: str
    has_photo: bool = False
    row_number: Optional[int] = None
    count: Optional[int] = None
