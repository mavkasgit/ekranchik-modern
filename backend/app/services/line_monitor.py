"""
Line Monitor Service - unified OPC UA monitoring for production line.
Combines hanger tracking, unload detection, and real-time polling.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque

from app.services.opcua_service import opcua_service
from app.services.websocket_manager import websocket_manager
from app.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)

# --- Constants ---
CONTROL_BATH = 34  # Unload point bath number
HANGER_TTL = timedelta(minutes=30)  # Time to keep inactive hanger data before cleanup
CLEANUP_INTERVAL = timedelta(minutes=5)  # How often to run the cleanup task
MAX_HANGERS = 500  # Максимум отслеживаемых подвесов
MAX_PATH_LENGTH = 100  # Максимум записей в пути подвеса
MAX_UNLOAD_EVENTS = 500  # Максимум событий выгрузки в памяти
# Между ваннами подвес не виден ни в одной, и на этой линии переход
# занимает минуты. Порог «не видно N секунд → сошёл с линии» берём из PLC:
# максимальное dTime по линии (остаток обработки самой долгой ванны) плюс
# запас на переход. На 29.09.2026 max dTime был 2200 с (ванна 31), то есть
# граница ~42 мин вместо прежних 5 с.
DEFAULT_MAX_BATH_SECONDS = 600  # Подстановка, пока PLC не отдал ни одного dTime
DEPARTURE_MARGIN_SECONDS = 300  # Запас сверх самой долгой ванны
DEPARTURE_BOUND_REFRESH = 60  # Как часто пересчитывать границу, секунд


# --- Data Classes ---
@dataclass
class HangerPathEntry:
    """Represents a hanger's time in a single bath."""
    bath_name: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    duration: Optional[float] = None  # in seconds


@dataclass
class HangerState:
    """Текущее состояние подвеса и его открытого прохода по линии.

    Один ``HangerState`` переживает несколько проходов: номера подвесов
    повторяются от смены к смене. Поля ``cycle_id``, ``first_seen_at``,
    ``entry_bath`` и ``path`` относятся ТОЛЬКО к текущему проходу и
    обнуляются при каждом новом (см. ``_open_cycle``).

    ``first_seen_at`` — момент, когда монитор впервые увидел подвес в
    ЛЮБОЙ ванне этого прохода, а не доказанный физический вход в линию.
    ``entry_bath`` — ванна, в которой он появился; нужна, чтобы измерить
    систематическое смещение относительно времени в книге учёта.

    ``unseen_since`` — с какого момента подвес не виден ни в одной ванне.
    Короткий разрыв между ваннами НЕ прерывает проход: ``current_bath``
    продолжает хранить последнюю известную ванну, а ``cycle_id`` — прежний.
    """
    id: int
    current_bath: Optional[str] = None
    entry_time: Optional[datetime] = None
    last_seen: datetime = field(default_factory=datetime.now)
    path: List[HangerPathEntry] = field(default_factory=list)
    cycle_id: Optional[int] = None
    first_seen_at: Optional[datetime] = None
    entry_bath: Optional[int] = None
    unseen_since: Optional[datetime] = None


