import math
import random
import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Device
from app.ota_models import Firmware, OtaTask, OtaDeviceTask
from app.ota_schemas import FirmwareCreate, OtaTaskCreate
from app.config import OTA_UPGRADE_SUCCESS_RATE


class FirmwareNotFoundError(Exception):
    def __init__(self, firmware_id: int):
        self.firmware_id = firmware_id
        super().__init__(f"Firmware {firmware_id} not found")


class OtaTaskNotFoundError(Exception):
    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"OTA task {task_id} not found")


class NoMatchingDevicesError(Exception):
    def __init__(self, model: str):
        self.model = model
        super().__init__(f"No devices found with model '{model}'")


class InvalidTaskStateError(Exception):
    def __init__(self, task_id: int, current_status: str, expected: str):
        self.task_id = task_id
        self.current_status = current_status
        super().__init__(f"Task {task_id} is in '{current_status}' state, expected '{expected}'")


OTA_FAILURE_MESSAGES = [
    "Firmware download timeout: device unreachable",
    "Flash write error: insufficient storage space",
    "Firmware checksum verification failed",
    "Bootloader update failed: partition table mismatch",
    "Device rebooted unexpectedly during upgrade",
    "Firmware signature verification failed",
    "Network interruption during file transfer",
    "Watchdog timer expired during upgrade process",
]


