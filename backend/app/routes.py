from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.crud import (
    create_device,
    get_device,
    get_devices,
    update_device,
    delete_device,
    update_heartbeat,
    DuplicateDeviceError,
)
from app.schemas import DeviceCreate, DeviceUpdate, DeviceResponse, DeviceListResponse

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("/", response_model=DeviceResponse, status_code=201)
def api_create_device(device_data: DeviceCreate, db: Session = Depends(get_db)):
    try:
        device = create_device(db, device_data)
    except DuplicateDeviceError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return device


@router.get("/", response_model=DeviceListResponse)
def api_list_devices(
    is_online: Optional[bool] = Query(None, description="筛选在线/离线状态"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    devices, total = get_devices(db, is_online=is_online, skip=skip, limit=limit)
    return DeviceListResponse(total=total, devices=devices)


@router.get("/{device_id}", response_model=DeviceResponse)
def api_get_device(device_id: str, db: Session = Depends(get_db)):
    device = get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device


@router.put("/{device_id}", response_model=DeviceResponse)
def api_update_device(device_id: str, device_data: DeviceUpdate, db: Session = Depends(get_db)):
    device = update_device(db, device_id, device_data)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device


@router.delete("/{device_id}", status_code=204)
def api_delete_device(device_id: str, db: Session = Depends(get_db)):
    if not delete_device(db, device_id):
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")


@router.post("/{device_id}/heartbeat", response_model=DeviceResponse)
def api_heartbeat(device_id: str, db: Session = Depends(get_db)):
    device = update_heartbeat(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device
