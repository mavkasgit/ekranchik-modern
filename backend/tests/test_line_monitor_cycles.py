"""Жизненный цикл прохода подвеса в line_monitor.

Контракт под тестом:
- каждый проход подвеса по линии получает свой cycle_id, first_seen_at и
  entry_bath; номер подвеса проход не идентифицирует, он повторяется;
- path принадлежит ТОЛЬКО текущему проходу и не наследуется следующему
  (иначе path[0] указывал бы на первый проход за всё время);
- выгрузка без открытого прохода даёт cycle_error, а не «нормальный» выход
  с total_time_sec = 0, и cycle_id задним числом не создаётся;
- дедупликация по cycle_id: два выхода одного номера в разных проходах —
  два события, повторная обработка одного прохода отсекается.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from app.services import line_monitor as lm
from app.services.line_monitor import LineMonitorService


@pytest.fixture
def monitor(monkeypatch):
    svc = LineMonitorService()
    monkeypatch.setattr(lm.opcua_service, "get_value", lambda node: None)
    return svc


def _baths(mapping):
    """Подменить значения OPC UA: {номер ванны: (InUse, Pallete)}."""
    def get_value(node: str):
        for bath, (in_use, pallete) in mapping.items():
            if node == f"ns=4;s=Bath[{bath}].InUse":
                return in_use
            if node == f"ns=4;s=Bath[{bath}].Pallete":
                return pallete
        return None
    return get_value


def test_repeated_number_gets_separate_cycles(monitor, monkeypatch):
    """Номер 1 прогоняют дважды — это два прохода, а не один с накопленным path."""
    monitor._open_cycle_hanger = None  # атрибут не используется, читаем состояние
    first = monitor._open_cycle
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    first(state, 3, datetime(2026, 9, 29, 20, 0))
    state.current_bath = "3"
    state.path.append(lm.HangerPathEntry("3", datetime(2026, 9, 29, 20, 0)))
    state.current_bath = None  # подвес сошёл

    second = monitor._open_cycle
    later = datetime(2026, 9, 29, 22, 40)
    second(state, 4, later)

    assert state.cycle_id == 2
    assert state.first_seen_at == later
    assert state.entry_bath == 4
    assert state.path == [], "путь прошлого прохода не должен наследоваться"


def test_counter_continues_from_the_journal_after_a_restart(monitor):
    """После перезапуска номера проходов продолжаются, а не начинаются с 1.

    Счётчик живёт в памяти, поэтому без подстановки из журнала каждый
    перезапуск выдавал бы номера, уже занятые, и разбирать проходы по номеру
    становилось бы невозможно.
    """
    monitor.resume_cycle_counter(19)
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state

    monitor._open_cycle(state, 3, datetime(2026, 9, 29, 20, 0))

    assert state.cycle_id == 20


def test_counter_resume_never_goes_backwards(monitor):
    """Чужое или битое значение не сбрасывает счётчик назад."""
    monitor.resume_cycle_counter(100)
    monitor.resume_cycle_counter(-5)
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state

    monitor._open_cycle(state, 3, datetime(2026, 9, 29, 20, 0))

    assert state.cycle_id == 101


def test_unload_closes_cycle_with_its_own_path(monitor, monkeypatch):
    """total_time_sec считается по текущему проходу, а не по первому за всё время."""
    start = datetime.now() - timedelta(minutes=90)
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    monitor._open_cycle(state, 3, start)
    state.current_bath = "34"
    state.entry_time = start + timedelta(minutes=89)
    state.path.append(lm.HangerPathEntry("3", start))
    state.path.append(lm.HangerPathEntry("4", start + timedelta(minutes=30)))

    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(1))

    event = monitor.get_unload_events()[-1]
    assert event["type"] == "unload"
    assert event["cycle_id"] == state.cycle_id
    assert 5300 < event["total_time_sec"] < 5500, "считает от первого замера текущего прохода"
    assert event["baths_visited"] == ["3", "4", "34"]


def test_unload_without_open_cycle_is_error(monitor, monkeypatch):
    """Состояние есть, но прохода нет — это ошибка монитора, а не выход."""
    state = lm.HangerState(id=4)
    state.current_bath = None
    state.path = []
    monitor._hangers[4] = state

    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(4))

    event = monitor.get_unload_events()[-1]
    assert event["type"] == "cycle_error"
    assert event["reason"] == "unload_without_open_cycle"
    assert event["cycle_id"] is None, "цикл не создаётся задним числом"
    assert event["total_time_sec"] is None
    assert event["baths_visited"] is None


def test_dedup_by_cycle_id_keeps_both_unloads(monitor, monkeypatch):
    """Два выхода одного номера в разных проходах — два разных события."""
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    now = datetime.now()
    for cycle_start in (now - timedelta(hours=2), now - timedelta(minutes=10)):
        state = lm.HangerState(id=1)
        monitor._hangers[1] = state
        monitor._open_cycle(state, 3, cycle_start)
        state.path.append(lm.HangerPathEntry("3", cycle_start))
        state.current_bath = "34"
        state.entry_time = datetime.now()
        asyncio.run(monitor._record_unload(1))

    events = monitor.get_unload_events()
    assert len(events) == 2
    assert all(e["type"] == "unload" for e in events)
    assert len({e["cycle_id"] for e in events}) == 2, "у проходов разные cycle_id"


def test_duplicate_processing_of_same_cycle_dropped(monitor, monkeypatch):
    """Повторная обработка одного прохода второго события не создаёт."""
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    state = lm.HangerState(id=1)
    monitor._hangers[1] = state
    monitor._open_cycle(state, 3, datetime.now() - timedelta(minutes=30))
    state.path.append(lm.HangerPathEntry("3", datetime.now() - timedelta(minutes=30)))
    state.current_bath = "34"
    state.entry_time = datetime.now()

    asyncio.run(monitor._record_unload(1))
    # Датчик дрогнул 0→N ещё раз для того же прохода: current_bath уже None,
    # но cycle_id тот же — ни дубля выхода, ни второй cycle_error.
    asyncio.run(monitor._record_unload(1))

    events = monitor.get_unload_events()
    assert len(events) == 1
    assert events[0]["type"] == "unload"


def test_transit_gap_does_not_break_cycle(monitor, monkeypatch):
    """Переход между ваннами — не новый проход.

    На линии подвес минутами не виден ни в одной ванне: он едет между
    ними. Прежний порог в 5 секунд считал это уходом с линии, обнулял
    first_seen_at и path, а следующий выход уходил в CYCLE_ERROR — из-за
    чего таблица выхода оставалась пустой.
    """
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths({30: (True, 1)}))
    asyncio.run(monitor._scan_baths())
    state = monitor._hangers[1]
    opened_at = state.first_seen_at
    cycle_id = state.cycle_id
    assert state.entry_bath == 30

    # Подвес пропал из ванн на 10 минут — едет между ними.
    monitor._departure_bound = timedelta(minutes=42)
    seen = monitor._hangers[1]
    seen.unseen_since = datetime.now() - timedelta(minutes=10)
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths({31: (True, 1)}))
    asyncio.run(monitor._scan_baths())

    assert state.cycle_id == cycle_id, "переход не открывает новый проход"
    assert state.first_seen_at == opened_at, "first_seen_at не обнуляется переходом"
    assert state.entry_bath == 30, "ванна входа остаётся той, где подвес появился"
    # path хранит завершённые ванны, текущая ванна — отдельно.
    assert [e.bath_name for e in state.path] == ["30"]
    assert state.current_bath == "31"


def test_unload_during_transit_keeps_cycle(monitor, monkeypatch):
    """Выгрузка в разрыве видимости — нормальный выход, а не CYCLE_ERROR."""
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths({30: (True, 46)}))
    asyncio.run(monitor._scan_baths())
    state = monitor._hangers[46]
    cycle_id = state.cycle_id

    # Подвес не виден ни в одной ванне (скан не успел), но проход цел.
    state.unseen_since = datetime.now() - timedelta(minutes=1)
    state.last_seen = datetime.now() - timedelta(minutes=1)
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(46))

    event = monitor.get_unload_events()[-1]
    assert event["type"] == "unload", "валидный проход нельзя выбрасывать"
    assert event["cycle_id"] == cycle_id
    assert event["entry_bath"] == 30


def test_unloaded_hanger_parked_at_control_bath_starts_no_cycle(monitor, monkeypatch):
    """Выгруженный подвес ещё стоит в 34-й — нового прохода это не начинает."""
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    state = lm.HangerState(id=7)
    monitor._hangers[7] = state
    monitor._open_cycle(state, 30, datetime.now() - timedelta(minutes=15))
    state.current_bath = "34"
    state.entry_time = datetime.now()
    asyncio.run(monitor._record_unload(7))
    cycle_after_unload = state.cycle_id

    # Скан видит подвеса в 34-й: это то же самое присутствие после выгрузки.
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths({34: (True, 7)}))
    asyncio.run(monitor._scan_baths())

    assert state.cycle_id == cycle_after_unload, "фантомный проход не заводится"
    assert monitor.get_unload_events()[-1]["type"] == "unload"


def test_hanger_leaving_line_closes_cycle(monitor, monkeypatch):
    """Подвес, пропавший заведомо дольше границы, проход закрывает."""
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths({30: (True, 3)}))
    asyncio.run(monitor._scan_baths())
    state = monitor._hangers[3]

    monitor._departure_bound = timedelta(minutes=42)
    state.unseen_since = datetime.now() - timedelta(minutes=43)
    state.last_seen = datetime.now() - timedelta(minutes=43)
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths({}))
    asyncio.run(monitor._scan_baths())

    assert state.cycle_id is None, "проход закрыт"
    assert state.current_bath is None, "подвес больше не на линии"


def test_departure_bound_comes_from_longest_bath(monitor, monkeypatch):
    """Граница невидимости считается по самой долгой ванне, а не константой."""
    values = {
        "ns=4;s=Bath[1].dTime": 60,
        "ns=4;s=Bath[2].dTime": 2200,   # самая долгая ванна
        "ns=4;s=Bath[3].dTime": 90,
        "ns=4;s=Bath[4].dTime": -448,   # счётчик ванны перешёл сутки
    }
    monkeypatch.setattr(lm.opcua_service, "get_value", lambda node: values.get(node))
    monitor._refresh_departure_bound()
    assert monitor._departure_bound == timedelta(
        seconds=2200 + lm.DEPARTURE_MARGIN_SECONDS
    )

    # Молчащий PLC не должен обнулять границу.
    monkeypatch.setattr(lm.opcua_service, "get_value", lambda node: 0)
    monitor._refresh_departure_bound()
    assert monitor._departure_bound == timedelta(
        seconds=2200 + lm.DEPARTURE_MARGIN_SECONDS
    ), "предыдущая граница держится, пока PLC не отдаёт dTime"


def test_unload_events_returned_newest_first(monitor, monkeypatch):
    """Таблица выхода читается сверху вниз, поэтому новый выход сверху.

    deque хранит события по порядку появления, то есть новый выход встаёт
    в конец списка. Без разворота только что сошедший подвес появлялся бы
    снизу, под уже ушедшими, и оператор его не видел.
    """
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    for number, minutes_ago in ((2, 30), (3, 20), (5, 10)):
        state = lm.HangerState(id=number)
        monitor._hangers[number] = state
        seen = datetime.now() - timedelta(minutes=minutes_ago)
        monitor._open_cycle(state, 30, seen)
        state.current_bath = "34"
        state.entry_time = datetime.now()
        asyncio.run(monitor._record_unload(number))

    events = monitor.get_unload_events()

    assert [e["hanger"] for e in events] == [5, 3, 2], "новый выход сверху"


def test_unload_events_limit_keeps_most_recent(monitor, monkeypatch):
    """limit режет самые старые, а не новые."""
    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    for number in (2, 3, 5, 7):
        state = lm.HangerState(id=number)
        monitor._hangers[number] = state
        monitor._open_cycle(state, 30, datetime.now() - timedelta(minutes=10))
        state.current_bath = "34"
        state.entry_time = datetime.now()
        asyncio.run(monitor._record_unload(number))

    events = monitor.get_unload_events(limit=2)

    assert [e["hanger"] for e in events] == [7, 5]


async def _connected() -> bool:
    return True


def _poll(monitor, monkeypatch, mapping):
    """Один успешный опрос линии: связь есть, ванны отдают mapping."""
    monkeypatch.setattr(lm.opcua_service, "ensure_connected", _connected)
    monkeypatch.setattr(lm.opcua_service, "_connected", True)
    monkeypatch.setattr(lm.opcua_service, "get_value", _baths(mapping))
    asyncio.run(monitor._poll_once())


def test_first_scan_after_start_is_untrusted(monitor, monkeypatch):
    """Первый скан после старта: подвес застали стоящим, первый замер врёт.

    Вход на линию монитор не видит. Проход, открытый на старте, получает
    first_seen_at = момент старта, и расхождение с книгой по нему считать
    нельзя — иначе каждый подвес, стоявший на линии в момент перезапуска,
    получает мусорную дельту.
    """
    _poll(monitor, monkeypatch, {5: (True, 777)})

    assert monitor._hangers[777].first_seen_source == lm.FIRST_SEEN_START


def test_scan_after_connection_gap_is_untrusted(monitor, monkeypatch):
    """Пауза без опросов: за неё подвес мог появиться и уйти незамеченным."""
    _poll(monitor, monkeypatch, {5: (True, 777)})
    monitor._last_scan_at = datetime.now() - timedelta(minutes=5)

    _poll(monitor, monkeypatch, {5: (True, 777), 6: (True, 888)})

    assert monitor._hangers[888].first_seen_source == lm.FIRST_SEEN_GAP


def test_scan_on_watched_line_is_trusted(monitor, monkeypatch):
    """Линию наблюдали непрерывно — первый замер достоверен."""
    _poll(monitor, monkeypatch, {5: (True, 777)})

    _poll(monitor, monkeypatch, {5: (True, 777), 6: (True, 888)})

    assert monitor._hangers[888].first_seen_source == lm.FIRST_SEEN_WATCHED


def test_unload_event_carries_source_and_path_times(monitor, monkeypatch):
    """Событие выгрузки несёт источник первого замера и путь с временами.

    Одну модель прохода отдают и событие, и /line/cycles: по ней в журнале
    разбирают сопоставление со строкой книги.
    """
    start = datetime(2026, 9, 29, 13, 11, 0)
    left_30 = start + timedelta(minutes=51)
    state = lm.HangerState(id=21)
    monitor._hangers[21] = state
    monitor._open_cycle(state, 30, start)
    state.current_bath = "31"
    state.entry_time = start + timedelta(minutes=54)
    state.path.append(lm.HangerPathEntry("30", start, left_30))

    monkeypatch.setattr(lm, "websocket_manager", _SilentWS())
    asyncio.run(monitor._record_unload(21))

    event = monitor.get_unload_events()[-1]
    assert event["first_seen_source"] == lm.FIRST_SEEN_START
    assert event["path"][0] == {"bath": "30", "in": start.isoformat(), "out": left_30.isoformat()}
    assert event["path"][-1]["bath"] == "31"
    assert event["path"][-1]["out"] == event["exit_at"], "выход прохода закрывает последнюю ванну"


class _SilentWS:
    connection_count = 0

    async def broadcast(self, message):
        return 0