def create_firmware(db: Session, data: FirmwareCreate) -> Firmware:
    checksum = hashlib.sha256(
        f"{data.version}-{data.target_model}-{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()

    firmware = Firmware(
        version=data.version,
        target_model=data.target_model,
        filename=data.filename,
        file_size=data.file_size,
        checksum=checksum,
        description=data.description,
    )
    db.add(firmware)
    db.commit()
    db.refresh(firmware)
    return firmware


def get_firmware(db: Session, firmware_id: int) -> Optional[Firmware]:
    stmt = select(Firmware).where(Firmware.id == firmware_id)
    return db.execute(stmt).scalar_one_or_none()


def get_firmwares(db: Session, target_model: Optional[str] = None,
                  skip: int = 0, limit: int = 50) -> tuple[list[Firmware], int]:
    stmt = select(Firmware)
    count_stmt = select(func.count()).select_from(Firmware)

    if target_model:
        stmt = stmt.where(Firmware.target_model == target_model)
        count_stmt = count_stmt.where(Firmware.target_model == target_model)

    total = db.execute(count_stmt).scalar()
    stmt = stmt.order_by(Firmware.created_at.desc()).offset(skip).limit(limit)
    firmwares = list(db.execute(stmt).scalars().all())
    return firmwares, total


def delete_firmware(db: Session, firmware_id: int) -> bool:
    firmware = get_firmware(db, firmware_id)
    if not firmware:
        return False
    db.delete(firmware)
    db.commit()
    return True


def _calculate_batch_sizes(total: int) -> tuple[int, int, int]:
    batch1 = max(1, math.ceil(total * 0.10))
    batch2 = max(0, math.ceil(total * 0.50) - batch1)
    batch3 = total - batch1 - batch2
    return batch1, batch2, batch3


def create_ota_task(db: Session, data: OtaTaskCreate) -> OtaTask:
    firmware = get_firmware(db, data.firmware_id)
    if not firmware:
        raise FirmwareNotFoundError(data.firmware_id)

    stmt = select(Device).where(Device.model == firmware.target_model)
    devices = list(db.execute(stmt).scalars().all())

    if not devices:
        raise NoMatchingDevicesError(firmware.target_model)

    total = len(devices)
    batch1_size, batch2_size, batch3_size = _calculate_batch_sizes(total)

    task = OtaTask(
        firmware_id=firmware.id,
        target_model=firmware.target_model,
        status="batch1_pending",
        total_devices=total,
        batch1_size=batch1_size,
        batch2_size=batch2_size,
        batch3_size=batch3_size,
        current_batch=1,
    )
    db.add(task)
    db.flush()

    random.shuffle(devices)

    idx = 0
    for batch_num, size in [(1, batch1_size), (2, batch2_size), (3, batch3_size)]:
        for _ in range(size):
            device = devices[idx]
            device_task = OtaDeviceTask(
                ota_task_id=task.id,
                device_id=device.device_id,
                batch_number=batch_num,
                status="pending",
                previous_version=device.kernel_version,
                target_version=firmware.version,
            )
            db.add(device_task)
            idx += 1

    db.commit()
    db.refresh(task)
    return task


def get_ota_task(db: Session, task_id: int) -> Optional[OtaTask]:
    stmt = select(OtaTask).where(OtaTask.id == task_id)
    return db.execute(stmt).scalar_one_or_none()


def get_ota_tasks(db: Session, status: Optional[str] = None,
                  skip: int = 0, limit: int = 50) -> tuple[list[OtaTask], int]:
    stmt = select(OtaTask)
    count_stmt = select(func.count()).select_from(OtaTask)

    if status:
        stmt = stmt.where(OtaTask.status == status)
        count_stmt = count_stmt.where(OtaTask.status == status)

    total = db.execute(count_stmt).scalar()
    stmt = stmt.order_by(OtaTask.created_at.desc()).offset(skip).limit(limit)
    tasks = list(db.execute(stmt).scalars().all())
    return tasks, total


def confirm_batch(db: Session, task_id: int) -> OtaTask:
    task = get_ota_task(db, task_id)
    if not task:
        raise OtaTaskNotFoundError(task_id)

    current = task.current_batch
    expected_status = f"batch{current}_pending"
    if task.status != expected_status:
        raise InvalidTaskStateError(task_id, task.status, expected_status)

    task.status = f"batch{current}_running"

    stmt = select(OtaDeviceTask).where(
        OtaDeviceTask.ota_task_id == task_id,
        OtaDeviceTask.batch_number == current,
        OtaDeviceTask.status == "pending",
    )
    device_tasks = list(db.execute(stmt).scalars().all())

    batch_has_failure = False
    failure_reason = None

    for dt in device_tasks:
        device_stmt = select(Device).where(Device.device_id == dt.device_id)
        device = db.execute(device_stmt).scalar_one_or_none()

        dt.status = "upgrading"
        dt.started_at = datetime.utcnow()

        if random.random() < OTA_UPGRADE_SUCCESS_RATE:
            dt.status = "success"
            dt.completed_at = datetime.utcnow()
            if device:
                device.kernel_version = dt.target_version
        else:
            dt.status = "failed"
            failure_reason = random.choice(OTA_FAILURE_MESSAGES)
            dt.error_message = failure_reason
            dt.completed_at = datetime.utcnow()
            batch_has_failure = True

    if batch_has_failure:
        _rollback_entire_batch(db, task_id, current, failure_reason)
        task.status = f"batch{current}_failed"
    else:
        _advance_task_state(task)

    db.commit()
    db.refresh(task)
    return task


def _rollback_entire_batch(db: Session, task_id: int, batch_number: int, reason: str):
    """When any device in a batch fails, roll back ALL devices in that batch."""
    stmt = select(OtaDeviceTask).where(
        OtaDeviceTask.ota_task_id == task_id,
        OtaDeviceTask.batch_number == batch_number,
    )
    device_tasks = list(db.execute(stmt).scalars().all())

    for dt in device_tasks:
        device_stmt = select(Device).where(Device.device_id == dt.device_id)
        device = db.execute(device_stmt).scalar_one_or_none()

        if device:
            device.kernel_version = dt.previous_version

        if dt.status == "success":
            dt.status = "failed"
            dt.error_message = f"Rolled back: batch failure caused by other device ({reason})"
            dt.completed_at = datetime.utcnow()
        elif dt.status != "failed":
            dt.status = "failed"
            if not dt.error_message:
                dt.error_message = reason
            dt.completed_at = datetime.utcnow()


def _advance_task_state(task: OtaTask):
    current = task.current_batch
    if current < 3:
        next_batch = current + 1
        next_size = getattr(task, f"batch{next_batch}_size")
        if next_size > 0:
            task.status = f"batch{next_batch}_pending"
            task.current_batch = next_batch
        else:
            task.status = "completed"
    else:
        task.status = "completed"


def retry_batch(db: Session, task_id: int) -> OtaTask:
    """Retry a failed batch: reset all failed device tasks to pending (failed→pending)."""
    task = get_ota_task(db, task_id)
    if not task:
        raise OtaTaskNotFoundError(task_id)

    current = task.current_batch
    expected_status = f"batch{current}_failed"
    if task.status != expected_status:
        raise InvalidTaskStateError(task_id, task.status, expected_status)

    stmt = select(OtaDeviceTask).where(
        OtaDeviceTask.ota_task_id == task_id,
        OtaDeviceTask.batch_number == current,
    )
    device_tasks = list(db.execute(stmt).scalars().all())

    for dt in device_tasks:
        dt.status = "pending"
        dt.error_message = None
        dt.started_at = None
        dt.completed_at = None

    task.status = f"batch{current}_pending"
    db.commit()
    db.refresh(task)
    return task


def abort_ota_task(db: Session, task_id: int) -> OtaTask:
    task = get_ota_task(db, task_id)
    if not task:
        raise OtaTaskNotFoundError(task_id)

    if task.status in ("completed", "aborted"):
        raise InvalidTaskStateError(task_id, task.status, "an active state")

    task.status = "aborted"
    db.commit()
    db.refresh(task)
    return task


def get_ota_device_tasks(db: Session, task_id: int,
                         batch_number: Optional[int] = None,
                         status: Optional[str] = None,
                         skip: int = 0, limit: int = 50) -> tuple[list[OtaDeviceTask], int]:
    stmt = select(OtaDeviceTask).where(OtaDeviceTask.ota_task_id == task_id)
    count_stmt = select(func.count()).select_from(OtaDeviceTask).where(OtaDeviceTask.ota_task_id == task_id)

    if batch_number:
        stmt = stmt.where(OtaDeviceTask.batch_number == batch_number)
        count_stmt = count_stmt.where(OtaDeviceTask.batch_number == batch_number)
    if status:
        stmt = stmt.where(OtaDeviceTask.status == status)
        count_stmt = count_stmt.where(OtaDeviceTask.status == status)

    total = db.execute(count_stmt).scalar()
    stmt = stmt.order_by(OtaDeviceTask.batch_number, OtaDeviceTask.id).offset(skip).limit(limit)
    device_tasks = list(db.execute(stmt).scalars().all())
    return device_tasks, total


def get_task_batch_stats(db: Session, task_id: int) -> dict:
    result = {}
    for batch_num in (1, 2, 3):
        stmt = select(OtaDeviceTask).where(
            OtaDeviceTask.ota_task_id == task_id,
            OtaDeviceTask.batch_number == batch_num,
        )
        tasks = list(db.execute(stmt).scalars().all())
        result[f"batch{batch_num}"] = {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.status == "pending"),
            "upgrading": sum(1 for t in tasks if t.status == "upgrading"),
            "success": sum(1 for t in tasks if t.status == "success"),
            "failed": sum(1 for t in tasks if t.status == "failed"),
        }
    return result


def get_upgrading_device_ids(db: Session) -> set[str]:
    stmt = select(OtaDeviceTask.device_id).where(OtaDeviceTask.status == "upgrading")
    return set(db.execute(stmt).scalars().all())
