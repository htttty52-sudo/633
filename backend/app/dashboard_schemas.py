from typing import Optional
from pydantic import BaseModel


class DriftDevice(BaseModel):
    device_id: str
    model: str
    template_name: Optional[str] = None
    expected_hash: Optional[str] = None
    current_hash: Optional[str] = None
    is_drifted: bool


class DriftResponse(BaseModel):
    total_devices: int
    drifted_count: int
    compliant_count: int
    unbound_count: int
    devices: list[DriftDevice]


class HeatmapCell(BaseModel):
    model: str
    kernel_version: str
    count: int
    drift_ratio: float


class HeatmapResponse(BaseModel):
    models: list[str]
    kernel_versions: list[str]
    cells: list[HeatmapCell]


class WorkerStatusItem(BaseModel):
    name: str
    last_heartbeat: Optional[str] = None
    is_alive: bool


class WorkerListResponse(BaseModel):
    total_workers: int
    active_workers: int
    workers: list[WorkerStatusItem]


class StreamStatsResponse(BaseModel):
    stream_length: int
    groups: list[dict]
    first_entry: Optional[dict] = None
    last_entry: Optional[dict] = None
