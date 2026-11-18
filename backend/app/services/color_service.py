"""Сервис справочника цветов.

Справочник — локальная копия операций анодирования KTM (спека 0003):
читается целиком и правится только по подписи. Строки сопоставляет и
перекрывает синк KTM, поэтому ``code``/``operation_code`` здесь не меняются.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Color
from app.db.session import get_session
from app.schemas.color import ColorResponse


class ColorService:
    """Чтение справочника и локальная правка названия/hex."""

    async def list_colors(self, session: AsyncSession | None = None) -> list[ColorResponse]:
        """Весь справочник: сначала по коду, затем по названию.

        Пустая таблица — пустой список: отсутствие цветов не ошибка, а
        состояние свежей базы до засева.
        """

        async def _list(sess: AsyncSession) -> list[ColorResponse]:
            result = await sess.execute(select(Color).order_by(Color.code, Color.name))
            return [ColorResponse.model_validate(color) for color in result.scalars().all()]

        if session:
            return await _list(session)
        async with get_session() as sess:
            return await _list(sess)

    async def update_color(
        self,
        color_id: int,
        name: str | None = None,
        abbreviation: str | None = None,
        hex_value: str | None = None,
        session: AsyncSession | None = None,
    ) -> ColorResponse | None:
        """Поправить подпись цвета и отметить правку локальной.

        Успешная правка всегда ставит ``updated_at`` в текущее UTC-время и
        ``source=local``: именно эти поля решают, чья правка победит при
        следующем синке. Ключи синхронизации не трогаются.
        """

        async def _update(sess: AsyncSession) -> ColorResponse | None:
            result = await sess.execute(select(Color).where(Color.id == color_id))
            color = result.scalar_one_or_none()
            if color is None:
                return None

            if name is not None:
                color.name = name
            if abbreviation is not None:
                color.abbreviation = abbreviation
            if hex_value is not None:
                color.hex = hex_value
            color.updated_at = datetime.now(UTC)
            color.source = "local"

            await sess.flush()
            await sess.refresh(color)
            return ColorResponse.model_validate(color)

        if session:
            return await _update(session)
        async with get_session() as sess:
            return await _update(sess)


color_service = ColorService()
