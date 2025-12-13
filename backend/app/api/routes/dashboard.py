"""
Dashboard API routes.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from app.services.excel_service import excel_service
from app.services.ftp_service import ftp_service
from app.schemas.dashboard import (
    DashboardResponse,
    HangerData,
    FileStatus,
    FTPStatus,
    UnloadEvent
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    days: Optional[int] = Query(default=7, ge=1, le=365, description="Days to look back"),
    limit: Optional[int] = Query(default=100, ge=1, le=1000, description="Max records")
):
    """
    Get dashboard data with production records.
    
    Returns recent production data from Excel file.
    """
    try:
        products = excel_service.get_products(limit=limit, days=days)
        
        # Convert to HangerData format
        hanger_data = []
        for i, product in enumerate(products):
            hanger = HangerData(
                number=str(product.get('number', product.get('№', i + 1))),
                date=str(product.get('date', product.get('Дата', ''))),
                time=str(product.get('time', product.get('Время', ''))),
                client=str(product.get('client', product.get('Клиент', '—'))),
                profile=str(product.get('profile', product.get('Профиль', '—'))),
                color=str(product.get('color', product.get('Цвет', '—'))),
                lamels_qty=product.get('lamels_qty', product.get('Кол-во ламелей', 0)),
                kpz_number=str(product.get('kpz_number', product.get('КПЗ', '—'))),
                material_type=str(product.get('material_type', product.get('Тип материала', '—')))
            )
            hanger_data.append(hanger)
        
        return DashboardResponse(
            success=True,
            products=hanger_data,
            total=len(hanger_data),
            total_all=len(products),
            days_filter=days
        )
    except Exception as e:
        return DashboardResponse(
            success=False,
            error=str(e)
        )


@router.get("/status/file", response_model=FileStatus)
async def get_file_status():
    """
    Get Excel file status.
    """
    from app.core.config import settings
    
    try:
        path = settings.excel_path
        if path and path.exists():
            stat = path.stat()
            return FileStatus(
                is_open=False,  # Can't reliably detect if file is open
                last_modified=datetime.fromtimestamp(stat.st_mtime),
                file_name=path.name
            )
        return FileStatus(
            is_open=False,
            error="Excel file not found"
        )
    except Exception as e:
        return FileStatus(error=str(e))


@router.get("/status/ftp", response_model=FTPStatus)
async def get_ftp_status():
    """
    Get FTP connection status.
    """
    try:
        # Try to connect
        client = await ftp_service.connect()
        connected = client is not None
        
        if client:
            await client.quit()
        
        return FTPStatus(
            connected=connected,
            last_check=datetime.now()
        )
    except Exception as e:
        return FTPStatus(
            connected=False,
            last_check=datetime.now(),
            error=str(e)
        )


@router.get("/events", response_model=list[UnloadEvent])
async def get_today_events():
    """
    Get today's unload events from FTP.
    """
    try:
        content = await ftp_service.read_today_log()
        events = ftp_service.parse_unload_events(content)
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
