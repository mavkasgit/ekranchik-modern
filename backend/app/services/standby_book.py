"""Запасная книга учёта: дашборд сам выбирает книгу, в которой идёт работа.

Сценарий, ради которого это существует: книгу открыли на другом компьютере и
сохранение с машины оператора заблокировалось. Автосохранение продолжает
писать оба файла, поэтому **время сохранения ничего не различает** — у
основной книги mtime тоже идёт. Различает только наполненность: в основной
строки перестают прибавляться, в запасной растут, потому что работать
оператор пошёл в неё.

Правило (ADR 0009):

* читаем основную, пока в ней растут строки с реальными данными;
* переходим на запасную, когда основная не растёт 30 минут, а запасная за это
  время росла и обошла её по числу строк;
* возвращаемся на основную на первом же росте её строк: основная книга
  первична, и «ложный» возврат чинится следующим переключением;
* основная пропала/не читается — переходим сразу, это отказ, а не заморозка.

Решение принимается по числу непустых строк с датой или номером подвеса —
тех же строк, что видны на дашборде. Размер файла в решении не участвует:
сохранение переписывает файл целиком и меняет размер, даже когда новых строк
в книге нет.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from app.services.excel_service import excel_service, path_exists

logger = logging.getLogger(__name__)

# Как часто сравниваем книги. 30 секунд — тот же ритм, что у автобэкапа:
# решение не срочное (порог — полчаса), а чтение шары лишними опросами не
# поощряется.
CHECK_SECONDS = 30
# Сколько основная книга должна не пополняться, прежде чем поверить запасной.
# Совпадает с предупреждением дашборда «файл не сохранялся более 30 минут».
FROZEN_SECONDS = 30 * 60


class Role(StrEnum):
    """Роль книги: основная — первичная, запасная — на случай отказа."""

    MAIN = "main"
    RESERVE = "reserve"


@dataclass(frozen=True)
class BookSample:
    """Замер книги: дошла ли она до нас и сколько в ней строк с данными.

    ``present`` — файл существует. ``rows`` — число строк либо ``None``, если
    прочитать не удалось (книга ещё записывается). Это разные вещи: пропавшая
    книга — отказ, нечитаемая на секунду — повод подождать, а не уезжать на
    запасную и тут же возвращаться.
    """

    path: Path | None
    present: bool
    rows: int | None

    @property
    def available(self) -> bool:
        return self.present and self.rows is not None


@dataclass(frozen=True)
class Switch:
    """Решение фоновой задачи перейти на другую книгу."""

    role: Role
    reason: str


def decide(
    active: Role,
    main: BookSample,
    reserve: BookSample,
    *,
    main_grew: bool,
    main_grown_at: float,
    reserve_grown_at: float | None,
    now: float,
    frozen_seconds: float = FROZEN_SECONDS,
) -> Role | None:
    """На какую книгу перейти: ответ правила, без чтения файлов.

    ``None`` — остаёмся на текущей. Порядок проверок — это таблица спеки
    0001: пропавшая запасная выключает режим, рост основной при чтении
    запасной возвращает на неё, пропавшая основная уводит сразу, нечитаемая
    книга — повод ждать, а не уезжать. Переключение на запасную требует
    заморозки основной и того, что запасная росла и обошла её по строкам.

    Время роста передаётся монотонным (``time.monotonic``), а не календарным:
    перевод часов не должен превращать «полчаса» в «сутки».
    ``main_grown_at`` — последний рост основной (для не росшей при нас книги —
    начало наблюдения), ``reserve_grown_at`` — её рост либо ``None``, если она
    ещё ни разу не росла при нас.
    """
    # Запасная пропала: режим выключается, читаем основную — но только если
    # она действительно читается. Иначе остаёмся где есть.
    if not reserve.present:
        if active is Role.RESERVE and main.available:
            return Role.MAIN
        return None

    # Сейчас читаем запасную: любой рост основной возвращает работу в неё.
    if active is Role.RESERVE:
        return Role.MAIN if main_grew else None

    # Основная пропала — отказ, а не заморозка: уходим без ожидания.
    if not main.present:
        return Role.RESERVE if reserve.available else None

    # Книга есть, но прямо сейчас не читается (сохраняется), либо не читается
    # запасная: уезжать некуда и незачем — через секунду книга снова доступна
    # со старым числом строк, и решение принимать рано.
    if not main.available or not reserve.available:
        return None

    # Основная не пополняется полчаса, запасная за это время росла и обошла
    # её по строкам: работа идёт в запасной.
    frozen = now - main_grown_at >= frozen_seconds
    reserve_recent = reserve_grown_at is not None and now - reserve_grown_at <= frozen_seconds
    if frozen and reserve_recent and reserve.rows > main.rows:
        return Role.RESERVE
    return None


class StandbyBook:
    """Фоновая задача: замерять обе книги и переключать активную.

    Память между замерами живёт здесь: когда книга последний раз прибавляла
    строки. Перезапуск сервера её обнуляет, поэтому после рестарта правило
    снова ждёт 30 минут наблюдения — так лучше, чем принять решение по
    догадке о том, что было до перезапуска.
    """

    def __init__(self) -> None:
        self._rows: dict[Role, int | None] = {Role.MAIN: None, Role.RESERVE: None}
        # Дошла ли книга до нас на последнем замере: False — файла нет,
        # None — замера ещё не было.
        self._present: dict[Role, bool | None] = {Role.MAIN: None, Role.RESERVE: None}
        # Начало наблюдения за книгой. От него считается «основная не растёт N
        # минут» у книги, которая ещё ни разу не росла при нас: иначе после
        # рестарта отсчёт пошёл бы от вечности и переключение случилось бы на
        # первом же замере.
        self._first_seen: dict[Role, float] = {}
        # Момент настоящего роста: только он делает запасную «растущей».
        self._grown_at: dict[Role, float] = {}
        self._grown_wall: dict[Role, datetime | None] = {Role.MAIN: None, Role.RESERVE: None}
        # Когда служба впервые посмотрела на книги: до этого момента статистика
        # пустая, и «не растёт 30 минут» ещё не о чем говорить.
        self._observed_wall: datetime | None = None

    def reset(self) -> None:
        """Забыть замеры: сменились роли или книга подменена в тестах."""
        self._rows = {Role.MAIN: None, Role.RESERVE: None}
        self._present = {Role.MAIN: None, Role.RESERVE: None}
        self._first_seen = {}
        self._grown_at = {}
        self._grown_wall = {Role.MAIN: None, Role.RESERVE: None}
        self._observed_wall = None

    def main_last_growth(self) -> datetime | None:
        """Когда у основной книги последний раз прибавлялись строки."""
        return self._grown_wall[Role.MAIN]

    def _minutes_without_growth(self, role: Role, now: float) -> int | None:
        """Сколько минут книга не прибавляла строк (от начала наблюдения)."""
        grown = self._grown_at.get(role)
        if grown is None:
            started = self._first_seen.get(role)
            return None if started is None else int((now - started) / 60)
        return int((now - grown) / 60)

    def reason(self, now: float | None = None) -> str:
        """Почему читается именно эта книга — одной строкой для экрана.

        Считается из тех же замеров, что и решение, поэтому объяснение не
        расходится с фактическим поведением. Формулировки короткие: их место —
        в модалке книг, а не в логе.
        """
        now = time.monotonic() if now is None else now
        if excel_service.reserve_path is None:
            return "запасная не задана — читается только основная"
        if self._observed_wall is None:
            return "первый замер ещё не выполнен"

        main_present = self._present[Role.MAIN]
        reserve_present = self._present[Role.RESERVE]
        main_rows = self._rows[Role.MAIN]
        reserve_rows = self._rows[Role.RESERVE]
        active = self._active_role()

        if main_present is False:
            return "основная книга не найдена — читается запасная"
        if main_rows is None:
            return "основная книга ещё не прочитана"
        if reserve_present is False:
            return "запасная книга не найдена — читается основная"
        if reserve_rows is None:
            return "запасная книга ещё не прочитана"
        if active is Role.RESERVE:
            minutes = self._minutes_without_growth(Role.MAIN, now)
            suffix = f" {minutes} мин" if minutes is not None else " уже 30+ мин"
            return f"работа идёт в запасной: основная не пополняется{suffix}"

        main_grown = self._grown_at.get(Role.MAIN)
        if main_grown is None:
            return "основная ещё не пополнялась при наблюдении — читается она"
        minutes = self._minutes_without_growth(Role.MAIN, now)
        if minutes is None or minutes < int(FROZEN_SECONDS / 60):
            return f"основная пополняется (последний рост {minutes or 0} мин назад) — читается она"

        reserve_grown = self._grown_at.get(Role.RESERVE)
        reserve_recent = reserve_grown is not None and now - reserve_grown <= FROZEN_SECONDS
        if not reserve_recent:
            return f"основная не растёт {minutes} мин, запасная тоже — перехода нет"
        if reserve_rows <= main_rows:
            return "запасная растёт, но строк не больше — перехода нет"
        return "запасная обошла основную — переход на следующем замере"

    def status(self, now: float | None = None) -> dict[str, object]:
        """Статистика обеих книг для строки статуса и модалки."""
        return {
            "main_rows": self._rows[Role.MAIN],
            "reserve_rows": self._rows[Role.RESERVE],
            "main_last_growth": self._grown_wall[Role.MAIN],
            "reserve_last_growth": self._grown_wall[Role.RESERVE],
            "main_present": self._present[Role.MAIN],
            "reserve_present": self._present[Role.RESERVE],
            "observed_since": self._observed_wall,
            "reason": self.reason(now),
        }

    def _observe(self, role: Role, sample: BookSample, now: float) -> bool:
        """Запомнить замер и ответить, выросла ли книга с прошлого раза.

        Нечитаемый замер не стирает прежнее число строк: иначе каждый сбой
        чтения выглядел бы как «книга опустела» и менял бы решение.
        """
        if not sample.available:
            return False

        previous = self._rows[role]
        if previous is None:
            self._rows[role] = sample.rows
            # Первый замер — начало наблюдения, а не рост. Считать его ростом
            # значило бы, что запасная «росла» просто потому, что её впервые
            # увидели, и через полчаса она забрала бы чтение без работы в ней.
            self._first_seen.setdefault(role, now)
            return False

        if sample.rows > previous:
            self._rows[role] = sample.rows
            self._grown_at[role] = now
            self._grown_wall[role] = datetime.now().astimezone()
            return True

        # Строки могли и убрать: это не рост, но и не повод считать книгу живой.
        self._rows[role] = sample.rows
        return False

    def _sample(self, path: Path | None) -> BookSample:
        if path is None:
            return BookSample(path=None, present=False, rows=None)
        present = path_exists(path)
        return BookSample(path=path, present=present, rows=excel_service.count_book_rows(path) if present else None)

    def _active_role(self) -> Role:
        role = excel_service.current_role
        return Role(role) if role else Role.MAIN

    def tick(self, now: float | None = None) -> Switch | None:
        """Один замер: переключить активную книгу, если правило велит.

        Синхронный: ``stat`` и разбор книги идут по сетевой шаре, поэтому
        вызывающий обязан уводить это в поток.
        """
        now = time.monotonic() if now is None else now

        main = self._sample(excel_service.main_path)
        reserve = self._sample(excel_service.reserve_path)
        if self._observed_wall is None:
            self._observed_wall = datetime.now().astimezone()
        self._present[Role.MAIN] = main.present
        self._present[Role.RESERVE] = reserve.present
        main_grew = self._observe(Role.MAIN, main, now)
        self._observe(Role.RESERVE, reserve, now)

        # Выбор вне ролей (старая запись, ручная подмена): привести к основной,
        # но только когда основная читается, — иначе некуда вести.
        active = self._active_role()
        if excel_service.current_role is None and main.available and excel_service.main_path is not None:
            excel_service.set_active_file(str(excel_service.main_path))
            active = Role.MAIN

        target = decide(
            active,
            main,
            reserve,
            main_grew=main_grew,
            main_grown_at=self._grown_at.get(Role.MAIN, self._first_seen.get(Role.MAIN, now)),
            reserve_grown_at=self._grown_at.get(Role.RESERVE),
            now=now,
        )
        if target is None or target is active:
            return None

        path = excel_service.main_path if target is Role.MAIN else excel_service.reserve_path
        if path is None:
            return None

        excel_service.set_active_file(str(path))
        reason = (
            f"основная книга не пополняется {int(FROZEN_SECONDS / 60)} минут, "
            f"в запасной {self._rows[Role.RESERVE]} строк"
            if target is Role.RESERVE
            else "в основной книге снова растут строки"
        )
        logger.warning(f"[StandbyBook] Чтение переключено на {target.value}: {reason}")
        return Switch(role=target, reason=reason)

    async def _announce(self, switch: Switch) -> None:
        """Сообщить открытым экранам, что читается другая книга."""
        try:
            from app.schemas.websocket import WebSocketMessage
            from app.services.websocket_manager import websocket_manager

            path = excel_service.current_path
            await websocket_manager.broadcast(
                WebSocketMessage(
                    type="data_update",
                    payload={
                        "source": "excel",
                        "role": switch.role.value,
                        "file": path.name if path else None,
                        "file_path": str(path) if path else None,
                        "message": f"Книга учёта: {switch.reason}",
                    },
                    timestamp=datetime.now(),
                )
            )
        except Exception as error:
            logger.warning(f"[StandbyBook] Не удалось разослать переключение книги: {error}")

    async def run_forever(self) -> None:
        """Просыпаться каждые ``CHECK_SECONDS`` и проверять обе книги."""
        while True:
            try:
                switch = await asyncio.to_thread(self.tick)
                if switch is not None:
                    await self._announce(switch)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(f"[StandbyBook] Задача переключения книги упала: {error}", exc_info=True)
            await asyncio.sleep(CHECK_SECONDS)


# Синглтон для main.py, роутов и тестов.
standby_book = StandbyBook()
