from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Device
from app.schemas import DeviceCreate, DeviceUpdate


class DuplicateDeviceError(Exception):
    def __init__(self, device_id: str):
        self.device_id = device_id
        super().__init__(f"Device with ID '{device_id}' already exists")


def create_device(db: Session, device_data: DeviceCreate) -> Device:
    device = Device(
        device_id=device_data.device_id,
        model=device_data.model,
        kernel_version=device_data.kernel_version,
        is_online=True,
        last_heartbeat=datetime.utcnow(),
    )
    db.add(device)
    try:
        db.commit()
        db.refresh(device)
    except IntegrityError:
        db.rollback()
        raise DuplicateDeviceError(device_data.device_id)
    return device


def get_device(db: Session, device_id: str) -> Optional[Device]:
    return db.execute(
        select(Device).where(Device.device_id == device_id)
    ).scalar_one_or_none()


def get_devices(db: Session, is_online: Optional[bool] = None, skip: int = 0, limit: int = 100) -> tuple[list[Device], int]:
    query = select(Device)
    count_query = select(func.count()).select_from(Device)

    if is_online is not None:
        query = query.where(Device.is_online == is_online)
        count_query = count_query.where(Device.is_online == is_online)

    total = db.execute(count_query).scalar()
    devices = db.execute(query.offset(skip).limit(limit).order_by(Device.created_at.desc())).scalars().all()
    return list(devices), total


def update_device(db: Session, device_id: str, device_data: DeviceUpdate) -> Optional[Device]:
    device = get_device(db, device_id)
    if not device:
        return None
    update_fields = device_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(device, field, value)
    db.commit()
    db.refresh(device)
    return device


def delete_device(db: Session, device_id: str) -> bool:
    device = get_device(db, device_id)
    if not device:
        return False
    db.delete(device)
    db.commit()
    return True


def update_heartbeat(db: Session, device_id: str) -> Optional[Device]:
    device = get_device(db, device_id)
    if not device:
        return None
    device.last_heartbeat = datetime.utcnow()
    device.is_online = True
    db.commit()
    db.refresh(device)
    return device


def check_heartbeat_timeout(db: Session, timeout_seconds: int) -> int:
    """Mark devices as offline if heartbeat exceeds timeout. Returns count of affected devices."""
    threshold = datetime.utcnow()
    from datetime import timedelta
    threshold = threshold - timedelta(seconds=timeout_seconds)

    devices = db.execute(
        select(Device).where(Device.is_online == True, Device.last_heartbeat < threshold)
    ).scalars().all()

    count = 0
    for device in devices:
        device.is_online = False
        count += 1

    if count > 0:
        db.commit()
    return count
