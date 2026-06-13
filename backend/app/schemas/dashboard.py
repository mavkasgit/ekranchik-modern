"""
Pydantic schemas for Dashboard data
"""
from datetime import datetime
from typing import Optional, List, Union

from pydantic import BaseModel, Field

from app.schemas.profile import ProfileInfo


class HangerData(BaseModel):
    """Data for a single hanger row in dashboard"""
    number: str = Field(..., description="Hanger number")
    date: str = Field(..., description="Date string")
    time: str = Field(..., description="Time string")
    client: str = Field(default="—", description="Client name")
    profile: str = Field(default="—", description="Profile name(s)")
    canonical_name: Optional[str] = None
    profiles_info: List[ProfileInfo] = Field(default_factory=list)
    profile_photo_thumb: Optional[str] = None
    profile_photo_full: Optional[str] = None
    color: str = Field(default="—", description="Color")
    lamels_qty: Union[int, str] = Field(default=0, description="Lamels quantity")
    kpz_number: str = Field(default="—", description="KPZ number")
    material_type: str = Field(default="—", description="Material type")
    is_defect: bool = Field(default=False, description="True if defect/браk")


class UnloadEvent(BaseModel):
    """Raw unload event from OPC UA"""
    time: str
    hanger: int = Field(..., ge=0)


class MatchedUnloadEvent(BaseModel):
    """Unload event matched with Excel data"""
    exit_date: str
    exit_time: str
    hanger: int
    # From Excel (if matched)
    entry_date: Optional[str] = None
    entry_time: Optional[str] = None
    client: str = "—"
    profile: str = "—"
    profiles_info: List[ProfileInfo] = Field(default_factory=list)
    color: str = "—"
    lamels_qty: Union[int, str] = 0
    kpz_number: str = "—"
    material_type: str = "—"
    # Forecast info - current bath and processing time
    current_bath: Optional[int] = None  # Bath number 30-33 where hanger currently is
    bath_entry_time: Optional[str] = None  # Time when hanger entered current bath (HH:MM:SS)
    bath_processing_time: Optional[int] = None  # Expected processing time in seconds for current bath


class DashboardResponse(BaseModel):
    """Response for dashboard API"""
    success: bool = True
    products: List[HangerData] = Field(default_factory=list)
    unloading_products: List[HangerData] = Field(default_factory=list)
    total: int = 0
    total_all: int = 0
    days_filter: Optional[int] = None
    dual_mode: bool = False
    error: Optional[str] = None


class FileStatus(BaseModel):
    """Excel file status"""
    is_open: bool = False
    last_modified: Optional[datetime] = None
    file_name: Optional[str] = None
    status_text: str = "Неизвестно"
    error: Optional[str] = None
    seconds_since_modified: Optional[float] = None


class ExcelFileInfo(BaseModel):
    """Detailed information about an Excel file or directory"""
    name: str
    path: str
    size_bytes: int
    size_formatted: str
    last_modified: datetime
    is_dir: bool = False


class ExcelFileListResponse(BaseModel):
    """Response for Excel files list"""
    success: bool = True
    files: List[ExcelFileInfo] = []
    active: str
    current_directory: str
    parent_directory: Optional[str] = None
    error: Optional[str] = None


class ExcelFileSelectRequest(BaseModel):
    """Request to select active Excel file"""
    file_path: Optional[str] = None
    file_name: Optional[str] = None





