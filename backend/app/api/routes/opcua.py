"""
OPC UA API routes - подключение к OMRON PLC и чтение данных.
"""
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.opcua_service import opcua_service
from app.services.line_monitor import line_monitor
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opcua", tags=["opcua"])


class OPCUAStatus(BaseModel):
    """Статус OPC UA подключения."""
    available: bool
    enabled: bool
    connected: bool
    state: str
    endpoint: Optional[str] = None
    stats: dict


class OPCUANodeValue(BaseModel):
    """Значение узла OPC UA."""
    node_id: str
    value: Any
    type: str


class OPCUANodesList(BaseModel):
    """Список узлов."""
    nodes: List[Dict[str, str]]


@router.get("/status", response_model=OPCUAStatus)
async def get_opcua_status():
    """Получить статус OPC UA подключения."""
    diagnostics = opcua_service.get_diagnostics()
    
    return OPCUAStatus(
        available=diagnostics['available'],
        enabled=diagnostics['enabled'],
        connected=diagnostics['connected'],
        state=diagnostics['state'],
        endpoint=diagnostics['endpoint'],
        stats=diagnostics['stats']
    )


@router.get("/diagnose")
async def diagnose_opcua():
    """Диагностировать проблемы с OPC UA подключением."""
    import socket
    from urllib.parse import urlparse
    
    diagnostics = opcua_service.get_diagnostics()
    
    # Парсим endpoint
    parsed = urlparse(settings.OPCUA_ENDPOINT)
    host = parsed.hostname
    port = parsed.port or 4840
    
    # Проверяем доступность хоста
    host_reachable = False
    try:
        socket.create_connection((host, port), timeout=5)
        host_reachable = True
        logger.info(f"[OPC UA Diagnose] Host {host}:{port} is reachable")
    except socket.timeout:
        logger.warning(f"[OPC UA Diagnose] Host {host}:{port} timeout")
    except socket.error as e:
        logger.warning(f"[OPC UA Diagnose] Cannot reach {host}:{port}: {e}")
    
    # Измеряем ping
    ping_ms = await opcua_service.ping_server()
    
    return {
        "endpoint": settings.OPCUA_ENDPOINT,
        "host": host,
        "port": port,
        "host_reachable": host_reachable,
        "ping_ms": round(ping_ms, 1) if ping_ms else None,
        "opcua_connected": diagnostics['connected'],
        "opcua_state": diagnostics['state'],
        "reconnect_attempts": diagnostics.get('reconnect_attempts', 0),
        "blacklisted_nodes": diagnostics.get('blacklisted_nodes', 0),
        "stats": diagnostics['stats'],
        "metrics": diagnostics.get('metrics', {}),
        "recommendations": [
            "Check if OPC UA server is running" if not host_reachable else "Host is reachable",
            "Check firewall rules for port 4840" if not host_reachable else "Port 4840 is open",
            "Verify network connectivity" if not host_reachable else "Network is OK",
            "Check OPC UA endpoint configuration" if not diagnostics['connected'] else "OPC UA is connected",
            f"Network latency: {ping_ms:.1f}ms" if ping_ms else "Cannot measure network latency",
        ]
    }


@router.get("/metrics")
async def get_opcua_metrics():
    """
    Получить детальные метрики подключения OPC UA.
    Полезно для диагностики проблем со стабильностью.
    """
    diagnostics = opcua_service.get_diagnostics()
    metrics = diagnostics.get('metrics', {})
    
    # Измеряем текущий ping
    ping_ms = await opcua_service.ping_server()
    
    return {
        "connected": diagnostics['connected'],
        "state": diagnostics['state'],
        "current_ping_ms": round(ping_ms, 1) if ping_ms else None,
        "metrics": metrics,
        "stats": diagnostics['stats'],
        "reconnect_attempts": diagnostics.get('reconnect_attempts', 0),
        "blacklisted_nodes": diagnostics.get('blacklisted_nodes', 0),
    }


@router.post("/connect")
async def connect_opcua():
    """Подключиться к OPC UA серверу."""
    if not opcua_service.is_available:
        raise HTTPException(status_code=400, detail="OPC UA library not available")
    
    success = await opcua_service.connect()
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect to OPC UA server")
    
    return {"status": "connected", "endpoint": settings.OPCUA_ENDPOINT}


@router.post("/disconnect")
async def disconnect_opcua():
    """Отключиться от OPC UA сервера и очистить все данные."""
    await opcua_service.disconnect()
    # Также очищаем данные мониторинга линии
    line_monitor.clear_data()
    return {"status": "disconnected", "data_cleared": True}


