"""Засев справочника цветов: повторный запуск не плодит дублей.

Проверка идёт по ключу синка, а не по названию: администратор мог переименовать
строку, и второй засев не должен вставить её заново (упадёт на уникальном
``operation_code``).
"""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.color_seed import seed_missing_colors
from app.db.models import Color


def test_repeated_seed_after_local_rename_does_not_duplicate() -> None:
    engine = create_engine("sqlite://")
    Color.__table__.create(engine)

    with Session(engine) as session:
        assert seed_missing_colors(session.connection()) == 22
        session.commit()

        row = session.scalar(select(Color).where(Color.code == "C32"))
        assert row is not None
        row.name = "Моя тёмная шампань"
        row.abbreviation = "моя"
        session.commit()

        assert seed_missing_colors(session.connection()) == 0
        session.commit()

        assert session.query(Color).count() == 22
        renamed = session.scalar(select(Color).where(Color.code == "C32"))
        assert renamed is not None
        assert renamed.name == "Моя тёмная шампань"
        assert renamed.abbreviation == "моя"
