from sqlalchemy import select, func, case, text
from sqlalchemy.orm import Session

from app.models import Device
from app.template_models import ConfigTemplate, TemplateBinding


def get_drift_data(db: Session, skip: int = 0, limit: int = 50, drifted_only: bool = False) -> dict:
    base_query = (
        select(
            Device.device_id,
            Device.model,
            ConfigTemplate.name.label("template_name"),
            TemplateBinding.expected_config_hash,
            TemplateBinding.current_config_hash,
        )
        .outerjoin(TemplateBinding, Device.device_id == TemplateBinding.device_id)
        .outerjoin(ConfigTemplate, TemplateBinding.template_id == ConfigTemplate.id)
    )

    # Count totals
    total_devices = db.execute(select(func.count()).select_from(Device)).scalar()

    drifted_count = db.execute(
        select(func.count()).select_from(TemplateBinding).where(
            TemplateBinding.expected_config_hash.isnot(None),
            TemplateBinding.expected_config_hash != TemplateBinding.current_config_hash,
        )
    ).scalar()

    bound_count = db.execute(
        select(func.count(func.distinct(TemplateBinding.device_id))).select_from(TemplateBinding)
    ).scalar()

    compliant_count = bound_count - drifted_count
    unbound_count = total_devices - bound_count

    if drifted_only:
        base_query = base_query.where(
            TemplateBinding.expected_config_hash.isnot(None),
            TemplateBinding.expected_config_hash != TemplateBinding.current_config_hash,
        )

    # Order drifted first
    base_query = base_query.order_by(
        case(
            (TemplateBinding.expected_config_hash.isnot(None).__and__(
                TemplateBinding.expected_config_hash != TemplateBinding.current_config_hash
            ), 0),
            else_=1,
        ),
        Device.model,
        Device.device_id,
    ).offset(skip).limit(limit)

    rows = db.execute(base_query).all()

    devices = []
    for row in rows:
        is_drifted = (
            row.expected_config_hash is not None
            and row.current_config_hash is not None
            and row.expected_config_hash != row.current_config_hash
        )
        devices.append({
            "device_id": row.device_id,
            "model": row.model,
            "template_name": row.template_name,
            "expected_hash": row.expected_config_hash,
            "current_hash": row.current_config_hash,
            "is_drifted": is_drifted,
        })

    return {
        "total_devices": total_devices,
        "drifted_count": drifted_count,
        "compliant_count": compliant_count,
        "unbound_count": unbound_count,
        "devices": devices,
    }


def get_heatmap_data(db: Session) -> dict:
    query = (
        select(
            Device.model,
            Device.kernel_version,
            func.count().label("count"),
            func.sum(
                case(
                    (TemplateBinding.expected_config_hash.isnot(None).__and__(
                        TemplateBinding.expected_config_hash != TemplateBinding.current_config_hash
                    ), 1),
                    else_=0,
                )
            ).label("drifted_count"),
        )
        .outerjoin(TemplateBinding, Device.device_id == TemplateBinding.device_id)
        .group_by(Device.model, Device.kernel_version)
        .order_by(Device.model, Device.kernel_version)
    )

    rows = db.execute(query).all()

    models = sorted(set(row.model for row in rows))
    kernel_versions = sorted(set(row.kernel_version for row in rows))

    cells = []
    for row in rows:
        drift_ratio = (row.drifted_count / row.count) if row.count > 0 else 0.0
        cells.append({
            "model": row.model,
            "kernel_version": row.kernel_version,
            "count": row.count,
            "drift_ratio": round(drift_ratio, 3),
        })

    return {
        "models": models,
        "kernel_versions": kernel_versions,
        "cells": cells,
    }
