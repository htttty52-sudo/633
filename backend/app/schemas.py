from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64, description="唯一设备标识")
    model: str = Field(..., min_length=1, max_length=128, description="设备型号")
    kernel_version: str = Field(..., min_length=1, max_length=64, description="内核版本")


class DeviceUpdate(BaseModel):
    model: Optional[str] = Field(None, max_length=128)
    kernel_version: Optional[str] = Field(None, max_length=64)


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    model: str
    kernel_version: str
    is_online: bool
    last_heartbeat: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeviceListResponse(BaseModel):
    total: int
    devices: list[DeviceResponse]
