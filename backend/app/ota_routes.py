from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.ota_schemas import (
    FirmwareCreate, FirmwareResponse, FirmwareListResponse,
    OtaTaskCreate, OtaTaskResponse, OtaTaskDetailResponse,
    OtaTaskListResponse, OtaDeviceTaskListResponse, BatchStats,
)
from app.ota_crud import (
    create_firmware, get_firmwares, get_firmware, delete_firmware,
    create_ota_task, get_ota_tasks, get_ota_task, confirm_batch,
    abort_ota_task, get_ota_device_tasks, get_task_batch_stats,
    FirmwareNotFoundError, OtaTaskNotFoundError,
    NoMatchingDevicesError, InvalidTaskStateError,
)

router = APIRouter(prefix="/api/ota", tags=["OTA"])


@router.post("/firmwares/", response_model=FirmwareResponse, status_code=201)
def api_create_firmware(data: FirmwareCreate, db: Session = Depends(get_db)):
    firmware = create_firmware(db, data)
    return firmware


@router.get("/firmwares/", response_model=FirmwareListResponse)
def api_list_firmwares(
    target_model: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    firmwares, total = get_firmwares(db, target_model=target_model, skip=skip, limit=limit)
    return FirmwareListResponse(total=total, firmwares=firmwares)


@router.delete("/firmwares/{firmware_id}", status_code=204)
def api_delete_firmware(firmware_id: int, db: Session = Depends(get_db)):
    if not delete_firmware(db, firmware_id):
        raise HTTPException(status_code=404, detail=f"Firmware {firmware_id} not found")


@router.post("/tasks/", response_model=OtaTaskResponse, status_code=201)
def api_create_ota_task(data: OtaTaskCreate, db: Session = Depends(get_db)):
    try:
        task = create_ota_task(db, data)
    except FirmwareNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NoMatchingDevicesError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return task


@router.get("/tasks/", response_model=OtaTaskListResponse)
def api_list_ota_tasks(
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    tasks, total = get_ota_tasks(db, status=status, skip=skip, limit=limit)
    return OtaTaskListResponse(total=total, tasks=tasks)


@router.get("/tasks/{task_id}", response_model=OtaTaskDetailResponse)
def api_get_ota_task(task_id: int, db: Session = Depends(get_db)):
    task = get_ota_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"OTA task {task_id} not found")

    batch_stats = get_task_batch_stats(db, task_id)

    return OtaTaskDetailResponse(
        id=task.id,
        firmware_id=task.firmware_id,
        target_model=task.target_model,
        status=task.status,
        total_devices=task.total_devices,
        batch1_size=task.batch1_size,
        batch2_size=task.batch2_size,
        batch3_size=task.batch3_size,
        current_batch=task.current_batch,
        created_at=task.created_at,
        updated_at=task.updated_at,
        batch1=BatchStats(**batch_stats["batch1"]),
        batch2=BatchStats(**batch_stats["batch2"]),
        batch3=BatchStats(**batch_stats["batch3"]),
    )


@router.post("/tasks/{task_id}/confirm", response_model=OtaTaskResponse)
def api_confirm_batch(task_id: int, db: Session = Depends(get_db)):
    try:
        task = confirm_batch(db, task_id)
    except OtaTaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return task


@router.post("/tasks/{task_id}/abort", response_model=OtaTaskResponse)
def api_abort_ota_task(task_id: int, db: Session = Depends(get_db)):
    try:
        task = abort_ota_task(db, task_id)
    except OtaTaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return task


@router.get("/tasks/{task_id}/devices", response_model=OtaDeviceTaskListResponse)
def api_list_device_tasks(
    task_id: int,
    batch_number: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    task = get_ota_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"OTA task {task_id} not found")

    device_tasks, total = get_ota_device_tasks(
        db, task_id, batch_number=batch_number, status=status, skip=skip, limit=limit
    )
    return OtaDeviceTaskListResponse(total=total, device_tasks=device_tasks)
