"""Pydantic-схемы справочника цветов (спека 0003, тикеты 0022 и 0023)."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# Канон hex — `#RRGGBB`: так его понимает ячейка панели и так он лежит в засеве.
HEX_PATTERN = r"^#[0-9A-Fa-f]{6}$"

ColorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ColorAbbreviation = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]


class ColorUpdate(BaseModel):
    """Локальная правка цвета: подпись, название и hex.

    ``code`` и ``operation_code`` — ключи синхронизации, а не подпись, поэтому
    в теле запроса их нет. Пустой запрос — 422: PATCH без изменений не должен
    двигать ``updated_at`` и побеждать в «новее — правильнее».
    """

    name: ColorName | None = Field(default=None, description="Название покрытия")
    abbreviation: ColorAbbreviation | None = Field(default=None, description="Привычная подпись в ячейке")
    hex: str | None = Field(default=None, pattern=HEX_PATTERN, description="Цвет в формате #RRGGBB")

    @model_validator(mode="after")
    def _require_change(self) -> "ColorUpdate":
        if not self.model_fields_set:
            raise ValueError("нужно передать name, abbreviation или hex")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} не может быть пустым")
        return self


class ColorResponse(BaseModel):
    """Строка справочника для клиента: без служебных полей БД (``created_at``)."""

    id: int
    code: str | None = Field(description="Отображаемый код; у старых названий его нет")
    name: str
    hex: str
    abbreviation: str | None = Field(default=None, description="Привычная подпись в ячейке")
    operation_code: str | None = Field(description="Ключ синка с KTM")
    source: Literal["ktm", "local"] = Field(description="Чья правка последняя")
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("updated_at", mode="after")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        """SQLite не хранит зону: наивное время из базы трактуем как UTC."""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
