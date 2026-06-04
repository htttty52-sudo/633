from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Firmware(Base):
    __tablename__ = "firmwares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=True, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OtaTask(Base):
    __tablename__ = "ota_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firmware_id: Mapped[int] = mapped_column(Integer, ForeignKey("firmwares.id"), nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    total_devices: Mapped[int] = mapped_column(Integer, nullable=False)
    batch1_size: Mapped[int] = mapped_column(Integer, nullable=False)
    batch2_size: Mapped[int] = mapped_column(Integer, nullable=False)
    batch3_size: Mapped[int] = mapped_column(Integer, nullable=False)
    current_batch: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OtaDeviceTask(Base):
    __tablename__ = "ota_device_tasks"
    __table_args__ = (
        UniqueConstraint("ota_task_id", "device_id", name="uq_ota_task_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ota_task_id: Mapped[int] = mapped_column(Integer, ForeignKey("ota_tasks.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    previous_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_version: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
