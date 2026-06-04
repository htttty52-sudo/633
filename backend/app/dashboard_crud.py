from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from app.models import Device
from app.template_models import ConfigTemplate, TemplateBinding
from app.redis_client import get_redis

EXPECTED_HASH_PREFIX = "drift:expected:"


def sync_expected_hashes_to_redis(db: Session):
    """Bulk-load all expected hashes into Redis for fast drift lookups."""
    r = get_redis()
    stmt = select(TemplateBinding.device_id, TemplateBinding.expected_config_hash).where(
        TemplateBinding.expected_config_hash.isnot(None)
    )
    rows = db.execute(stmt).all()
    pipe = r.pipeline()
    for device_id, expected_hash in rows:
        pipe.set(f"{EXPECTED_HASH_PREFIX}{device_id}", expected_hash)
    pipe.execute()
    return len(rows)


def cache_expected_hash(device_id: str, expected_hash: str):
    """Cache a single device's expected hash in Redis."""
    r = get_redis()
    r.set(f"{EXPECTED_HASH_PREFIX}{device_id}", expected_hash)


def get_drift_data(db: Session, skip: int = 0, limit: int = 50, drifted_only: bool = False) -> dict:
    """Drift detection: reads expected hashes from Redis, compares with DB current hashes."""
    r = get_redis()

    total_devices = db.execute(select(func.count()).select_from(Device)).scalar()

    # Get all bindings with current_config_hash from DB
    bindings_stmt = (
        select(
            TemplateBinding.device_id,
            TemplateBinding.current_config_hash,
            TemplateBinding.drift_field_count,
            TemplateBinding.template_id,
        )
    )
    bindings = db.execute(bindings_stmt).all()

    # Build device->model lookup
    devices_stmt = select(Device.device_id, Device.model)
    device_models = {row.device_id: row.model for row in db.execute(devices_stmt).all()}

    # Build template_id->name lookup
    tpl_stmt = select(ConfigTemplate.id, ConfigTemplate.name)
    tpl_names = {row.id: row.name for row in db.execute(tpl_stmt).all()}

    # Batch-read expected hashes from Redis
    bound_device_ids = [b.device_id for b in bindings]
    if bound_device_ids:
        redis_keys = [f"{EXPECTED_HASH_PREFIX}{did}" for did in bound_device_ids]
        expected_hashes = r.mget(redis_keys)
    else:
        expected_hashes = []

    # Build drift result
    all_devices = []
    drifted_count = 0
    bound_set = set()

    for i, binding in enumerate(bindings):
        expected_hash = expected_hashes[i] if i < len(expected_hashes) else None
        current_hash = binding.current_config_hash
        bound_set.add(binding.device_id)

        is_drifted = (
            expected_hash is not None
            and current_hash is not None
            and expected_hash != current_hash
        )
        if is_drifted:
            drifted_count += 1

        if drifted_only and not is_drifted:
            continue

        all_devices.append({
            "device_id": binding.device_id,
            "model": device_models.get(binding.device_id, ""),
            "template_name": tpl_names.get(binding.template_id),
            "expected_hash": expected_hash,
            "current_hash": current_hash,
            "is_drifted": is_drifted,
            "drift_field_count": binding.drift_field_count if is_drifted else 0,
        })

    # Sort: drifted first, then by model/device_id
    all_devices.sort(key=lambda d: (0 if d["is_drifted"] else 1, d["model"], d["device_id"]))

    compliant_count = len(bound_set) - drifted_count
    unbound_count = total_devices - len(bound_set)

    # Paginate
    paginated = all_devices[skip:skip + limit]

    return {
        "total_devices": total_devices,
        "drifted_count": drifted_count,
        "compliant_count": compliant_count,
        "unbound_count": unbound_count,
        "devices": paginated,
    }


def get_heatmap_data(db: Session) -> dict:
    """Heatmap: color intensity based on average drift_field_count per model/kernel cell."""
    query = (
        select(
            Device.model,
            Device.kernel_version,
            func.count().label("count"),
            func.coalesce(func.avg(TemplateBinding.drift_field_count), 0).label("avg_drift_fields"),
            func.max(TemplateBinding.drift_field_count).label("max_drift_fields"),
        )
        .outerjoin(TemplateBinding, Device.device_id == TemplateBinding.device_id)
        .group_by(Device.model, Device.kernel_version)
        .order_by(Device.model, Device.kernel_version)
    )

    rows = db.execute(query).all()

    models = sorted(set(row.model for row in rows))
    kernel_versions = sorted(set(row.kernel_version for row in rows))

    # Find the global max to normalize color scale
    global_max = max((row.avg_drift_fields for row in rows), default=1) or 1

    cells = []
    for row in rows:
        # Normalize to 0.0-1.0 based on avg drift field count
        drift_intensity = float(row.avg_drift_fields) / float(global_max) if global_max > 0 else 0.0
        cells.append({
            "model": row.model,
            "kernel_version": row.kernel_version,
            "count": row.count,
            "avg_drift_fields": round(float(row.avg_drift_fields), 2),
            "max_drift_fields": int(row.max_drift_fields or 0),
            "drift_ratio": round(drift_intensity, 3),
        })

    return {
        "models": models,
        "kernel_versions": kernel_versions,
        "cells": cells,
    }