class LineMonitorService:
    """
    Unified service for monitoring production line via OPC UA.
    - Tracks hangers through baths, handling cyclical hanger numbers.
    - Detects unload events at the control bath.
    - Broadcasts real-time updates via WebSocket.
    - Cleans up stale hanger data to prevent memory leaks.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 1  # seconds - обновление каждую секунду
        self._heartbeat_interval = 2  # seconds - отправка статуса на фронтенд каждые 2 секунды
        self._health_check_interval = 30  # seconds - проверка здоровья OPC UA соединения
        self._last_heartbeat = datetime.now()
        self._last_health_check = datetime.now()
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # После этого делаем полный reconnect
        
        # State tracking
        self._hangers: Dict[int, HangerState] = {}
        self._bath34_pallete: Optional[int] = None
        # Идентификатор физического прохода подвеса по линии. Монотонный и
        # никогда не переиспользуется, поэтому остаётся уникальным и после
        # clear_data — события у клиентов переживают сброс.
        self._cycle_counter = 0
        # Ключи уже обработанных проходов: cycle_id для нормального выхода и
        # (номер, минута) для аварийного, у которого цикла нет.
        self._processed_unloads: Deque[object] = deque(maxlen=1000)
        self._last_cleanup_time = datetime.now()

        # Граница «подвес сошёл с линии». Считается по dTime ванн (остаток
        # обработки) и кэшируется: дергать 39 узлов раз в секунду незачем.
        self._departure_bound = timedelta(
            seconds=DEFAULT_MAX_BATH_SECONDS + DEPARTURE_MARGIN_SECONDS
        )
        self._last_bound_refresh = datetime.now()

        # Unload events cache (deque для O(1) операций)
        self._unload_events: deque = deque(maxlen=MAX_UNLOAD_EVENTS)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def start(self) -> bool:
        """Start the line monitoring loop."""
        if self._running:
            logger.warning("[Line Monitor] Already running")
            return False
        
        # Регистрируем все узлы для опроса в OPC UA сервисе
        self._register_monitored_nodes()
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[Line Monitor] Started")
        return True
    
    def _register_monitored_nodes(self) -> None:
        """
        Регистрирует все необходимые OPC UA узлы для постоянного опроса.
        Это "герметизирует" список — только эти узлы будут опрашиваться.
        """
        node_ids = []
        
        # Узлы для всех 39 ванн
        bath_props = ["InUse", "Free", "Pallete", "InTime", "OutTime", "dTime"]
        for bath_num in range(1, 40):
            for prop in bath_props:
                node_ids.append(f"ns=4;s=Bath[{bath_num}].{prop}")
        
        # Узлы блока питания
        power_props = ["Current", "Voltage", "Status"]
        for prop in power_props:
            node_ids.append(f"ns=4;s=S8VK_X.{prop}")
        
        # Системные узлы
        node_ids.append("i=2258")  # Server CurrentTime
        
        # Регистрируем в OPC UA сервисе
        opcua_service.register_nodes(node_ids)
        logger.info(f"[Line Monitor] Registered {len(node_ids)} nodes for OPC UA polling")
    
    async def stop(self) -> None:
        """Stop the line monitoring loop."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("[Line Monitor] Stopped")
    
    def clear_data(self) -> None:
        """Очистить все данные мониторинга (подвесы, события)."""
        self._hangers.clear()
        self._bath34_pallete = None
        self._processed_unloads.clear()
        self._unload_events.clear()
        logger.info("[Line Monitor] All data cleared")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.info(f"[Line Monitor] Loop started, interval: {self._poll_interval}s")
        
        while self._running:
            try:
                await self._poll_once()
                
                # Сбрасываем счётчик ошибок при успешном опросе
                self._consecutive_errors = 0

                # Периодический heartbeat для фронтенда
                now = datetime.now()
                if (now - self._last_heartbeat).total_seconds() >= self._heartbeat_interval:
                    asyncio.create_task(self._send_heartbeat()) # Запускаем как фоновую задачу
                    self._last_heartbeat = now
                
                # Периодическая проверка здоровья OPC UA соединения
                if (now - self._last_health_check).total_seconds() >= self._health_check_interval:
                    health_ok = await opcua_service.ensure_connected()
                    if not health_ok:
                        logger.warning("[Line Monitor] OPC UA health check failed")
                    self._last_health_check = now
                
                # Периодический flush батча ошибок OPC UA
                await opcua_service._flush_error_batch()

                # Periodically clean up old hangers
                if now - self._last_cleanup_time > CLEANUP_INTERVAL:
                    await self._cleanup_hangers()
                    self._last_cleanup_time = now

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"[Line Monitor] Error in monitor loop ({self._consecutive_errors}): {e}", exc_info=True)
                
                # При множественных ошибках - принудительный reconnect
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.warning("[Line Monitor] Too many errors, forcing OPC UA reconnect")
                    await opcua_service.disconnect()
                    self._consecutive_errors = 0
                    await self._broadcast_connection_status(False)
            
            await asyncio.sleep(self._poll_interval)
    
    async def _send_heartbeat(self) -> None:
        """Send heartbeat with current status and line data to all clients."""
        try:
            active_hangers = self.get_active_hangers()
            
            # Собираем данные о ваннах для визуализации
            baths_data = []
            for bath_num in range(1, 40):
                in_use = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].InUse")
                pallete = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].Pallete")
                in_time = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].InTime")
                out_time = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].OutTime")
                
                baths_data.append({
                    "bath_number": bath_num,
                    "in_use": bool(in_use) if in_use is not None else False,
                    "pallete": int(pallete) if pallete else 0,
                    "in_time": float(in_time) if in_time else 0,
                    "out_time": float(out_time) if out_time else 0,
                })
            
            heartbeat = WebSocketMessage(
                type="line_update",
                payload={
                    "opcua_connected": opcua_service.is_connected,
                    "opcua_state": opcua_service.state.value,
                    "active_hangers": len(active_hangers),
                    "total_tracked": len(self._hangers),
                    "recent_unloads": len(self._unload_events),
                    "stats": opcua_service.stats,
                    "baths": baths_data,
                    "timestamp": datetime.now().isoformat(),
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(heartbeat)
        except Exception as e:
            logger.error(f"[Line Monitor] Heartbeat error: {e}")
    
    async def _poll_once(self) -> None:
        """Single poll cycle: scan baths and detect events."""
        # Ensure OPC UA connection with health check
        connected = await opcua_service.ensure_connected()
        if not connected:
            logger.warning("[Line Monitor] Cannot connect to OPC UA. Skipping poll.")
            # Отправляем статус отключения на фронтенд
            await self._broadcast_connection_status(False)
            return
        
        # Если только что переподключились - уведомляем фронтенд
        if not opcua_service.is_connected:
            await self._broadcast_connection_status(False)
            return
        
        # ВАЖНО: Сначала проверяем выгрузку (ванна 34), потом сканируем остальные
        # Это гарантирует что выгрузка будет зафиксирована до того как
        # _scan_baths() создаст "новый цикл" для подвеса
        await self._check_unload()
        
        # Scan all baths to update hanger states
        await self._scan_baths()
    
    async def _broadcast_connection_status(self, connected: bool) -> None:
        """Broadcast OPC UA connection status to all clients."""
        try:
            status_message = WebSocketMessage(
                type="opcua_status",
                payload={
                    "connected": connected,
                    "state": opcua_service.state.value,
                    "stats": opcua_service.stats,
                },
                timestamp=datetime.now()
            )
            await websocket_manager.broadcast(status_message)
        except Exception as e:
            logger.error(f"[Line Monitor] Failed to broadcast status: {e}")

    async def _cleanup_hangers(self) -> None:
        """Remove hanger data that has been inactive for too long."""
        now = datetime.now()
        
        # 1. Удаляем неактивные подвесы по TTL
        inactive_hangers = [
            hanger_id
            for hanger_id, state in self._hangers.items()
            if state.current_bath is None and (now - state.last_seen) > HANGER_TTL
        ]
        
        if inactive_hangers:
            for hanger_id in inactive_hangers:
                del self._hangers[hanger_id]
            logger.info(f"[Line Monitor] Cleaned up {len(inactive_hangers)} inactive hangers.")
        
        # 2. Защита от переполнения: если слишком много подвесов, удаляем самые старые
        if len(self._hangers) > MAX_HANGERS:
            # Сортируем по last_seen, удаляем самые старые
            sorted_hangers = sorted(
                self._hangers.items(),
                key=lambda x: x[1].last_seen
            )
            to_remove = len(self._hangers) - MAX_HANGERS
            for hanger_id, _ in sorted_hangers[:to_remove]:
                del self._hangers[hanger_id]
            logger.warning(f"[Line Monitor] Force-cleaned {to_remove} oldest hangers (overflow protection)")

    def _open_cycle(
        self, hanger: HangerState, bath_num: int, now: datetime
    ) -> None:
        """Открыть новый физический проход подвеса по линии.

        Вызывается только когда открытого прохода действительно нет: подвес
        увиден впервые либо вернулся на линию после закрытого прохода.
        Простое исчезновение из ванн проход не закрывает — иначе переход
        между ваннами рвал бы его на куски (см. ``_departure_bound``).
        Всё, что относится к прошлому проходу, отбрасывается — накопленный
        path в том числе.
        """
        self._cycle_counter += 1
        hanger.cycle_id = self._cycle_counter
        hanger.first_seen_at = now
        hanger.entry_bath = bath_num
        hanger.path = []
        hanger.unseen_since = None

    def _close_cycle(self, hanger: HangerState, reason: str) -> None:
        """Закрыть проход, не дожидаясь выгрузки с 34-й ванны."""
        logger.warning(
            f"[Line Monitor] Hanger {hanger.id} cycle {hanger.cycle_id} "
            f"closed ({reason}): unseen for "
            f"{(datetime.now() - hanger.last_seen).total_seconds():.0f}s, "
            f"last bath {hanger.current_bath}."
        )
        hanger.cycle_id = None
        hanger.current_bath = None
        hanger.entry_time = None
        hanger.unseen_since = None

    def _refresh_departure_bound(self) -> None:
        """Пересчитать границу «сошёл с линии» по dTime ванн.

        dTime — остаток обработки ванны в секундах, то есть верхняя оценка
        того, сколько подвес может в ней простоять. Максимум по линии плюс
        запас на переход между ваннами и даёт границу невидимости. Ноль и
        мусор (у счётчика ванны, перешедшего сутки, dTime уходит в минус)
        игнорируются, а при пустом чтении держится предыдущее значение —
        иначе кратковременный сбой PLC обнулил бы границу.
        """
        longest = 0
        for bath_num in range(1, 40):
            raw = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].dTime")
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value > longest:
                longest = value

        if longest <= 0:
            return  # PLC молчит — держим предыдущую границу

        bound = timedelta(seconds=longest + DEPARTURE_MARGIN_SECONDS)
        if bound != self._departure_bound:
            logger.info(
                f"[Line Monitor] Departure bound: longest bath dTime "
                f"{longest:.0f}s + {DEPARTURE_MARGIN_SECONDS}s margin "
                f"= {bound.total_seconds():.0f}s"
            )
            self._departure_bound = bound
        self._last_bound_refresh = datetime.now()

    def cycle_snapshot(self, hanger: HangerState) -> Dict:
        """Общее представление прохода для события выгрузки и /line/cycles."""
        return {
            "cycle_id": hanger.cycle_id,
            "hanger": hanger.id,
            "first_seen_at": hanger.first_seen_at.isoformat()
            if hanger.first_seen_at
            else None,
            "entry_bath": hanger.entry_bath,
            "baths_visited": [e.bath_name for e in hanger.path],
        }

    async def _scan_baths(self) -> None:
        """Scan all baths and update hanger positions, handling new cycles."""
        now = datetime.now()
        
        # Keep track of all hangers seen in this scan cycle
        hangers_seen_in_scan = set()

        for bath_num in range(1, 40):
            bath_name = str(bath_num)
            try:
                # ВАЖНО: Читаем из кэша, а не напрямую из OPC UA!
                in_use = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].InUse")
                if not in_use:
                    continue
                
                pallete = opcua_service.get_value(f"ns=4;s=Bath[{bath_num}].Pallete")
                if not pallete or pallete == 0:
                    continue

                hanger_id = int(pallete)
                hangers_seen_in_scan.add(hanger_id)
                hanger_state = self._hangers.get(hanger_id)

                # --- Cycle lifetime ---
                # Проход открыт, если подвес на линии и проход не закрыт.
                # current_bath обнуляется только выгрузкой или уходом с
                # линии (см. ``_close_cycle``), поэтому None — это однозначно
                # «подвес не на линии», и новый проход начинается именно там.
                # Переход между ваннами current_bath не трогает, поэтому
                # проход на нём не рвётся.
                opened = False
                if not hanger_state:
                    hanger_state = HangerState(id=hanger_id)
                    self._hangers[hanger_id] = hanger_state
                    self._open_cycle(hanger_state, bath_num, now)
                    opened = True
                elif hanger_state.current_bath is None:
                    # Подвес, только что выгруженный, ещё стоит в 34-й ванне:
                    # выгрузка срабатывает по ПРИХОДУ в неё. Это то же самое
                    # присутствие, а не новый проход, иначе на каждый выход
                    # заводился бы фантомный проход с нулём на линии.
                    if bath_num != CONTROL_BATH:
                        self._open_cycle(hanger_state, bath_num, now)
                        opened = True
                else:
                    hanger_state.unseen_since = None

                if opened:
                    logger.info(
                        f"Hanger {hanger_id} cycle {hanger_state.cycle_id} opened: "
                        f"first seen at bath {hanger_state.entry_bath}."
                    )

                # --- State Update ---
                # If hanger moved to a new bath
                if hanger_state.current_bath != bath_name:
                    # Finalize the previous step if it exists
                    if hanger_state.current_bath is not None and hanger_state.entry_time is not None:
                        duration = (now - hanger_state.entry_time).total_seconds()
                        hanger_state.path.append(
                            HangerPathEntry(
                                bath_name=hanger_state.current_bath,
                                entry_time=hanger_state.entry_time,
                                exit_time=now,
                                duration=duration,
                            )
                        )
                        # Защита от переполнения path
                        if len(hanger_state.path) > MAX_PATH_LENGTH:
                            hanger_state.path = hanger_state.path[-MAX_PATH_LENGTH:]
                    # Record entry into the new bath
                    hanger_state.current_bath = bath_name
                    hanger_state.entry_time = now

                # Always update the last_seen timestamp for any active hanger
                hanger_state.last_seen = now

            except Exception as e:
                logger.error(f"[Line Monitor] Error scanning bath {bath_name}: {e}")

        # --- Hangers no longer visible in ANY bath ---
        # Между ваннами подвес не виден ни в одной — это нормальный переход,
        # а не уход с линии. Проход закрываем только когда невидимость
        # превысила границу, посчитанную по dTime ванн (см.
        # ``_refresh_departure_bound``). Прежние 5 секунд на этой линии
        # срабатывали на каждом переходе и рвали проход.
        if now - self._last_bound_refresh > timedelta(
            seconds=DEPARTURE_BOUND_REFRESH
        ):
            self._refresh_departure_bound()

        for hanger_id, state in list(self._hangers.items()):
            if state.cycle_id is None:
                continue  # Прохода нет — подвес уже вне линии
            if hanger_id in hangers_seen_in_scan:
                continue  # Виден в текущем скане
            if state.unseen_since is None:
                state.unseen_since = now
            if now - state.unseen_since > self._departure_bound:
                self._close_cycle(state, "left the line")

    async def _check_unload(self) -> None:
        """Check Bath[34] for unload events."""
        try:
            # ВАЖНО: Читаем из кэша, а не напрямую из OPC UA!
            pallete = opcua_service.get_value(f"ns=4;s=Bath[{CONTROL_BATH}].Pallete")
            current_pallete = int(pallete) if pallete and pallete > 0 else 0
            
            # First poll - just initialize
            if self._bath34_pallete is None:
                self._bath34_pallete = current_pallete
                return
            
            # Detect entry: 0 -> N (hanger enters unload position)
            if self._bath34_pallete == 0 and current_pallete > 0:
                await self._record_unload(current_pallete)
            
            self._bath34_pallete = current_pallete
        
        except Exception as e:
            logger.error(f"[Line Monitor] Unload check error: {e}", exc_info=True)
    
    async def _record_unload(self, hanger_id: int) -> None:
        """Зафиксировать выгрузку подвеса и разослать событие.

        Выгрузка привязывается к физическому проходу (``cycle_id``), а не к
        номеру подвеса: один и тот же номер выходит с линии столько раз,
        сколько его прогоняют за смену. Дедупликация — по ``cycle_id``,
        поэтому два выхода одного номера в пределах одной минуты — это два
        разных события, а повторная обработка одного прохода отсекается.
        """
        try:
            now = datetime.now()
            hanger = self._hangers.get(hanger_id)

            # Прохода нет — состояние потеряно (рестарт сервера, давний
            # простой, вытеснение при переполнении). Это ошибка монитора, и
            # она НЕ должна выглядеть как нормальный выход с
            # total_time_sec = 0. cycle_id задним числом не создаём.
            #
            # Важно: судим по cycle_id, а НЕ по current_bath. Подвес,
            # который минуту назад переходил между ваннами, не виден ни в
            # одной, но его проход цел. Прежняя проверка current_bath
            # выбрасывала такие проходы в CYCLE_ERROR, и вся таблица выхода
            # оставалась пустой.
            if hanger is None or hanger.cycle_id is None:
                # Дедупликация по (номер, минута): цикла, к которому можно
                # было бы привязаться, здесь нет, а дрожание датчика 0→N
                # иначе даёт неограниченный поток одинаковых cycle_error.
                error_key = (hanger_id, now.strftime('%Y%m%d_%H%M'))
                if error_key in self._processed_unloads:
                    return
                self._processed_unloads.append(error_key)
                reason = "unload_without_open_cycle"
                logger.error(
                    f"[Line Monitor] {reason}: hanger {hanger_id} "
                    f"(state={'missing' if hanger is None else 'no_cycle'}, "
                    f"cycle={hanger.cycle_id if hanger else None})"
                )
                await self._publish(
                    {
                        "type": "cycle_error",
                        "reason": reason,
                        "cycle_id": None,
                        "hanger": hanger_id,
                        "first_seen_at": None,
                        "entry_bath": None,
                        "exit_at": now.isoformat(),
                        "total_time_sec": None,
                        "baths_visited": None,
                        "time": now.strftime("%H:%M:%S"),
                        "date": now.strftime("%d.%m.%Y"),
                        "timestamp": now.isoformat(),
                    },
                    now,
                    hanger_id,
                )
                return

            if hanger.cycle_id in self._processed_unloads:
                return
            self._processed_unloads.append(hanger.cycle_id)

            # Замыкаем последний шаг — ванну выгрузки. current_bath здесь
            # может быть последней известной ванной перехода, а не 34-й:
            # подвес выгружается по факту появления в 34-й, но скан успевает
            # не увидеть его в ванне. Номер 34 в этом случае врёт, поэтому
            # оставляем фактически известную ванну.
            if hanger.entry_time:
                hanger.path.append(
                    HangerPathEntry(
                        bath_name=hanger.current_bath or str(CONTROL_BATH),
                        entry_time=hanger.entry_time,
                        exit_time=now,
                        duration=(now - hanger.entry_time).total_seconds(),
                    )
                )

            # Проход цел от first_seen_at до выхода: path[0] теперь
            # принадлежит текущему проходу, а не первому за всё время.
            total_time_sec = (now - hanger.first_seen_at).total_seconds()
            event = {
                "type": "unload",
                "reason": None,
                "cycle_id": hanger.cycle_id,
                "hanger": hanger_id,
                "first_seen_at": hanger.first_seen_at.isoformat(),
                "entry_bath": hanger.entry_bath,
                "exit_at": now.isoformat(),
                "total_time_sec": total_time_sec,
                "baths_visited": [e.bath_name for e in hanger.path],
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%d.%m.%Y"),
                "timestamp": now.isoformat(),
            }

            # cycle_id НЕ обнуляем: он идентифицирует проход и по нему же
            # отсекается повторная обработка того же выхода при дрожании
            # датчика. Признак «подвес не на линии» — это current_bath.
            logger.info(
                f"Hanger {hanger_id} cycle {hanger.cycle_id} unloaded "
                f"after {total_time_sec / 60:.1f} min, "
                f"{len(hanger.path)} baths."
            )
            hanger.current_bath = None
            hanger.entry_time = None
            hanger.last_seen = now
            hanger.unseen_since = None

            await self._publish(event, now, hanger_id)

        except Exception as e:
            logger.error(f"[Line Monitor] Record unload error for hanger {hanger_id}: {e}", exc_info=True)

    async def _publish(
        self, event: Dict, now: datetime, hanger_id: int
    ) -> None:
        """Положить событие в кэш и разослать клиентам (с retry)."""
        # Cache event (deque автоматически удаляет старые)
        self._unload_events.append(event)

        message = WebSocketMessage(type="unload_event", payload=event, timestamp=now)

        # Пробуем отправить до 3 раз с небольшой задержкой
        for attempt in range(3):
            sent = await websocket_manager.broadcast(message)
            if sent > 0:
                logger.info(
                    f"[Line Monitor] Unload broadcast OK: "
                    f"hanger {hanger_id}, type {event.get('type')}, sent to {sent} clients"
                )
                break
            elif websocket_manager.connection_count > 0:
                logger.warning(f"[Line Monitor] Unload broadcast attempt {attempt+1} failed, retrying...")
                await asyncio.sleep(0.1)
    
    def get_unload_events(self, limit: int = 100) -> List[dict]:
        """Последние выходы с линии, новые сверху.

        deque хранит события в порядке появления, то есть новый выход
        встаёт в конец. Таблица выхода читается сверху вниз, поэтому
        возвращаем новые сверху — иначе только что сошедший подвес
        появлялся бы снизу, под уже ушедшими. Порядок тот же, что у
        /line/cycles.
        """
        events = list(self._unload_events)
        recent = events[-limit:] if limit < len(events) else events
        return recent[::-1]
    
    def get_hanger_state(self, hanger_num: int) -> Optional[HangerState]:
        """Get current state of a hanger."""
        return self._hangers.get(hanger_num)
    
    def get_active_hangers(self) -> List[HangerState]:
        """Get all hangers currently considered active in the line."""
        return [h for h in self._hangers.values() if h.current_bath is not None]


# Singleton instance
line_monitor = LineMonitorService()
