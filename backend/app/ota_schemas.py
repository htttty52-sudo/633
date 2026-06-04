from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FirmwareCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=64)
    target_model: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=256)
    file_size: int = Field(..., gt=0)
    description: str = Field(default="", max_length=512)


class FirmwareResponse(BaseModel):
    id: int
    version: str
    target_model: str
    filename: str
    file_size: int
    checksum: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class FirmwareListResponse(BaseModel):
    total: int
    firmwares: list[FirmwareResponse]


class OtaTaskCreate(BaseModel):
    firmware_id: int


class BatchStats(BaseModel):
    total: int
    pending: int
    upgrading: int
    success: int
    failed: int


class OtaTaskResponse(BaseModel):
    id: int
    firmware_id: int
    target_model: str
    status: str
    total_devices: int
    batch1_size: int
    batch2_size: int
    batch3_size: int
    current_batch: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OtaTaskDetailResponse(BaseModel):
    id: int
    firmware_id: int
    target_model: str
    status: str
    total_devices: int
    batch1_size: int
    batch2_size: int
    batch3_size: int
    current_batch: int
    created_at: datetime
    updated_at: datetime
    batch1: BatchStats
    batch2: BatchStats
    batch3: BatchStats

    model_config = {"from_attributes": True}


class OtaTaskListResponse(BaseModel):
    total: int
    tasks: list[OtaTaskResponse]


class OtaDeviceTaskResponse(BaseModel):
    id: int
    ota_task_id: int
    device_id: str
    batch_number: int
    status: str
    previous_version: str
    target_version: str
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class OtaDeviceTaskListResponse(BaseModel):
    total: int
    device_tasks: list[OtaDeviceTaskResponse]
