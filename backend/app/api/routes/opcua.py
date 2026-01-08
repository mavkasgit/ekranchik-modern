"""
OPC UA API routes - подключение к OMRON PLC и чтение данных.
"""
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.opcua_service import opcua_service
from app.services.hanger_service import hanger_service
from app.services.opcua_poller import opcua_poller
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
    """Отключиться от OPC UA сервера."""
    await opcua_service.disconnect()
    return {"status": "disconnected"}


@router.get("/read/{node_id}", response_model=OPCUANodeValue)
async def read_node(node_id: str):
    """Прочитать значение узла."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    value = await opcua_service.read_node(node_id)
    
    if value is None:
        raise HTTPException(status_code=500, detail=f"Failed to read node {node_id}")
    
    return OPCUANodeValue(
        node_id=node_id,
        value=value,
        type=type(value).__name__
    )


@router.post("/read-multiple")
async def read_multiple_nodes(node_ids: List[str] = Query(...)):
    """Прочитать несколько узлов."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    results = await opcua_service.read_nodes(node_ids)
    
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
    """Прочитать конкретную переменную."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    value = await opcua_service.read_node(node_id)
    
    if value is None:
        raise HTTPException(status_code=500, detail=f"Failed to read variable {node_id}")
    
    return {
        "node_id": node_id,
        "value": str(value),
        "type": type(value).__name__
    }


@router.get("/data")
async def get_plc_data():
    """Получить основные данные с ПЛК."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    try:
        # Основные узлы для чтения
        node_ids = [
            "i=2258",                    # Server CurrentTime
            "ns=4;s=NumOfVars",          # Количество переменных
            "ns=4;s=NumOfValues",        # Количество значений
            "ns=4;s=PLC.DeviceStatus",   # Статус устройства
            "ns=4;s=NxController.GlobalVars",  # Глобальные переменные
        ]
        
        values = await opcua_service.read_nodes(node_ids)
        
        # Пробуем прочитать дополнительные важные переменные
        important_vars = {}
        
        # Пытаемся получить статус работы
        try:
            status = await opcua_service.read_node("ns=4;s=PLC.DeviceStatus")
            if status:
                important_vars['device_status'] = str(status)
        except:
            pass
        
        # Пытаемся получить информацию о сервере
        try:
            server_status = await opcua_service.read_node("i=2256")  # ServerStatus
            if server_status:
                important_vars['server_status'] = str(server_status)
        except:
            pass
        
        # Пытаемся получить информацию о сборке
        try:
            build_info = await opcua_service.read_node("i=2257")  # BuildInfo
            if build_info:
                important_vars['build_info'] = str(build_info)
        except:
            pass
        
        return {
            "status": "ok",
            "server_time": str(values.get("i=2258")),
            "num_vars": values.get("ns=4;s=NumOfVars"),
            "num_values": values.get("ns=4;s=NumOfValues"),
            "device_status": values.get("ns=4;s=PLC.DeviceStatus"),
            "important_vars": important_vars,
            "connected": True
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
    
    await hanger_service.scan_baths()
    return {
        "status": "scanned",
        "total_hangers": len(hanger_service.get_all_hangers()),
        "active_hangers": len(hanger_service.get_active_hangers())
    }


@router.get("/hangers")
async def get_all_hangers():
    """Получить все подвесы."""
    hangers = hanger_service.get_all_hangers()
    return {
        "total": len(hangers),
        "hangers": [h.to_dict() for h in hangers]
    }


@router.get("/hangers/active")
async def get_active_hangers():
    """Получить активные подвесы (сейчас в ванне)."""
    hangers = hanger_service.get_active_hangers()
    return {
        "total": len(hangers),
        "hangers": [h.to_dict() for h in hangers]
    }


@router.get("/hangers/{hanger_number}")
async def get_hanger(hanger_number: int):
    """Получить данные подвеса по номеру."""
    hanger = hanger_service.get_hanger(hanger_number)
    if not hanger:
        raise HTTPException(status_code=404, detail=f"Hanger {hanger_number} not found")
    return hanger.to_dict()


@router.get("/baths/{bath_number}/hanger")
async def get_hanger_in_bath(bath_number: int):
    """Получить подвес который сейчас в ванне."""
    hanger = hanger_service.get_hanger_in_bath(bath_number)
    if not hanger:
        return {"bath_number": bath_number, "hanger": None}
    return {"bath_number": bath_number, "hanger": hanger.to_dict()}



# OPC UA Poller Control Endpoints

@router.post("/poller/start")
async def start_opcua_poller():
    """Start OPC UA poller."""
    success = await opcua_poller.start()
    if not success:
        raise HTTPException(status_code=400, detail="Poller already running")
    return {"status": "started"}


@router.post("/poller/stop")
async def stop_opcua_poller():
    """Stop OPC UA poller."""
    await opcua_poller.stop()
    return {"status": "stopped"}


@router.get("/poller/status")
async def get_opcua_poller_status():
    """Get OPC UA poller status."""
    return {
        "running": opcua_poller.is_running,
        "events_cached": opcua_poller.events_count,
        "events": opcua_poller.cached_events
    }


@router.post("/poller/poll-now")
async def poll_opcua_now():
    """Trigger immediate poll."""
    await opcua_poller.poll_now()
    return {"status": "polled"}



# Line Monitoring Endpoints (визуализация линии)

@router.get("/line/status")
async def get_line_status():
    """Получить статус всех ванн линии (1-39)."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    try:
        baths = []
        bath_props = ["InUse", "Free", "Pallete", "InTime", "OutTime", "dTime"]
        
        for i in range(1, 40):  # Bath[1] to Bath[39]
            bath_data = {
                "bath_number": i,
                "in_use": False,
                "free": True,
                "pallete": 0,
                "in_time": 0,
                "out_time": 0,
                "d_time": 0
            }
            
            for prop in bath_props:
                try:
                    value = await opcua_service.read_node(f"ns=4;s=Bath[{i}].{prop}")
                    if prop == "InUse":
                        bath_data["in_use"] = bool(value) if value is not None else False
                    elif prop == "Free":
                        bath_data["free"] = bool(value) if value is not None else True
                    elif prop == "Pallete":
                        bath_data["pallete"] = int(value) if value is not None else 0
                    elif prop == "InTime":
                        bath_data["in_time"] = float(value) if value is not None else 0
                    elif prop == "OutTime":
                        bath_data["out_time"] = float(value) if value is not None else 0
                    elif prop == "dTime":
                        bath_data["d_time"] = float(value) if value is not None else 0
                except Exception as e:
                    logger.debug(f"Error reading Bath[{i}].{prop}: {e}")
            
            baths.append(bath_data)
        
        # Read power supply data
        power_supply = None
        try:
            current = await opcua_service.read_node("ns=4;s=S8VK_X.Current")
            voltage = await opcua_service.read_node("ns=4;s=S8VK_X.Voltage")
            run_time = await opcua_service.read_node("ns=4;s=S8VK_X.ContinuousRunTime")
            
            power_supply = {
                "current": float(current) if current is not None else 0,
                "voltage": float(voltage) if voltage is not None else 0,
                "continuous_run_time": float(run_time) if run_time is not None else 0
            }
        except Exception as e:
            logger.debug(f"Error reading power supply: {e}")
        
        from datetime import datetime
        return {
            "baths": baths,
            "power_supply": power_supply,
            "timestamp": datetime.now().isoformat(),
            "total_baths": len(baths),
            "active_baths": sum(1 for b in baths if b["in_use"])
        }
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting line status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/line/bath/{bath_number}")
async def get_bath_status(bath_number: int):
    """Получить статус конкретной ванны."""
    if bath_number < 1 or bath_number > 39:
        raise HTTPException(status_code=400, detail="Bath number must be between 1 and 39")
    
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    try:
        bath_data = {
            "bath_number": bath_number,
            "in_use": False,
            "free": True,
            "pallete": 0,
            "in_time": 0,
            "out_time": 0,
            "d_time": 0,
            "disable": False,
            "reserved": False,
            "priority": 0
        }
        
        props = ["InUse", "Free", "Pallete", "InTime", "OutTime", "dTime", "Disable", "Reserved", "aPriority"]
        
        for prop in props:
            try:
                value = await opcua_service.read_node(f"ns=4;s=Bath[{bath_number}].{prop}")
                if prop == "InUse":
                    bath_data["in_use"] = bool(value) if value is not None else False
                elif prop == "Free":
                    bath_data["free"] = bool(value) if value is not None else True
                elif prop == "Pallete":
                    bath_data["pallete"] = int(value) if value is not None else 0
                elif prop == "InTime":
                    bath_data["in_time"] = float(value) if value is not None else 0
                elif prop == "OutTime":
                    bath_data["out_time"] = float(value) if value is not None else 0
                elif prop == "dTime":
                    bath_data["d_time"] = float(value) if value is not None else 0
                elif prop == "Disable":
                    bath_data["disable"] = bool(value) if value is not None else False
                elif prop == "Reserved":
                    bath_data["reserved"] = bool(value) if value is not None else False
                elif prop == "aPriority":
                    bath_data["priority"] = int(value) if value is not None else 0
            except Exception as e:
                logger.debug(f"Error reading Bath[{bath_number}].{prop}: {e}")
        
        return bath_data
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting bath {bath_number} status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/line/cycles")
async def get_completed_cycles(limit: int = 20):
    """Получить завершённые циклы (подвесы вышедшие из линии через Bath[34])."""
    # Get cycles from hanger service
    all_hangers = hanger_service.get_all_hangers()
    
    # Filter completed hangers (not currently in any bath)
    completed = [h for h in all_hangers if h.current_bath is None and h.baths_history]
    
    # Sort by last_updated descending
    completed.sort(key=lambda h: h.last_updated, reverse=True)
    
    cycles = []
    for hanger in completed[:limit]:
        if hanger.baths_history:
            first_bath = hanger.baths_history[0]
            last_bath = hanger.baths_history[-1]
            
            # Calculate total time
            total_time = 0
            for bath in hanger.baths_history:
                if bath.duration:
                    try:
                        total_time += float(bath.duration)
                    except (ValueError, TypeError):
                        pass
            
            cycles.append({
                "timestamp": hanger.last_updated,
                "pallete": hanger.hanger_number,
                "total_time": total_time,
                "baths_visited": [b.bath_number for b in hanger.baths_history]
            })
    
    return {
        "total": len(cycles),
        "cycles": cycles
    }


@router.get("/line/power")
async def get_power_supply_status():
    """Получить статус блока питания S8VK_X."""
    if not opcua_service.is_connected:
        if not await opcua_service.connect():
            raise HTTPException(status_code=500, detail="Cannot connect to OPC UA server")
    
    try:
        props = ["Status", "Voltage", "Current", "PeakHoldCurrent", "YearB4replace", 
                 "PercentB4replace", "TotalRunTime", "ContinuousRunTime"]
        
        power_data = {}
        for prop in props:
            try:
                value = await opcua_service.read_node(f"ns=4;s=S8VK_X.{prop}")
                power_data[prop.lower()] = value
            except Exception as e:
                logger.debug(f"Error reading S8VK_X.{prop}: {e}")
                power_data[prop.lower()] = None
        
        return power_data
        
    except Exception as e:
        logger.error(f"[OPC UA] Error getting power supply status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