@router.get("/read/{node_id}", response_model=OPCUANodeValue)
async def read_node(node_id: str):
    """
    Прочитать значение узла из кэша.
    Возвращает последнее известное значение (обновляется раз в секунду).
    """
    value = opcua_service.get_value(node_id)
    
    # Если узла нет в кэше — он не зарегистрирован для опроса
    if value is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Node {node_id} not in cache. Register it via line_monitor or check if OPC UA is connected."
        )
    
    return OPCUANodeValue(
        node_id=node_id,
        value=value,
        type=type(value).__name__
    )


@router.post("/read-multiple")
async def read_multiple_nodes(node_ids: List[str] = Query(...)):
    """Прочитать несколько узлов из кэша."""
    results = {node_id: opcua_service.get_value(node_id) for node_id in node_ids}
    
    return {
        "nodes": [
            {
                "node_id": node_id,
                "value": value,
                "type": type(value).__name__ if value is not None else "null"
            }
            for node_id, value in results.items()
        ]
    }


@router.get("/browse/{node_id}", response_model=OPCUANodesList)
async def browse_node(node_id: str):
    """Получить дочерние узлы."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    nodes = await opcua_service.browse_node(node_id)
    
    return OPCUANodesList(nodes=nodes)


@router.get("/global-variables")
async def get_global_variables():
    """Получить список всех глобальных переменных контроллера (только структура)."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    try:
        # Рекурсивно получаем структуру узлов (без чтения значений)
        all_nodes = await opcua_service.browse_recursive("ns=4;s=NxController.GlobalVars", max_depth=3)
        
        variables = []
        for node in all_nodes:
            variables.append({
                "id": node['id'],
                "name": node['name'],
                "depth": node['depth']
            })
        
        return {
            "total": len(variables),
            "variables": variables
        }
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting global variables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/variables")
async def get_available_variables():
    """Получить список доступных переменных для чтения."""
    variables = [
        {
            "id": "i=2258",
            "name": "Server Current Time",
            "description": "Текущее время сервера",
            "category": "System"
        },
        {
            "id": "i=2256",
            "name": "Server Status",
            "description": "Статус сервера OPC UA",
            "category": "System"
        },
        {
            "id": "i=2257",
            "name": "Build Info",
            "description": "Информация о сборке сервера",
            "category": "System"
        },
        {
            "id": "ns=4;s=NumOfVars",
            "name": "Total Variables",
            "description": "Количество переменных в ПЛК",
            "category": "Controller"
        },
        {
            "id": "ns=4;s=NumOfValues",
            "name": "Active Values",
            "description": "Количество активных значений",
            "category": "Controller"
        },
        {
            "id": "ns=4;s=PLC.DeviceStatus",
            "name": "Device Status",
            "description": "Статус устройства ПЛК",
            "category": "Controller"
        },
        {
            "id": "ns=4;s=NxController.GlobalVars",
            "name": "Global Variables",
            "description": "Глобальные переменные контроллера",
            "category": "Controller"
        },
    ]
    return {"variables": variables}


@router.post("/read-variable")
async def read_variable(node_id: str = Query(...)):
    """Прочитать конкретную переменную из кэша."""
    value = opcua_service.get_value(node_id)
    
    if value is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Variable {node_id} not in cache"
        )
    
    return {
        "node_id": node_id,
        "value": str(value),
        "type": type(value).__name__
    }


