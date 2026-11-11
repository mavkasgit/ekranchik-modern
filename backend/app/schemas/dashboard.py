"""
Pydantic schemas for Dashboard data
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.profile import ProfileInfo


class HangerData(BaseModel):
    """Data for a single hanger row in dashboard"""

    number: str = Field(..., description="Hanger number")
    date: str = Field(..., description="Date string")
    time: str = Field(..., description="Time string")
    client: str = Field(default="—", description="Client name")
    profile: str = Field(default="—", description="Profile name(s)")
    profiles_info: list[ProfileInfo] = Field(default_factory=list)
    color: str = Field(default="—", description="Color")
    lamels_qty: int | str = Field(default=0, description="Lamels quantity")
    kpz_number: str = Field(default="—", description="KPZ number")
    material_type: str = Field(default="—", description="Material type")
    is_defect: bool = Field(default=False, description="True if defect/браk")


class MatchedUnloadEvent(BaseModel):
    """Проход подвеса по линии, сопоставленный со строкой книги учёта"""

    # Физический проход — из line_monitor
    cycle_id: int | None = None
    first_seen_at: str | None = None  # Когда монитор впервые увидел подвес в линии
    entry_bath: int | None = None  # Ванна, в которой подвес появился
    # Из книги учёта (если строка подобрана)
    entry_date: str | None = None
    entry_time: str | None = None
    # Расхождение book_time − first_seen_at в секундах: сырые данные, по
    # которым откалиброван MAX_ENTRY_DELTA_SECONDS (ADR 0005)
    entry_delta_sec: float | None = None
    exit_date: str
    exit_time: str
    hanger: int
    client: str = "—"
    profile: str = "—"
    profiles_info: list[ProfileInfo] = Field(default_factory=list)
    color: str = "—"
    lamels_qty: int | str = 0
    kpz_number: str = "—"
    material_type: str = "—"
    is_defect: bool = False
    # Forecast info - current bath and processing time
    current_bath: int | None = None  # Bath number 30-33 where hanger currently is
    bath_entry_time: str | None = None  # Time when hanger entered current bath (HH:MM:SS)
    bath_processing_time: int | None = None  # Expected processing time in seconds for current bath
    # Причина, по которой подбор неуверенный: см. app.services.matching
    time_warning_code: str | None = None
    time_warning: str | None = None  # Текст причины для тултипа


class DashboardResponse(BaseModel):
    """Response for dashboard API"""

    success: bool = True
    products: list[HangerData] = Field(default_factory=list)
    total: int = 0
    total_all: int = 0
    days_filter: int | None = None
    error: str | None = None


class FileStatus(BaseModel):
    """Excel file status"""

    is_open: bool = False
    last_modified: datetime | None = None
    file_name: str | None = None
    file_path: str | None = None
    status_text: str = "Неизвестно"
    error: str | None = None
    seconds_since_modified: float | None = None
    # Роль читаемой книги: main / reserve. None — режим запасной книги не
    # настроен либо активная книга вне ролей (старая запись выбора).
    role: str | None = None
    main_file_path: str | None = None
    reserve_file_path: str | None = None
    # Когда у основной книги последний раз прибавлялись строки: из этого
    # времени собирается текст «основная не пополняется с …».
    main_last_growth: datetime | None = None


class ExcelFileSelectRequest(BaseModel):
    """Request to select active Excel file"""

    file_path: str | None = None
    file_name: str | None = None


class ExcelBooksRequest(BaseModel):
    """Роли книг: какая основная, какая запасная.

    Пустая основная — это 400 «не указан путь», а не 422 от схемы: ошибку
    оператор читает на экране, и она должна объяснять, что не так с путём.
    Запасная не задана — режим выключен, читается только основная.
    """

    main_path: str | None = None
    reserve_path: str | None = None
