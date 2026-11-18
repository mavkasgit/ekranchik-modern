"""API справочника цветов (спека 0003, тикеты 0022 и 0023).

Цвета принадлежат KTM, а Экранчик хранит их локальную копию: маршруты читают
справочник и правят только подпись. Создания и удаления здесь нет — список
пополняется засевом и синком.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.color import ColorResponse, ColorUpdate
from app.services.color_service import color_service

router = APIRouter(prefix="/colors", tags=["colors"])


@router.get("", response_model=list[ColorResponse])
async def list_colors():
    """Весь справочник цветов в стабильном порядке: код, затем название."""
    return await color_service.list_colors()


@router.patch("/{color_id}", response_model=ColorResponse)
async def update_color(color_id: int, data: ColorUpdate):
    """Поправить название, подпись или hex; ``code`` и ``operation_code`` не меняются."""
    color = await color_service.update_color(
        color_id, name=data.name, abbreviation=data.abbreviation, hex_value=data.hex
    )
    if color is None:
        raise HTTPException(status_code=404, detail="Color not found")
    return color