@router.get("/data")
async def get_plc_data():
    """Получить основные данные с ПЛК из кэша."""
    try:
        server_time = opcua_service.get_value("i=2258")
        
        return {
            "status": "ok" if opcua_service.is_connected else "disconnected",
            "server_time": str(server_time) if server_time else None,
            "connected": opcua_service.is_connected,
            "cache_size": len(opcua_service._cache),
        }
        
    except Exception as e:
        logger.error(f"[OPC UA] Error reading data: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# Hanger Tracking Endpoints (подвесы)

@router.post("/hangers/scan")
async def scan_hangers():
    """Сканировать все ванны и обновить информацию о подвесах."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    await line_monitor._scan_baths()
    active = [h for h in line_monitor._hangers.values() if h.current_bath is not None]
    return {
        "status": "scanned",
        "total_hangers": len(line_monitor._hangers),
        "active_hangers": len(active)
    }


@router.get("/hangers")
async def get_all_hangers():
    """Получить все подвесы."""
    hangers = line_monitor._hangers.values()
    return {
        "total": len(hangers),
        "hangers": [{
            "number": h.id, 
            "current_bath": int(h.current_bath) if h.current_bath and h.current_bath.isdigit() else None, 
            "baths_visited": [int(entry.bath_name) if entry.bath_name.isdigit() else entry.bath_name for entry in h.path]
        } for h in hangers]
    }


@router.get("/hangers/active")
async def get_active_hangers():
    """Получить активные подвесы (сейчас в ванне)."""
    hangers = [h for h in line_monitor._hangers.values() if h.current_bath is not None]
    return {
        "total": len(hangers),
        "hangers": [{
            "number": h.id, 
            "current_bath": int(h.current_bath) if h.current_bath and h.current_bath.isdigit() else None, 
            "baths_visited": [int(entry.bath_name) if entry.bath_name.isdigit() else entry.bath_name for entry in h.path]
        } for h in hangers]
    }


@router.get("/hangers/{hanger_number}")
async def get_hanger(hanger_number: int):
    """Получить данные подвеса по номеру."""
    hanger = line_monitor._hangers.get(hanger_number)
    if not hanger:
        raise HTTPException(status_code=404, detail=f"Hanger {hanger_number} not found")
    return {
        "number": hanger.id, 
        "current_bath": int(hanger.current_bath) if hanger.current_bath and hanger.current_bath.isdigit() else None, 
        "baths_visited": [int(entry.bath_name) if entry.bath_name.isdigit() else entry.bath_name for entry in hanger.path]
    }


@router.get("/baths/{bath_number}/hanger")
async def get_hanger_in_bath(bath_number: int):
    """Получить подвес который сейчас в ванне."""
    bath_name = str(bath_number)
    for hanger in line_monitor._hangers.values():
        if hanger.current_bath == bath_name:
            return {
                "bath_number": bath_number, 
                "hanger": {
                    "number": hanger.id, 
                    "current_bath": int(hanger.current_bath) if hanger.current_bath and hanger.current_bath.isdigit() else None
                }
            }
    return {"bath_number": bath_number, "hanger": None}



# Line Monitoring Control Endpoints

@router.post("/monitor/start")
async def start_line_monitor():
    """Start line monitoring."""
    success = await line_monitor.start()
    if not success:
        raise HTTPException(status_code=400, detail="Monitor already running")
    return {"status": "started"}


@router.post("/monitor/stop")
async def stop_line_monitor():
    """Stop line monitoring."""
    await line_monitor.stop()
    return {"status": "stopped"}


@router.get("/monitor/status")
async def get_line_monitor_status():
    """Get line monitor status."""
    return {
        "running": line_monitor.is_running,
        "events_cached": len(line_monitor.get_unload_events()),
        "active_hangers": len(line_monitor.get_active_hangers())
    }



# Line Monitoring Endpoints (визуализация линии)

@router.get("/line/status")
async def get_line_status():
    """
    Получить статус всех ванн линии (1-39).
    Читает из кэша — мгновенный отклик.
    """
    try:
        # Формируем результат из кэша
        baths = []
        for i in range(1, 40):
            in_use = opcua_service.get_value(f"ns=4;s=Bath[{i}].InUse")
            free = opcua_service.get_value(f"ns=4;s=Bath[{i}].Free")
            pallete = opcua_service.get_value(f"ns=4;s=Bath[{i}].Pallete")
            in_time = opcua_service.get_value(f"ns=4;s=Bath[{i}].InTime")
            out_time = opcua_service.get_value(f"ns=4;s=Bath[{i}].OutTime")
            d_time = opcua_service.get_value(f"ns=4;s=Bath[{i}].dTime")
            
            baths.append({
                "bath_number": i,
                "in_use": bool(in_use) if in_use is not None else False,
                "free": bool(free) if free is not None else True,
                "pallete": int(pallete) if pallete else 0,
                "in_time": float(in_time) if in_time else 0,
                "out_time": float(out_time) if out_time else 0,
                "d_time": float(d_time) if d_time else 0,
            })
        
        # Данные блока питания
        power_supply = {
            "current": float(opcua_service.get_value("ns=4;s=S8VK_X.Current") or 0),
            "voltage": float(opcua_service.get_value("ns=4;s=S8VK_X.Voltage") or 0),
        }
        
        from datetime import datetime
        return {
            "baths": baths,
            "power_supply": power_supply,
            "timestamp": datetime.now().isoformat(),
            "total_baths": len(baths),
            "active_baths": sum(1 for b in baths if b["in_use"]),
            "opcua_connected": opcua_service.is_connected,
        }
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting line status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/line/bath/{bath_number}")
async def get_bath_status(bath_number: int):
    """Получить статус конкретной ванны из кэша."""
    if bath_number < 1 or bath_number > 39:
        raise HTTPException(status_code=400, detail="Bath number must be between 1 and 39")
    
    try:
        bath_data = {
            "bath_number": bath_number,
            "in_use": bool(opcua_service.get_value(f"ns=4;s=Bath[{bath_number}].InUse") or False),
            "free": bool(opcua_service.get_value(f"ns=4;s=Bath[{bath_number}].Free") or True),
            "pallete": int(opcua_service.get_value(f"ns=4;s=Bath[{bath_number}].Pallete") or 0),
            "in_time": float(opcua_service.get_value(f"ns=4;s=Bath[{bath_number}].InTime") or 0),
            "out_time": float(opcua_service.get_value(f"ns=4;s=Bath[{bath_number}].OutTime") or 0),
            "d_time": float(opcua_service.get_value(f"ns=4;s=Bath[{bath_number}].dTime") or 0),
        }
        
        return bath_data
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting bath {bath_number} status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/line/cycles")
async def get_completed_cycles(limit: int = 20):
    """Получить завершённые циклы (подвесы вышедшие из линии через Bath[34])."""
    # Get cycles from line monitor
    all_hangers = list(line_monitor._hangers.values())
    
    # Filter completed hangers (not currently in any bath but have path history)
    completed = [h for h in all_hangers if h.current_bath is None and h.path]
    
    # Sort by last_seen descending
    completed.sort(key=lambda h: h.last_seen, reverse=True)
    
    cycles = []
    for hanger in completed[:limit]:
        if hanger.path:
            baths_visited = [entry.bath_name for entry in hanger.path]
            cycles.append({
                "timestamp": hanger.path[0].entry_time.isoformat() if hanger.path else None,
                "pallete": hanger.id,
                "baths_visited": baths_visited
            })
    
    return {
        "total": len(cycles),
        "cycles": cycles
    }


@router.get("/line/power")
async def get_power_supply_status():
    """Получить статус блока питания S8VK_X из кэша."""
    try:
        power_data = {
            "status": opcua_service.get_value("ns=4;s=S8VK_X.Status"),
            "voltage": opcua_service.get_value("ns=4;s=S8VK_X.Voltage"),
            "current": opcua_service.get_value("ns=4;s=S8VK_X.Current"),
        }
        
        return power_data
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting power supply status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# System Health & Memory Monitoring

@router.get("/system/health")
async def get_system_health():
    """
    Полная диагностика системы — память, лимиты, потенциальные проблемы.
    Используй для мониторинга долгосрочной стабильности.
    """
    import sys
    
    # OPC UA диагностика
    opcua_diag = opcua_service.get_diagnostics()
    
    # Line Monitor диагностика
    hangers_count = len(line_monitor._hangers)
    active_hangers = len(line_monitor.get_active_hangers())
    unload_events = len(line_monitor.get_unload_events())
    
    # Подсчёт размера path у всех подвесов
    total_path_entries = sum(len(h.path) for h in line_monitor._hangers.values())
    max_path_length = max((len(h.path) for h in line_monitor._hangers.values()), default=0)
    
    # WebSocket
    from app.services.websocket_manager import websocket_manager
    ws_connections = websocket_manager.connection_count
    
    # Предупреждения
    warnings = []
    if hangers_count > 400:
        warnings.append(f"High hanger count: {hangers_count}/500")
    if max_path_length > 80:
        warnings.append(f"Long hanger path detected: {max_path_length}/100 entries")
    if opcua_diag['stats']['errors'] > 100:
        warnings.append(f"High OPC UA error count: {opcua_diag['stats']['errors']}")
    if not opcua_diag['connected']:
        warnings.append("OPC UA disconnected!")
    
    return {
        "status": "healthy" if not warnings else "warning",
        "warnings": warnings,
        "opcua": {
            "connected": opcua_diag['connected'],
            "state": opcua_diag['state'],
            "cache_entries": opcua_diag['cache_entries'],
            "cache_size_kb": opcua_diag['cache_size_kb'],
            "monitored_nodes": opcua_diag['monitored_nodes'],
            "stats": opcua_diag['stats'],
        },
        "line_monitor": {
            "hangers_tracked": hangers_count,
            "hangers_active": active_hangers,
            "hangers_limit": 500,
            "total_path_entries": total_path_entries,
            "max_path_length": max_path_length,
            "path_limit": 100,
            "unload_events_cached": unload_events,
            "unload_events_limit": 500,
        },
        "websocket": {
            "connections": ws_connections,
        },
        "limits": {
            "max_hangers": 500,
            "max_path_length": 100,
            "max_unload_events": 500,
            "stats_reset_at": 1_000_000_000,
        }
    }
