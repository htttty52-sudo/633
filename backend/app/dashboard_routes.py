from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dashboard_schemas import (
    DriftResponse, HeatmapResponse, WorkerListResponse, StreamStatsResponse
)
from app.dashboard_crud import get_drift_data, get_heatmap_data
from app.redis_client import get_redis
from app.redis_cache import cache_get, cache_set
from app.worker_health import get_active_workers
from app.redis_streams import get_stream_info

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/heatmap", response_model=HeatmapResponse)
def get_heatmap(
    nocache: bool = Query(False),
    db: Session = Depends(get_db),
):
    cache_key = "dashboard:heatmap"
    if not nocache:
        cached = cache_get(cache_key)
        if cached:
            return cached

    data = get_heatmap_data(db)
    cache_set(cache_key, data)
    return data


@router.get("/drift", response_model=DriftResponse)
def get_drift(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    drifted_only: bool = Query(False),
    nocache: bool = Query(False),
    db: Session = Depends(get_db),
):
    cache_key = f"dashboard:drift:{skip}:{limit}:{drifted_only}"
    if not nocache:
        cached = cache_get(cache_key)
        if cached:
            return cached

    data = get_drift_data(db, skip=skip, limit=limit, drifted_only=drifted_only)
    cache_set(cache_key, data)
    return data


@router.get("/workers", response_model=WorkerListResponse)
def get_workers():
    r = get_redis()
    workers = get_active_workers(r)
    active = [w for w in workers if w["is_alive"]]
    return {
        "total_workers": len(workers),
        "active_workers": len(active),
        "workers": workers,
    }


@router.get("/stream-stats", response_model=StreamStatsResponse)
def get_stream_stats():
    r = get_redis()
    info = get_stream_info(r)
    return info
